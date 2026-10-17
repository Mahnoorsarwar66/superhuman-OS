"""Allowlisted adapters over existing capabilities; no arbitrary shell or HTTP tool."""
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
from superhuman.projects import engine as projects

@dataclass(frozen=True)
class Tool:
    name:str
    description:str
    permission:str
    fields:dict
    required:tuple=()
    calls:int=0
    mutates:bool=False

def spec(name,description,permission,fields,required=(),calls=0,mutates=False):return Tool(name,description,permission,fields,tuple(required),calls,mutates)
REGISTRY={t.name:t for t in [
 spec('team.handoff','Request another specialist: title <=180, instruction <=4000, acceptance <=1500. Parent waits for the Twin.','team_collaboration',{'recipient':str,'title':str,'instruction':str,'acceptance':str},('recipient','title','instruction','acceptance'),mutates=True),
 spec('team.challenge','Record concern, evidence and alternative; pause for the Twin/owner.','team_collaboration',{'reason':str,'evidence':str,'alternative':str},('reason','evidence','alternative'),mutates=True),
 spec('team.remember','Propose scoped employee memory; never confirms it automatically.','team_collaboration',{'kind':str,'content':str},('content',),mutates=True),
 spec('assurance.workspace','Read permitted requirement/evidence/gap/rubric pages; section and offset, two records per page.','read_workspace',{'section':str,'offset':int},('section',)),
 spec('assurance.record','Record JSON operation: requirement(key,title,critical,origin); evidence(requirement_id,kind,source_id,quote,locator,interpretation); review_evidence(id,expected,decision,note); gap(key,question,employee,critical); initiative(key,title,hypothesis). Include operation. No permission or strategic approval changes.','team_collaboration',{'record_json':str},('record_json',),mutates=True),
 spec('assurance.scorecard','Independent reviewer: JSON packet_id,digest,scores array with criterion,verdict(pass/revise/fail),rationale for every criterion.','team_collaboration',{'record_json':str},('record_json',),mutates=True),
 spec('milestone.read_output','Read a permitted milestone contribution or approved prior result in full.','read_workspace',{'task_id':str},('task_id',)),
 spec('milestone.note','Save a versioned working note for this milestone; never approves facts.','team_collaboration',{'key':str,'content':str,'expected_version':int},('key','content','expected_version'),mutates=True),
 spec('storage.pdf_pages','Read up to five complete PDF text pages from a permitted Storage source; no OCR.','read_workspace',{'item_id':str,'start_page':int,'end_page':int},('item_id','start_page','end_page')),
 spec('workspace.list','List uploaded source files and coding session identifiers.','read_workspace',{}),
 spec('workspace.read','Read supported PDF/DOCX/XLSX/text source with extraction limits and a hash.','read_workspace',{'filename':str},('filename',)),
 spec('workspace.search','Literal search of supported workstream source files.','read_workspace',{'query':str},('query',)),
 spec('table.profile','Profile an uploaded CSV with deterministic calculations.','read_workspace',{'filename':str},('filename',)),
 spec('calculate','Evaluate bounded arithmetic, never Python code.','read_workspace',{'expression':str},('expression',)),
 spec('context.lookup','Retrieve current memory, writing guidance and department context.','read_workspace',{'query':str},('query',)),
 spec('projects.list','Read projects and task statuses in this department.','read_workspace',{}),
 spec('research.web','Run existing cited web research, returning an unverified research draft.','read_web',{'title':str,'query':str},('title','query'),calls=1),
 spec('draft.create','Use existing draft/critique/revision workflow and inspect its saved text.','create_output',{'title':str,'instructions':str},('title','instructions'),calls=3),
 spec('document.export','Export exact text or a verified prior action to Word/PDF/XLSX.','create_output',{'title':str,'format':str,'text':str,'source_action':str,'numeric':bool},('title','format'),mutates=True),
 spec('spreadsheet.create','Create XLSX from CSV text, preserving text/numeric settings; no formulas.','create_output',{'title':str,'text':str,'source_action':str,'numeric':bool},('title',),mutates=True),
 spec('coding.inspect','Inspect an existing isolated coding working copy.','read_workspace',{'session_id':str},('session_id',)),
 spec('coding.read','Read an existing file in that coding working copy.','read_workspace',{'session_id':str,'filename':str},('session_id','filename')),
 spec('coding.syntax','Parse Python files; this does not execute tests.','read_workspace',{'session_id':str},('session_id',)),
 spec('coding.diff','Inspect changes against the original coding snapshot.','read_workspace',{'session_id':str},('session_id',)),
 spec('coding.edit','Edit an existing isolated file using its expected content hash; saves a before-copy.','edit_code',{'session_id':str,'filename':str,'text':str,'expected_hash':str,'note':str},('session_id','filename','text','expected_hash','note'),mutates=True),
 spec('coding.tests','Run a selected existing unittest module in the existing restricted Docker runner.','run_tests',{'session_id':str,'module':str},('session_id','module')),
 spec('coding.package','Package that isolated working copy, diff and history.','create_output',{'session_id':str},('session_id',),mutates=True),
 spec('inbox.cached','Read cached previews for an inbox assigned to this department.','read_mail',{'slot':str,'limit':int},('slot',)),
 spec('inbox.queue_sync','Queue an existing read-only sync; queued is not proof of completed sync.','read_mail_network',{'slot':str},('slot',),mutates=True),
 spec('inbox.status','Inspect saved sync results for a department inbox.','read_mail',{'slot':str},('slot',)),
 spec('project.create','Create a new unplanned objective in this department; no tasks or paid planning start.','create_project',{'title':str,'details':str,'max_calls':int},('title','details'),mutates=True),
 spec('memory.propose','Save a proposed feedback/decision note; it requires owner confirmation.','propose_memory',{'title':str,'content':str,'kind':str},('title','content'),mutates=True),
]}
PERMISSIONS={
 'team_collaboration':'Internal handoff requests, disagreements and proposed employee memory',
'read_workspace':'Read files, context and existing project/coding records',
'create_output':'Create drafts, document/spreadsheet exports and coding packages',
'read_web':'Public web research (additional model requests)',
'read_mail':'Read cached inbox previews assigned to this department',
'read_mail_network':'Queue read-only remote inbox syncs',
'edit_code':'Edit existing files in isolated coding working copies',
'run_tests':'Execute existing selected tests in the restricted Docker runner',
'create_project':'Create unplanned internal project objectives',
'propose_memory':'Propose memory/feedback notes for owner confirmation'}
DEFAULT_PERMISSIONS=('read_workspace','create_output')

