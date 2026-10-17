"""Exact v1.29 integration; preserve the production CLI and orchestrator."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','experience/store.py','experience/chat.py','team/store.py','team/work.py','team/engine.py','hosted/worker.py','hosted/boundary.py','repairs/__init__.py','repairs/web.py','repairs/context.py','agentic/tools.py','workspace/web.py','team/web.py','team/__init__.py','comms/web.py','comms/engine.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated integration anchor: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.29 source: '+name+'; nothing overwritten')
    if name in ('experience/store.py','team/store.py','team/engine.py','workspace/web.py','team/web.py','team/__init__.py','comms/web.py','comms/engine.py','navigation/shell.py'):text=text.replace('Mahnoor Twin','The Twin').replace('Coordinator & personal assistant','Superhuman').replace('You are the The Twin','You are The Twin')
    if name=='repairs/__init__.py':text=once(text,'1.29.0','1.30.0')
    elif name=='hosted/boundary.py':text=once(text,"'version':'1.29.0'","'version':'1.30.0'")
    elif name=='navigation/web.py':text+='\n    from superhuman.foundation.web import install as install_foundation\n    install_foundation(app)\n'
    elif name=='navigation/shell.py':
        text=once(text,"('knowledge','/knowledge','Knowledge')","('knowledge','/storage','Storage')")
        text=once(text,"('/knowledge','/research-desk'","('/storage','/knowledge','/research-desk'")
        text=once(text,"('/settings','/memory'","('/system-baseline','/proactive','/agent-personalities','/settings','/memory'")
        text=once(text,"'knowledge':(('/knowledge','Knowledge home'),('/tools','Source files'),('/documents','Documents'),('/research-desk','Research'))","'knowledge':(('/storage','Storage home'),('/storage/search','Retrieval preview'),('/documents','Generated outputs'),('/research-desk','Research'))")
        text=once(text,"('/team-room?tab=feed','Activity'))","('/team-room?tab=feed','Activity'),('/agent-personalities','Personalities'))")
        text=once(text,"('/queue','Legacy jobs'))","('/queue','Legacy jobs'),('/system-baseline','System baseline'),('/proactive','Proactive checks'))")
    elif name=='experience/store.py':
        anchor="            db.execute(\"INSERT INTO ux_migrations VALUES('employee-names-128')\")"
        text=once(text,anchor,anchor+"\n        if not db.execute(\"SELECT 1 FROM ux_migrations WHERE id='twin-title-130'\").fetchone():\n            db.execute(\"UPDATE team_employees SET name='The Twin',version=version+1 WHERE id='twin'\")\n            db.execute(\"INSERT INTO ux_migrations VALUES('twin-title-130')\")")
    elif name=='experience/chat.py':
        text=once(text,'    return messages,trace',"    from superhuman.foundation.context import chat_augment\n    return chat_augment(claimed,messages,trace,path)")
        text=once(text,'def validate(claimed,trace,path=p.DEFAULT_DB):',"def validate(claimed,trace,path=p.DEFAULT_DB):\n    from superhuman.foundation.context import chat_validate\n    chat_validate(claimed,trace,path)")
    elif name=='team/work.py':
        text=once(text,"    return '\\nTEAM ASSIGNMENT (department boundaries and owner governance apply):\\n'+store.encode(body)","    from superhuman.foundation import personality,storage\n    body['storage']=storage.search(item['owner'],item['instruction'][:500],item['project_id'],store.effective(item,path)['sensitivity'],path)\n    return personality.instruction(item['owner'],path)+'\\nTEAM ASSIGNMENT (department boundaries and owner governance apply):\\n'+store.encode(body)")
    elif name=='team/engine.py':
        text=once(text,'    key={',"    from superhuman.foundation import proactive,personality\n    signals=proactive.twin_signals(path)\n    key={")
        text=once(text,"    signature=hashlib", "    key['proactive']=[(s['id'],s['episode'],s['state']) for s in signals]\n    signature=hashlib")
        text=once(text,'    return signature,body,actionable',"    body['proactive_signals']=signals\n    body['proactive_policy']='Signals request reassessment, not new authority. Do not duplicate tasks or infer missing facts. Notify-only signals are excluded.'\n    return signature,body,actionable or bool(signals)")
        text=once(text,'    try:\n        payload=',"    from superhuman.foundation.personality import instruction\n    system+=instruction('twin',path)\n    try:\n        payload=") if '    try:\n        payload=' in text else once(text,"    payload=store.encode(body)","    from superhuman.foundation.personality import instruction\n    system+=instruction('twin',path)\n    payload=store.encode(body)")
    elif name=='hosted/worker.py':
        text=once(text,"                    # Alternate bounded read cycles", "                    from superhuman.foundation.proactive import scan as proactive_scan\n                    proactive_scan(path)\n                    # Alternate bounded read cycles")
    elif name=='repairs/web.py':text=once(text,"data=checks.report();body=", "data=checks.report();body=") if False else once(text,"        body+='<h2>Inbox checks</h2>'","        body+='<p><a href=\"/system-baseline\">System baseline and activation evidence</a> · <a href=\"/proactive\">Proactive checks</a></p>'\n        body+='<h2>Inbox checks</h2>'")
    elif name=='repairs/context.py':
        text=once(text,"    names=[f['name'] for f in data['files']]", "    from superhuman.foundation.storage import rows as storage_rows\n    catalogued={r['filename'] for r in storage_rows() if r['scope']==scope and r['kind']=='document'}\n    names=[f['name'] for f in data['files'] if f['name'] not in catalogued]")
        text=once(text,'    return result',"    from superhuman.foundation.context import selection as storage_selection\n    return storage_selection(result,scope,title,details,max_reference_chars)")
    elif name=='agentic/tools.py':
        text=once(text,"    if name=='workspace.read':return outcome(local.extract(scope,args['filename']))", "    from superhuman.foundation import storage\n    if name=='workspace.read':return outcome(storage.read_for_run(run,args['filename'],path))\n    if name=='workspace.search':return outcome(storage.search_for_run(run,args['query'],path))\n    if name=='table.profile':storage.read_for_run(run,args['filename'],path)")
        text=once(text,"result=select_context(scope,args['query'],run['project']['details']);return outcome(result)","result=select_context(scope,args['query'],run['project']['details']);result['storage']=storage.run_search(run,args['query'],path);return outcome(result)")
        text=once(text,"    if tool in ('draft.create','research.web'):projects._text(data)","    if data.get('storage_receipt'):\n        from superhuman.foundation.storage import verify_receipt\n        verify_receipt(data['storage_receipt'],path)\n    if tool in ('draft.create','research.web'):projects._text(data)")
        text=once(text,"    if data.get('storage_receipt'):","    from superhuman.foundation.storage import verify_lookup\n    receipt=data.get('storage_lookup') or data.get('storage',{}).get('storage_lookup')\n    if receipt:verify_lookup(receipt,path)\n    if data.get('storage_receipt'):")
    elif name=='workspace/web.py':
        text=once(text,'Your coordinator and personal assistant.','Superhuman · Your coordinator and personal assistant.')
        text=once(text,"    body+='<p>'+link('/reviews','All decisions')", "    body+='<p>'+link('/system-baseline','System baseline')+' · '+link('/proactive','Proactive checks')+' · '+link('/storage','Storage')+'</p>'\n    body+='<p>'+link('/reviews','All decisions')")
    elif name=='comms/engine.py':
        text=once(text,"messages=[{'role':'system','content':POLICY}","messages=[{'role':'system','content':POLICY+__import__('superhuman.foundation.personality',fromlist=['instruction']).instruction('twin',path)}")
    ast.parse(text);return text
