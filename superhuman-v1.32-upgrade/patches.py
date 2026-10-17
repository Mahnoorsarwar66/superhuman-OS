"""Exact v1.31 integration. Production CLI/orchestrator are not modified."""
import ast
from pathlib import Path
FILES=('milestones/store.py','milestones/workflow.py','milestones/engine.py','milestones/web.py','agentic/tools.py','foundation/__init__.py','repairs/__init__.py','hosted/boundary.py','workspace/model.py','agentic/engine.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Missing or repeated integration anchor: '+old[:100])
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text()):raise ValueError('Unrecognised v1.31 source: '+name+'; nothing overwritten')
    if name in ('foundation/__init__.py','repairs/__init__.py','hosted/boundary.py'):text=once(text,'1.31.0','1.32.0')
    elif name=='agentic/engine.py':
        text=once(text,"in ('storage.pdf_pages','milestone.read_output')","in ('storage.pdf_pages','milestone.read_output','assurance.workspace')")
    elif name=='workspace/model.py':
        text=once(text,'    unique={}',"    from superhuman.assurance.outcomes import attention as assurance_attention\n    out.extend(assurance_attention(path))\n    unique={}")
    elif name=='milestones/store.py':
        text=once(text,'def seed_endorsement(path=p.DEFAULT_DB):','def _seed_endorsement_v131(path=p.DEFAULT_DB):')
        text+='\n\ndef seed_endorsement(path=p.DEFAULT_DB):\n    pid=_seed_endorsement_v131(path)\n    from superhuman.assurance.store import seed\n    for row in listing(pid,path):seed(row["id"],path)\n    return pid\n'
        text=once(text,"    return ident\n\ndef _seed_endorsement_v131", "    from superhuman.assurance.store import seed\n    seed(ident,path)\n    return ident\n\ndef _seed_endorsement_v131")
        text=once(text,"def active(mid,path=p.DEFAULT_DB):\n", "def active(mid,path=p.DEFAULT_DB):\n    from superhuman.assurance.workflow import execution_block\n    blocked=execution_block(mid,path)\n    if blocked:return False,blocked\n")
        text=once(text,"    if a['role']=='lead':\n        if 'twin'", "    if a['role']=='lead':\n        from superhuman.assurance.store import gaps\n        if any(g['critical'] and g['state']!='resolved' for g in gaps(m['id'],path)):return False,'Resolve critical investigations before integration execution'\n        if 'twin'")
        text=once(text,"def start(mid,expected,path=p.DEFAULT_DB):\n", "def start(mid,expected,path=p.DEFAULT_DB):\n    from superhuman.assurance.workflow import execution_block\n    if execution_block(mid,path):raise ValueError(execution_block(mid,path))\n")
    elif name=='milestones/workflow.py':
        text=once(text,"    a=s.assignment(tid,path)\n    if not a:raise ValueError('Not a milestone assignment')", "    a=s.assignment(tid,path)\n    if approve:\n        from superhuman.assurance.workflow import check_reviewer\n        check_reviewer(tid,path)\n    if not a:raise ValueError('Not a milestone assignment')")
        text=once(text,"\ndef submit(mid,expected,path=p.DEFAULT_DB,actor=None):", "    from superhuman.assurance.investigations import accepted_task\n    accepted_task(tid,approve,note,actor,path)\n\ndef submit(mid,expected,path=p.DEFAULT_DB,actor=None):\n    from superhuman.assurance.workflow import gate\n    gate(mid,path=path)")
        text=once(text,'    export_packet(mid,path)\n    return ident','    from superhuman.assurance.workflow import freeze\n    freeze(mid,path)\n    export_packet(mid,path)\n    return ident')
        text=once(text,"    if decision=='accept' and not m['criteria_confirmed']:","    if decision=='accept':\n        from superhuman.assurance.workflow import quality_gate\n        quality_gate(mid,twin=True,path=path)\n    if decision=='accept' and not m['criteria_confirmed']:")
        text=once(text,'def approve(mid,expected,packet_id,note,path=p.DEFAULT_DB):','def approve(mid,expected,packet_id,note,path=p.DEFAULT_DB):\n    from superhuman.assurance.workflow import quality_gate\n    quality_gate(mid,twin=True,path=path)')
        text=once(text,"    return '\\nMILESTONE WORKSPACE (reference data and delegated scope):\\n'+json.dumps(body,ensure_ascii=False)","    from superhuman.assurance.tools import summary\n    return '\\nMILESTONE WORKSPACE (reference data and delegated scope):\\n'+json.dumps(body,ensure_ascii=False)+summary(item,path)")
    elif name=='milestones/engine.py':
        text=once(text,"set(data)!=set(SCHEMA['required']) or any(not isinstance(v,str) for v in data.values())", "set(data) not in (set(SCHEMA['required']),set(SCHEMA['required'])|{'scores'}) or any(not isinstance(v,str) for k,v in data.items() if k!='scores')")
        text=once(text,"    key['outputs']=", "    from superhuman.assurance.workflow import fingerprint\n    key['assurance']=fingerprint(mid,path)\n    key['outputs']=")
        text=once(text,'def tick(path=p.DEFAULT_DB,client=None):','def tick(path=p.DEFAULT_DB,client=None):\n    from superhuman.assurance.workflow import maintenance,dispatch_one\n    maintenance(path)')
        text=once(text,'    work.refresh(path)\n    for m', '    work.refresh(path)\n    assigned_gap=dispatch_one(path)\n    if assigned_gap:return assigned_gap\n    for m')
        text=once(text,"            body['storage']=storage.search(actor,query,m['project_id'],ceiling,path)","            body['storage']=storage.search(actor,query,m['project_id'],ceiling,path)\n            from superhuman.assurance.engine import prepare\n            prepare(m['id'],body,actor,kind,target,ceiling,path)")
        text=once(text,"'schema':SCHEMA", "'schema':decision_schema(m['id'],kind,path)")
        text=once(text,"            action=decision['action']", "            action=decision['action']\n            if kind=='review' and action in ('accept','revise'):\n                from superhuman.assurance.engine import save_twin_scores\n                save_twin_scores(m['id'],decision,path)")
        text+='\n\ndef decision_schema(mid,kind,path):\n    from superhuman.assurance.engine import schema\n    return schema(mid,kind,SCHEMA,path)\n'
    elif name=='milestones/web.py':
        text=once(text,"    body+='<h2>Milestones</h2>'", "    body+='<p>'+link('/project-hub/'+pid+'/outcomes','Initiatives & outcome review')+'</p>'\n    from superhuman.assurance.web import impact_summary\n    body+=impact_summary(pid)\n    body+='<h2>Milestones</h2>'")
        text=once(text,"    return render(body+'</details>','Milestone '+str(m['ordinal']))", "    from superhuman.assurance.web import milestone_summary\n    body+='</details>'\n    body+=milestone_summary(mid)\n    return render(body,'Milestone '+str(m['ordinal']))")
        text=once(text,'def install(app):','def install(app):\n    from superhuman.assurance.web import install as install_assurance\n    install_assurance(app)')
    elif name=='agentic/tools.py':
        text=once(text," spec('milestone.read_output'", " spec('assurance.workspace','Read permitted requirement/evidence/gap/rubric pages; section and offset, two records per page.','read_workspace',{'section':str,'offset':int},('section',)),\n spec('assurance.record','Record JSON operation: requirement(key,title,critical,origin); evidence(requirement_id,kind,source_id,quote,locator,interpretation); review_evidence(id,expected,decision,note); gap(key,question,employee,critical); initiative(key,title,hypothesis). Include operation. No permission or strategic approval changes.','team_collaboration',{'record_json':str},('record_json',),mutates=True),\n spec('assurance.scorecard','Independent reviewer: JSON packet_id,digest,scores array with criterion,verdict(pass/revise/fail),rationale for every criterion.','team_collaboration',{'record_json':str},('record_json',),mutates=True),\n spec('milestone.read_output'")
        text=once(text,"    data=json.loads(action['result_json'] or '{}');tool=action['tool'];args=json.loads(action['arguments_json'])","    data=json.loads(action['result_json'] or '{}');tool=action['tool'];args=json.loads(action['arguments_json'])\n    if data.get('assurance_receipt'):\n        from superhuman.assurance.tools import verify_receipt\n        verify_receipt(data['assurance_receipt'],path)")
        text=once(text,"    if name=='milestone.read_output':", "    if name.startswith('assurance.'):\n        from superhuman.assurance.tools import execute as execute_assurance\n        return outcome(execute_assurance(name,args,run,path))\n    if name=='milestone.read_output':")
    ast.parse(text);return text