def validate(name,args):
    if name not in REGISTRY:raise ValueError('Unknown tool')
    tool=REGISTRY[name]
    if not isinstance(args,dict) or set(args)-set(tool.fields) or any(k not in args for k in tool.required):raise ValueError('Arguments do not match this tool contract')
    for k,v in args.items():
        if type(v) is not tool.fields[k]:raise ValueError('Invalid argument type for '+k)
        if isinstance(v,str) and (len(v)>100000 or '\x00' in v):raise ValueError('Tool text is too large or contains unsupported characters')
    if name in ('document.export','spreadsheet.create') and bool(args.get('text'))==bool(args.get('source_action')):raise ValueError('Provide text OR source_action, not both')
    if name=='document.export' and args['format'] not in ('docx','pdf','xlsx'):raise ValueError('Unsupported export format')
    return tool

def describe():return [{'name':t.name,'description':t.description,'permission':t.permission,'fields':{k:v.__name__ for k,v in t.fields.items()},'required':list(t.required),'model_requests':t.calls,'writes':t.mutates} for t in REGISTRY.values()]

def text_from_action(run,args):
    from . import store
    a=next((a for a in run['actions'] if a['id']==args.get('source_action') and a['status'] in ('succeeded','cached')),None)
    if not a:raise ValueError('Choose a successful action in this run')
    result=json.loads(a['result_json'])
    if result.get('output'):
        _,text=projects._text(result);return text
    text=result.get('text')
    if not isinstance(text,str):raise ValueError('That action has no exportable text')
    return text

def outcome(data,success=True,reason='Contract and local result checked',**extra):
    return {'data':data,'verification':{'verified':bool(success),'reason':reason,**extra},'success':bool(success)}

