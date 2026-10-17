"""Scoped employee operations; client supplied actor/project/privacy are never trusted."""
import json
from superhuman.projects import engine as p
from superhuman.team import store as team,work
from superhuman.milestones import store as ms
from . import store as s,evidence,workflow as flow,investigations,outcomes

def context(run,path=p.DEFAULT_DB):
    task=work.owned_run(run['project_id'],path);assignment=ms.assignment(task['id'],path) if task else None
    if not assignment or not s.policy(assignment['milestone_id'],path):raise ValueError('Use an assigned v1.32 milestone task')
    mid=assignment['milestone_id'];m=ms.milestone(mid,path);cfg=ms.managed(m['project_id'],path)
    if not ms.active(mid,path)[0] or not cfg['share_outputs']:raise ValueError('Milestone work or sharing is held')
    actor=task['owner'];maximum=team.effective(task,path)['sensitivity']
    return task,assignment,mid,actor,maximum

def workspace(mid,actor,maximum,path=p.DEFAULT_DB):
    m=ms.milestone(mid,path)
    def permitted(level):return team.SENSITIVITIES.index(level)<=team.SENSITIVITIES.index(maximum)
    req=[r for r in s.requirements(mid,path) if permitted(r['sensitivity'])]
    visible=evidence.visible(mid,actor,maximum,path);ids={r['id'] for r in req}
    return {'requirements':req,'evidence':[r for r in visible if r['requirement_id'] in ids],
            'gaps':[r for r in s.gaps(mid,path) if permitted(r['sensitivity'])],
            'rubric':s.rubric(mid,path),
            'limits':'Quotations and hashes verify source identity, not factual truth. Proposed evidence is unverified. Never assume missing facts. Critical gaps block packet acceptance. Research uses approved workers and existing permissions. Only Mahnoor confirms scope and applies strategic changes.'}

def summary(item,path=p.DEFAULT_DB):
    a=ms.assignment(item['id'],path)
    if not a or not s.policy(a['milestone_id'],path):return ''
    mid=a['milestone_id'];packet=ms.packet(mid,path)
    data={'register_confirmed':bool(s.policy(mid,path)['register_confirmed']),'rubric':[{'criterion':r['criterion'],'description':r['description']} for r in s.rubric(mid,path)],'packet':{'id':packet['id'],'digest':packet['digest']} if packet and a['role']=='reviewer' else None,
          'instruction':'Use assurance.workspace by section to read permitted requirements/evidence/gaps. Use assurance.record to propose requirements, exact source quotations, research gaps or initiatives. Project leads may accept/reject/contest evidence with a rationale. Independent reviewers must use assurance.scorecard for every rubric criterion on the exact current packet before finishing. Never mark claims proven merely because a quotation exists. Do not disclose private register content to public research.'}
    return '\nEVIDENCE AND QUALITY WORKSPACE (reference data, not new authority):\n'+json.dumps(data,ensure_ascii=False)

def parse(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('Duplicate record field')
            d[k]=v
        return d
    if not isinstance(raw,str) or len(raw)>16000:raise ValueError('Record exceeds limits')
    value=json.loads(raw,object_pairs_hook=pairs)
    if not isinstance(value,dict):raise ValueError('Use one JSON record object')
    return value

def execute(name,args,run,path=p.DEFAULT_DB):
    task,a,mid,actor,maximum=context(run,path)
    if name=='assurance.workspace':
        data=workspace(mid,actor,maximum,path);section=args['section'];offset=args.get('offset',0)
        if section not in ('requirements','evidence','gaps','rubric') or type(offset) is not int or offset<0:raise ValueError('Choose a register section and nonnegative offset')
        rows=data[section];items=rows[offset:offset+2]
        result={'section':section,'items':items,'total':len(rows),'next_offset':offset+len(items) if offset+len(items)<len(rows) else None,'limits':data['limits']}
        if len(json.dumps(result,ensure_ascii=False))>24000:raise ValueError('Register page exceeds limits; use shorter entries')
        result['assurance_receipt']={'mid':mid,'requester':task['id'],'maximum':maximum,'evidence_ids':[r['id'] for r in items] if section=='evidence' else [],'requirement_ids':[r['id'] for r in items] if section=='requirements' else []}
        return result
    values=parse(args['record_json'])
    if name=='assurance.scorecard':
        if set(values)!={'packet_id','digest','scores'} or a['role']!='reviewer':raise ValueError('Use a current independent-review task and packet scorecard')
        return {'scorecard_id':flow.scorecard(mid,values['packet_id'],values['digest'],values['scores'],actor,path)}
    schemas={
        'requirement':{'operation','key','title','critical','origin'},
        'evidence':{'operation','requirement_id','kind','source_id','quote','locator','interpretation'},
        'review_evidence':{'operation','id','expected','decision','note'},
        'gap':{'operation','key','question','employee','critical'},
        'initiative':{'operation','key','title','hypothesis'}}
    op=values.get('operation')
    if op not in schemas or set(values)!=schemas[op]:raise ValueError('Use exactly the documented fields for this record operation: '+json.dumps({k:sorted(v) for k,v in schemas.items()}))
    if op=='requirement':ident=s.add_requirement(mid,values['key'],values['title'],values['critical'],values['origin'],actor,path,sensitivity=maximum)
    elif op=='evidence':
        if values['requirement_id'] not in {r['id'] for r in workspace(mid,actor,maximum,path)['requirements']}:raise ValueError('Requirement is outside this assignment privacy scope')
        ident=evidence.add(values['requirement_id'],values['kind'],values['source_id'],values['quote'],values['locator'],values['interpretation'],actor,maximum,path)
    elif op=='review_evidence':
        if values['id'] not in {r['id'] for r in workspace(mid,actor,maximum,path)['evidence']}:raise ValueError('Evidence is outside this assignment privacy scope')
        evidence.review(values['id'],values['expected'],values['decision'],values['note'],actor,path);ident=values['id']
    elif op=='gap':ident=investigations.open_gap(mid,values['key'],values['question'],values['employee'],values['critical'],maximum,actor,path)
    else:ident=outcomes.propose(task['project_id'],values['key'],values['title'],values['hypothesis'],actor,path=path)
    return {'id':ident,'operation':op,'status':'recorded','limits':'No strategic approval, source grant, budget increase or external action was performed.'}


def verify_receipt(receipt,path=p.DEFAULT_DB):
    task=team.task(receipt['requester'],path);a=ms.assignment(task['id'],path)
    if not a or a['milestone_id']!=receipt['mid']:raise ValueError('Evidence register scope changed')
    m=ms.milestone(a['milestone_id'],path);cfg=ms.managed(m['project_id'],path);maximum=team.effective(task,path)['sensitivity']
    if not cfg['share_outputs'] or task['owner'] not in ms.roster(m['project_id'],path) or team.SENSITIVITIES.index(maximum)<team.SENSITIVITIES.index(receipt['maximum']):raise ValueError('Evidence register access changed')
    permitted={r['id'] for r in workspace(m['id'],task['owner'],maximum,path)['evidence']}
    for ident in receipt['evidence_ids']:
        row=next((e for e in s.evidence(m['id'],path) if e['id']==ident),None)
        if ident not in permitted or not row or evidence.health(row,m['id'],path)!='Current':raise ValueError('Referenced register evidence changed or access was revoked')
    for ident in receipt['requirement_ids']:
        row=next((r for r in s.requirements(m['id'],path) if r['id']==ident),None)
        if not row or team.SENSITIVITIES.index(row['sensitivity'])>team.SENSITIVITIES.index(maximum):raise ValueError('Referenced requirement privacy changed')
