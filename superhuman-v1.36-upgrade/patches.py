"""Recognise exact v1.35 integration source; preserve customized CLI/orchestrator."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','foundation/context.py','dialogue/engine.py','dialogue/store.py','hosted/worker.py','workspace/web.py','foundation/__init__.py','repairs/__init__.py','hosted/boundary.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated v1.36 anchor: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.35 source: '+name+'; nothing overwritten')
    if name in ('foundation/__init__.py','repairs/__init__.py','hosted/boundary.py'):text=once(text,'1.35.0','1.36.0')
    elif name=='navigation/shell.py':
        text=once(text,"('team','/team-room','Team')","('team','/team-hub','Team')")
        text=once(text,'</script></head><body>','</script><link rel="stylesheet" href="/assets/teamhub.css?v=136"><script src="/assets/teamhub.js?v=136" defer></script></head><body>')
    elif name=='navigation/web.py':text+='\n    from superhuman.teamhub.web import install as install_teamhub\n    install_teamhub(app)\n'
    elif name=='foundation/context.py':
        text=once(text,"    data=storage.search(r['employee'],query,r['project_id'],maximum,path)","    from superhuman.teamhub.context import shared_storage\n    data=shared_storage(claimed,storage.search(r['employee'],query,r['project_id'],maximum,path),path)")
        text=once(text,"    current=storage.search(info['employee'],info['query'],info['project_id'],info['maximum'],path)","    from superhuman.teamhub.context import shared_storage\n    current=shared_storage(claimed,storage.search(info['employee'],info['query'],info['project_id'],info['maximum'],path),path)")
        text=once(text,'    return messages,trace\n','    from superhuman.teamhub.context import augment\n    return augment(claimed,messages,trace,path)\n')
        text+='\n    from superhuman.teamhub.context import validate\n    validate(claimed,trace,path)\n'
    elif name=='dialogue/engine.py':
        text=once(text,"        response_schema = briefing_engine.SCHEMA if report_mode else SCHEMA","        from superhuman.teamhub.engine import schema as hub_schema\n        response_schema = briefing_engine.SCHEMA if report_mode else hub_schema(trace,SCHEMA)")
        text=once(text,"        parsed = briefing_engine.parse(raw,claimed['scope'],trace) if report_mode else parse(raw, claimed['scope'])","        from superhuman.teamhub.engine import parse as hub_parse\n        parsed = briefing_engine.parse(raw,claimed['scope'],trace) if report_mode else hub_parse(raw, claimed['scope'],trace,path)")
    elif name=='dialogue/store.py':
        anchor="        if db.execute(\"SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('queued','running')\", (thread_id,)).fetchone():"
        text=once(text,anchor,"        from superhuman.departments.store import tables\n        if 'hub_rooms' in tables(db) and db.execute('SELECT 1 FROM hub_rooms WHERE id=? AND archived=1',(thread_id,)).fetchone():raise ValueError('Restore this archived conversation before sending')\n"+anchor)
    elif name=='hosted/worker.py':
        text=once(text,'                    from superhuman.foundation.proactive import scan as proactive_scan','                    from superhuman.teamhub.engine import advance as advance_team_discussions\n                    advance_team_discussions(path)\n                    from superhuman.foundation.proactive import scan as proactive_scan')
    elif name=='workspace/web.py':
        text=once(text,'def transcript(ident,before=0):\n','def transcript(ident,before=0):\n    from superhuman.teamhub.web import thread_actions\n')
        text=once(text,"rich(t['user_text'])+'</article><article class=\"card reply\"><small>'","rich(t['user_text'])+thread_actions(ident,t)+'</article><article class=\"card reply\"><small>'")
        text=once(text,"body+='<article class=\"card owner\"><small>You · '","body+='<article id=\"turn-'+t['id']+'\" class=\"card owner\"><small>You · '")
    ast.parse(text);return text