def execute(name,args,run,client,folder,path):
    tool=validate(name,args);scope=run['project']['workstream']
    if name.startswith('assurance.'):
        from superhuman.assurance.tools import execute as execute_assurance
        return outcome(execute_assurance(name,args,run,path))
    if name=='milestone.read_output':
        from superhuman.milestones.workflow import read_output
        return outcome(read_output(run,args['task_id'],path))
    if name=='milestone.note':
        from superhuman.milestones.pdf import note
        return outcome(note(run,args['key'],args['content'],args['expected_version'],path))
    if name=='storage.pdf_pages':
        from superhuman.milestones.pdf import read_pages
        return outcome(read_pages(run,args['item_id'],args['start_page'],args['end_page'],path))
    if name.startswith('team.'):
        from superhuman.team.work import request_tool
        return request_tool(name,args,run,path)
    from superhuman.capabilities import local,coding,exports
    from superhuman.departments.store import snapshot,materials
    if name=='workspace.list':
        files,_,warnings=materials(scope);base=local.ROOT.resolve()/scope/'coding';sessions=[]
        if base.is_dir() and not base.is_symlink():
            for d in sorted(base.iterdir()):
                if d.is_dir() and not d.is_symlink():
                    try:record=coding.inspect(scope,d.name);sessions.append({'session_id':d.name,'label':record.get('label',''),'files':[f['name'] for f in record['files']]})
                    except (ValueError,OSError):continue
        return outcome({'files':files,'coding_sessions':sessions,'warnings':warnings})
    from superhuman.foundation import storage
    if name=='workspace.read':return outcome(storage.read_for_run(run,args['filename'],path))
    if name=='workspace.search':return outcome(storage.search_for_run(run,args['query'],path))
    if name=='table.profile':storage.read_for_run(run,args['filename'],path)
    if name in ('workspace.search','table.profile'):
        result=local.execute(scope,'search_files' if name=='workspace.search' else 'profile_table',**args)
        return outcome(result.get('result',{}),result['status']=='completed',result.get('error','Local operation completed'))
    if name=='calculate':return outcome(local.calculate(args['expression']))
    if name=='context.lookup':
        from superhuman.identity.selection import select_context
        result=select_context(scope,args['query'],run['project']['details']);result['storage']=storage.run_search(run,args['query'],path);return outcome(result)
    if name=='projects.list':
        data=snapshot(scope,path=path);return outcome({'projects':[{k:p[k] for k in ('id','objective','status','used_calls','max_calls')} for p in data['projects']],'tasks':[{k:t[k] for k in ('project_id','id','title','status')} for t in data['tasks']]})
    if name in ('draft.create','research.web'):
        if name=='draft.create':
            from superhuman.collab.runner import run_collaboration
            result=run_collaboration(args['title'],args['instructions'],project=scope,client=client,output_dir=folder,requirements={})
        else:
            from superhuman.research.runner import run_research
            result=run_research(args['title'],args['query'],project=scope,client=client,output_dir=folder)
        _,text=projects._text(result)
        errors=projects.quality(result,text,{},'research' if name=='research.web' else 'collab')
        result['content_sha256']=hashlib.sha256(text.encode()).hexdigest()
        return outcome(result,not errors,'; '.join(errors) if errors else 'Saved text integrity and existing quality checks passed; factual claims remain unverified')
    if name in ('document.export','spreadsheet.create'):
        text=args.get('text') or text_from_action(run,args)
        record=exports.generate(scope,'xlsx' if name=='spreadsheet.create' else args['format'],args['title'],text,source={'kind':'agentic_action','project_id':run['project_id'],'source_action':args.get('source_action','')},numeric=args.get('numeric',False))
        artifact,_=exports.artifact(scope,record['export_id'])
        return outcome({**record,'download_url':'/documents/download/'+scope+'/'+record['export_id']},artifact.is_file(),'Created artifact reopened and content hash checked')
    if name.startswith('coding.'):
        sid=args['session_id']
        if name=='coding.inspect':return outcome(coding.inspect(scope,sid))
        if name=='coding.read':return outcome(coding.read(scope,sid,args['filename']))
        if name=='coding.syntax':
            result=coding.syntax(scope,sid);return outcome(result,result['status']=='passed','Syntax '+result['status']+'; this is not test execution')
        if name=='coding.diff':return outcome({'text':coding.full_diff(scope,sid)})
        if name=='coding.edit':
            result=coding.edit(scope,sid,args['filename'],args['text'],args['expected_hash'],args['note']);checked=coding.read(scope,sid,args['filename'])
            return outcome({**result,'session_id':sid,'filename':args['filename'],'current_sha256':checked['sha256']},checked['sha256']==hashlib.sha256(args['text'].encode()).hexdigest(),'Working-copy edit hash checked; behavior not yet verified')
        if name=='coding.tests':
            result=coding.run_tests(scope,sid,args['module'],confirmed=True)
            return outcome({**result,'session_id':sid},result['status']=='passed','Tests '+result['status']+'; unavailable runners are not reported as passing')
        if name=='coding.package':
            artifact=coding.package(scope,sid)
            return outcome({'session_id':sid,'filename':artifact.name,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'artifact_kind':'coding_package','snapshot':{f['name']:f['sha256'] for f in coding.inspect(scope,sid)['files']}},artifact.is_file(),'Coding archive exists and is hashed')
    if name.startswith('inbox.'):
        from superhuman.mail import store as mail
        account=mail.account(args['slot'],path)
        if account.get('scope')!=scope:raise ValueError('This inbox is assigned to another department')
        if name=='inbox.cached':
            limit=args.get('limit',10)
            if not 1<=limit<=25:raise ValueError('Read at most 25 cached previews')
            return outcome({'messages':[{k:r[k] for k in ('id','sender','subject','sent_at','body')} for r in mail.messages(args['slot'],path,limit)]},True,'Cached previews only; sender identities and contents are unverified')
        if name=='inbox.status':
            queued=[a['created_at'] for a in run['actions'] if a['tool']=='inbox.queue_sync' and json.loads(a['arguments_json']).get('slot')==args['slot'] and a['status'] in ('pending','cached')]
            good=bool(account.get('last_sync') and not account.get('last_error') and (not queued or account['last_sync']>=max(queued)))
            result=outcome({k:account.get(k) for k in ('id','label','connected','last_sync','last_error')},good,'Successful sync observed' if good else 'No fresh successful sync verified yet');result['pending']=not good;return result
        result=outcome({'sync_id':mail.queue_sync(args['slot'],path),'slot':args['slot'],'status':'queued'},False,'Sync queued; use inbox.status after worker processing to verify completion');result['pending']=True;return result
    if name=='project.create':
        maximum=args.get('max_calls',12)
        if not 1<=maximum<=100:raise ValueError('Invalid future project request limit')
        pid=projects.create(scope,args['title'],args['details'],maximum,path)
        return outcome({'project_id':pid,'status':'new','url':'/work/'+pid},True,'Unplanned objective created; no paid work started')
    if name=='memory.propose':
        from superhuman.knowledge.store import Store
        kind=args.get('kind','feedback')
        if kind not in ('feedback','decision','update'):raise ValueError('Only feedback, decision or update proposals are supported')
        note=Store().add(scope,kind,args['title'],args['content'],source_type='inferred',source='agentic:'+run['project_id'],status='proposed')
        return outcome({'note_id':note['id'],'status':'proposed','url':'/memory/'+note['id']},True,'Proposed note saved; not eligible as confirmed memory until owner review')
    raise ValueError('No adapter for this tool')

