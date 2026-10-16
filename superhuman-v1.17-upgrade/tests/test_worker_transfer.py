import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from zipfile import ZipFile,ZIP_DEFLATED
from superhuman.hosted import jobs,worker,transfer,auth
from superhuman.runtime import engine as r
from superhuman.projects import engine as p


class Client:
    def __init__(self,fail=False):
        self.calls=[];self.fail=fail;self.chat=N(completions=N(create=self.create))
    def create(self,**kwargs):
        self.calls.append(kwargs)
        if self.fail:raise RuntimeError('private-provider-diagnostic')
        name=kwargs.get('response_format',{}).get('json_schema',{}).get('name')
        if name=='superhuman_project_plan':
            text=json.dumps({'tasks':[{'id':'draft','kind':'collab','title':'Prepare briefing','details':'Prepare a local briefing.','depends_on':[],'checks':{'max_words':100,'required_terms':[]}}]})
        elif name=='superhuman_stage_review':text=json.dumps({'issues':[]})
        elif name=='superhuman_final_deliverable':text=json.dumps({'deliverable':'Useful briefing for review.','verification_needed':[]})
        else:text='Useful briefing for review.'
        return N(choices=[N(message=N(content=text,refusal=None),finish_reason='stop')])


class WorkerTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=Path.cwd();self.root=Path(self.temp.name)/'source';self.root.mkdir();os.chdir(self.root)
        self.env=patch.dict(os.environ,{'SUPERHUMAN_IDENTITY_DIR':str(self.root/'data/identity'),'SUPERHUMAN_MEMORY_PATH':str(self.root/'data/memory/records.json')});self.env.start()
    def tearDown(self):self.env.stop();os.chdir(self.old);self.temp.cleanup()
    def serve(self,client,**kwargs):return worker.serve(once=True,client=client,**kwargs)
    def prepare_bundle_root(self):
        (self.root/'superhuman/hosted').mkdir(parents=True)
        (self.root/'superhuman/hosted/__init__.py').write_text('# fixture source')
        (self.root/'.env').write_text('SECRET=must-not-transfer')
        (self.root/'requirements.txt').write_text('fixture')
        (self.root/'data').mkdir(exist_ok=True)
    def output_executor(self,task,brief,folder):
        file=folder/'output.md';file.write_text('A preserved briefing.\n',encoding='utf-8');return {'output':str(file.resolve())}
    def test_worker_runs_authorized_task(self):
        pid=r.enqueue('collab','marketing','Prepare briefing');client=Client();self.serve(client)
        self.assertEqual(p.get(pid)['status'],'needs_review');self.assertEqual(len(client.calls),3)
    def test_worker_restart_continues_without_repeating_completed_work(self):
        pid=r.enqueue('collab','marketing','Prepare briefing');client=Client()
        self.serve(client);self.serve(client)
        self.assertEqual(len(client.calls),3);self.assertEqual(p.get(pid)['used_calls'],3)
    def test_worker_failure_is_not_automatically_retried(self):
        pid=r.enqueue('collab','marketing','Prepare briefing');client=Client(fail=True)
        self.serve(client);self.serve(client)
        self.assertEqual(len(client.calls),1);self.assertEqual(p.get(pid)['tasks'][0]['status'],'failed')
        self.assertNotIn('private-provider-diagnostic',json.dumps(r.history()))
    def test_planning_runs_in_worker_and_stops_for_approval(self):
        pid=p.create('marketing','Prepare a briefing',max_calls=10);jobs.request_plan(pid);client=Client()
        self.serve(client)
        self.assertEqual(p.get(pid)['status'],'plan_review');self.assertEqual(len(client.calls),1)
        self.serve(client);self.assertEqual(len(client.calls),1)
        p.approve_plan(pid);self.serve(client);self.serve(client)
        self.assertEqual(p.get(pid)['status'],'needs_review');self.assertEqual(len(client.calls),7)
    def test_duplicate_planning_request_refused(self):
        pid=p.create('marketing','Prepare briefing');jobs.request_plan(pid)
        with self.assertRaises(ValueError):jobs.request_plan(pid)
    def test_failed_planning_not_automatically_replayed(self):
        pid=p.create('marketing','Prepare briefing');jobs.request_plan(pid);client=Client(fail=True)
        self.serve(client);self.serve(client)
        self.assertEqual(len(client.calls),1);self.assertEqual(p.get(pid)['status'],'plan_failed')
    def test_pause_persists_across_worker_restarts(self):
        pid=r.enqueue('collab','marketing','Prepare briefing');jobs.pause(True);client=Client()
        self.serve(client);self.assertEqual(client.calls,[]);self.assertEqual(p.get(pid)['tasks'][0]['status'],'pending')
        jobs.pause(False);self.serve(client);self.assertEqual(len(client.calls),3)
    def test_missing_api_key_does_not_claim_work(self):
        pid=r.enqueue('collab','marketing','Prepare briefing')
        with patch.object(worker,'configured_client',return_value=None):worker.serve(once=True)
        self.assertEqual(p.get(pid)['tasks'][0]['status'],'pending');self.assertEqual(p.get(pid)['used_calls'],0)
    def test_heartbeat_and_stop_status_persist(self):
        jobs.initialize();jobs.pulse('owner','idle');self.assertTrue(jobs.worker_status()['online'])
        jobs.pulse('owner','stopped');self.assertFalse(jobs.worker_status()['online'])
    def test_worker_lock_prevents_parallel_service(self):
        with r.worker_lock():
            with self.assertRaises(RuntimeError):self.serve(Client())
    def test_interrupted_task_not_replayed_on_service_restart(self):
        pid=r.enqueue('collab','marketing','Prepare briefing');p.claim(pid);client=Client();self.serve(client)
        self.assertEqual(client.calls,[]);self.assertEqual(p.get(pid)['tasks'][0]['status'],'running')
    def test_bundle_excludes_env_and_snapshots_sqlite(self):
        self.prepare_bundle_root();pid=r.enqueue('collab','marketing','Prepare briefing');p.run_one(pid,executor=self.output_executor)
        archive=Path(self.temp.name)/'bundle.zip';transfer.bundle(self.root,archive)
        with ZipFile(archive) as z:
            self.assertNotIn('.env',z.namelist());self.assertFalse(any(n.endswith(('-wal','-shm')) for n in z.namelist()))
            self.assertIn('data/superhuman_projects.db',z.namelist())
            self.assertIn('bundle-manifest.json',z.namelist())
    def test_round_trip_rebases_paths_and_preserves_artifact_hash(self):
        self.prepare_bundle_root();pid=r.enqueue('collab','marketing','Prepare briefing');p.run_one(pid,executor=self.output_executor)
        original=p.get(pid)['tasks'][0];old_meta=json.loads(original['result_json']);old_hash=old_meta['content_sha256']
        archive=Path(self.temp.name)/'bundle.zip';transfer.bundle(self.root,archive)
        target=Path(self.temp.name)/'restored';transfer.restore(archive,target)
        os.chdir(target)
        meta=json.loads(p.get(pid)['tasks'][0]['result_json']);_,text=p._text(meta)
        self.assertTrue(meta['output'].startswith(str(target)))
        self.assertEqual(meta['content_sha256'],old_hash);self.assertIn('preserved briefing',text)
    def test_windows_bundle_paths_work_after_linux_restore(self):
        self.prepare_bundle_root();pid=r.enqueue('collab','marketing','Prepare briefing');p.run_one(pid,executor=self.output_executor)
        task=p.get(pid)['tasks'][0];meta=json.loads(task['result_json'])
        relative=Path(meta['output']).relative_to(self.root)
        windows_root=r'C:\superhuman-os-starter'
        windows_output=windows_root+'\\'+str(relative).replace('/','\\')
        meta['output']=windows_output
        with p.connect() as db:db.execute('UPDATE project_tasks SET output=?,result_json=? WHERE project_id=?',(windows_output,json.dumps(meta),pid))
        archive=Path(self.temp.name)/'bundle.zip';transfer.bundle(self.root,archive)
        windows_archive=Path(self.temp.name)/'windows.zip'
        with ZipFile(archive) as z,ZipFile(windows_archive,'w') as dest:
            for name in z.namelist():
                raw=z.read(name)
                if name=='bundle-manifest.json':
                    manifest=json.loads(raw);manifest['original_root']=windows_root;raw=json.dumps(manifest).encode()
                dest.writestr(name,raw)
        target=Path(self.temp.name)/'restored';transfer.restore(windows_archive,target);os.chdir(target)
        migrated=json.loads(p.get(pid)['tasks'][0]['result_json']);_,text=p._text(migrated)
        self.assertIn('preserved briefing',text);self.assertTrue(migrated['output'].startswith(str(target)))
    def test_windows_paths_normalized_only_in_metadata(self):
        old=r'C:\superhuman-os-starter';new=Path('/home/forge/superhuman')
        value={'output':old+r'\data\outputs\test.md','text':old+r'\data\outputs\test.md','stage_archive':r'data\outputs\stages','url':'https://example.org'}
        updated=transfer.rebase(value,old,new)
        self.assertEqual(updated['output'],str(new/'data/outputs/test.md'))
        self.assertEqual(updated['text'],value['text']);self.assertEqual(updated['url'],value['url'])
        self.assertEqual(updated['stage_archive'],'data/outputs/stages')
    def test_restore_revokes_sessions_keeps_owner_credentials(self):
        self.prepare_bundle_root();store=auth.Store('data/hosted/auth.sqlite3');store.setup('owner','synthetic-owner-password');raw,_=store.new_session()
        archive=Path(self.temp.name)/'bundle.zip';transfer.bundle(self.root,archive);target=Path(self.temp.name)/'restored';transfer.restore(archive,target)
        restored=auth.Store(target/'data/hosted/auth.sqlite3');self.assertTrue(restored.configured());self.assertIsNone(restored.session(raw))
    def test_restore_refuses_nonempty_target(self):
        target=Path(self.temp.name)/'restored';target.mkdir();(target/'keep.txt').write_text('Keep')
        with self.assertRaises(ValueError):transfer.restore('missing.zip',target)
        self.assertEqual((target/'keep.txt').read_text(),'Keep')
    def test_corrupt_archive_rejected_without_partial_install(self):
        self.prepare_bundle_root();archive=Path(self.temp.name)/'bundle.zip';transfer.bundle(self.root,archive)
        bad=Path(self.temp.name)/'bad.zip'
        with ZipFile(archive) as z,ZipFile(bad,'w') as dest:
            for name in z.namelist():dest.writestr(name,b'changed' if name=='requirements.txt' else z.read(name))
        target=Path(self.temp.name)/'restored'
        with self.assertRaises(ValueError):transfer.restore(bad,target)
        self.assertFalse(target.exists())
    def test_path_traversal_archive_rejected(self):
        bad=Path(self.temp.name)/'bad.zip';raw=b'bad';name='data/../../escape'
        manifest={'original_root':'C:/source','files':[{'name':name,'bytes':3,'sha256':hashlib.sha256(raw).hexdigest()}]}
        with ZipFile(bad,'w') as z:z.writestr(name,raw);z.writestr('bundle-manifest.json',json.dumps(manifest))
        with self.assertRaises(ValueError):transfer.restore(bad,Path(self.temp.name)/'restored')
        self.assertFalse((Path(self.temp.name)/'escape').exists())
    def test_existing_bundle_not_overwritten(self):
        self.prepare_bundle_root();archive=Path(self.temp.name)/'bundle.zip';archive.write_text('Existing')
        with self.assertRaises(ValueError):transfer.bundle(self.root,archive)
        self.assertEqual(archive.read_text(),'Existing')


if __name__=='__main__':unittest.main()
