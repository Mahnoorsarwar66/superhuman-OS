"""Exact-baseline integration over the delivered v1.26 release."""
import ast
from pathlib import Path
FILES=('hosted/worker.py','hosted/boundary.py','navigation/web.py','navigation/shell.py','repairs/__init__.py','repairs/web.py','repairs/checks.py','team/web.py','team/work.py','mail/store.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Integration source anchor missing or repeated: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.26 source: '+name+'; nothing overwritten')
    if name=='hosted/boundary.py':
        text=once(text,"'version':'1.26.0'","'version':'1.27.0'")
        anchor="        if not store.configured():return await reply(PlainTextResponse('Service setup required',status_code=503))"
        text=once(text,anchor,anchor+"\n        if scope['path']=='/hooks/whatsapp':\n            if names.count('x-hub-signature-256')>1:return await reply(PlainTextResponse('Invalid signature headers',status_code=400))\n            from superhuman.comms.providers import webhook\n            return await reply(await webhook(scope,receive,headers))")
    elif name=='hosted/worker.py':
        text=once(text,'        recover_team(path)','        recover_team(path)\n        from superhuman.comms.engine import recover as recover_comms\n        recover_comms(path)')
        text=once(text,'                        mail_result=mail_providers.run_sync(path)','                        mail_result=mail_providers.run_sync(path)\n                        if mail_result is None:\n                            from superhuman.comms.providers import read_tick as read_comms\n                            mail_result=read_comms(path)')
        text=once(text,'                                result=team_engine.tick(path,actual) if team_store.enabled(path) else review_departments(path,actual)','                                from superhuman.comms.engine import tick as assistant_tick\n                                result=assistant_tick(path,actual)\n                                if result is None:result=team_engine.tick(path,actual) if team_store.enabled(path) else review_departments(path,actual)')
        text=once(text,"result.get('team_cycle_id')))","result.get('team_cycle_id') or result.get('comms_cycle_id')))")
    elif name=='navigation/web.py':
        text+='\n    from superhuman.comms.web import install as install_comms\n    install_comms(app)\n'
    elif name=='navigation/shell.py':
        text=once(text,"('/talk','/team/twin')","('/talk','/team/twin','/assistant')")
        text=once(text,"('/team/twin','Mahnoor Twin'))","('/team/twin','Mahnoor Twin'),('/assistant','Personal assistant'))")
    elif name=='repairs/__init__.py':text=once(text,'1.26.0','1.27.0')
    elif name=='repairs/web.py':
        text=once(text,'    out.extend(team_attention())','    out.extend(team_attention())\n    from superhuman.comms.web import attention as assistant_attention\n    out.extend(assistant_attention())')
    elif name=='repairs/checks.py':
        text=once(text,"    result['live_verification']=","    from superhuman.comms import store as comms\n    result['communications']={'enabled':bool(comms.settings()['enabled']),'channels':[{k:a[k] for k in ('id','kind','connected','enabled','ai_enabled','last_sync','last_error')} for a in comms.channels()],'run_states':dict(Counter(r['status'] for r in comms.runs())),'unacknowledged_alerts':sum(a['state']=='new' for a in comms.alerts()),'external_sending':False}\n    result['live_verification']=")
    elif name=='mail/store.py':
        anchor="        any_credentials=db.execute('SELECT 1 FROM mail_accounts WHERE credential IS NOT NULL LIMIT 1').fetchone()"
        text=once(text,anchor,anchor+"\n        if not any_credentials and db.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='comms_channels'\").fetchone():\n            any_credentials=db.execute('SELECT 1 FROM comms_channels WHERE credential IS NOT NULL LIMIT 1').fetchone()")
    elif name=='team/web.py':
        text=once(text,'<button name="action" value="cancel">Cancel</button>', '<button name="action" value="cancel">Cancel</button> <button name="action" value="restrict_private_tools">Remove public-web tools from private run</button>')
        text=once(text,'External communications belong to v1.27.','Communications and scheduled briefings are in the Personal assistant workspace.')
        text=once(text,'External channel intake and scheduled briefings arrive in v1.27.','Use Personal assistant for connected-channel intake, local reply drafts and scheduled briefings.')
        text=once(text,'        if cfg[\'hold\']:body+=','        from superhuman.comms.web import twin_panel\n        body+=twin_panel()\n        if cfg[\'hold\']:body+=')
    elif name=='team/work.py':
        text=once(text,"        if not set(run['allowed_tools'])<=set(json.loads(employee['allowed_tools'])):return False,'Employee tool permission was withdrawn'","        if not set(run['allowed_tools'])<=set(json.loads(employee['allowed_tools'])):return False,'Employee tool permission was withdrawn'\n        if classification['sensitivity'] in ('confidential','restricted') and any(tools.REGISTRY[n].permission=='read_web' for n in run['allowed_tools'] if n in tools.REGISTRY):return False,'Private assignment has public-web tools; inspect permissions before continuation'")
        text=once(text,"    if action=='approve_start':", "    if action=='restrict_private_tools':\n        from superhuman.comms.engine import restrict_private_tools\n        restrict_private_tools(ident,expected,note,path);return\n    if action=='approve_start':")
        text=once(text,"    allowed=json.loads(employee['allowed_tools'])","    allowed=json.loads(employee['allowed_tools'])\n    if store.effective(item,path)['sensitivity'] in ('confidential','restricted'):allowed=[n for n in allowed if tools.REGISTRY[n].permission!='read_web']")
    ast.parse(text);return text