def verify_saved(action,scope,path=projects.DEFAULT_DB):
    data=json.loads(action['result_json'] or '{}');tool=action['tool'];args=json.loads(action['arguments_json'])
    if data.get('assurance_receipt'):
        from superhuman.assurance.tools import verify_receipt
        verify_receipt(data['assurance_receipt'],path)
    if data.get('milestone_output_receipt'):
        from superhuman.milestones.workflow import verify_output_receipt
        verify_output_receipt(data['milestone_output_receipt'],path)
    from superhuman.foundation.storage import verify_lookup
    receipt=data.get('storage_lookup') or data.get('storage',{}).get('storage_lookup')
    if receipt:verify_lookup(receipt,path)
    if data.get('storage_receipt'):
        from superhuman.foundation.storage import verify_receipt
        verify_receipt(data['storage_receipt'],path)
    if tool in ('draft.create','research.web'):projects._text(data)
    if tool in ('document.export','spreadsheet.create'):
        from superhuman.capabilities.exports import artifact
        artifact(scope,data['export_id'])
    if tool in ('coding.tests','coding.syntax'):
        from superhuman.capabilities import coding
        snapshot={f['name']:f['sha256'] for f in coding.inspect(scope,args['session_id'])['files']}
        if snapshot!=data.get('snapshot'):raise ValueError('Code changed after this check; run the check again')
    if tool=='coding.edit':
        from superhuman.capabilities import coding
        if coding.read(scope,args['session_id'],args['filename'])['sha256']!=data['current_sha256']:raise ValueError('Working copy changed after that edit')
    if tool=='project.create':
        if projects.get(data['project_id'],path)['workstream']!=scope:raise ValueError('Created project scope changed')
    if tool=='coding.package':
        from superhuman.capabilities import coding
        current={f['name']:f['sha256'] for f in coding.inspect(scope,args['session_id'])['files']}
        if current!=data.get('snapshot'):raise ValueError('Coding copy changed after packaging; create a current package')
        folder,_=coding.session(scope,args['session_id']);file=folder/'events'/data['filename']
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=data['sha256']:raise ValueError('Coding package changed or is missing')
