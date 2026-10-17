"""Quality decisions stay in the existing metered lead/Twin controller."""
import copy,json
from superhuman.projects import engine as p
from superhuman.milestones import store as ms
from . import store as s,workflow as flow,tools

def schema(mid,kind,original,path=p.DEFAULT_DB):
    result=copy.deepcopy(original)
    if kind=='review' and s.policy(mid,path):
        result['properties']['scores']={'type':'array','items':{'type':'object','properties':{'criterion':{'type':'string'},'verdict':{'type':'string','enum':['pass','revise','fail']},'rationale':{'type':'string'}},'required':['criterion','verdict','rationale'],'additionalProperties':False}}
        result['required'].append('scores')
    return result

def prepare(mid,body,actor,kind,target,ceiling,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return
    body['evidence_quality']=tools.workspace(mid,actor,ceiling,path)
    body['evidence_quality']['register_confirmed']=bool(s.policy(mid,path)['register_confirmed'])
    body['quality_instruction']='Assess every material claim against current evidence and the full rubric. Proposed/contested claims are not verified facts. Do not substitute length or generic advice for context. For review mode return scores for every rubric criterion with verdict pass/revise/fail and a concrete rationale; accepting requires all pass. A specialist critique must have a complete scorecard before lead acceptance. A failing packet verdict is a valid critique; revise integration using its findings. Twin acceptance requires passing current specialist scorecards. Strategic approval remains Mahnoor’s.'
    if kind=='review':
        packet=ms.packet(mid,path);body['specialist_scorecards']=[flow.scores(mid,packet['id'],employee,path) for employee in json.loads(ms.milestone(mid,path)['reviewers'])]
    try:
        if kind=='submit':flow.gate(mid,path=path)
        if kind=='review':flow.quality_gate(mid,path=path)
        if kind=='contribution' and target:flow.check_reviewer(target['task_id'],path)
    except ValueError as exc:
        body['quality_blocker']=str(exc);body['allowed_actions']=[v for v in body['allowed_actions'] if v not in ('accept','submit')]

def save_twin_scores(mid,decision,path=p.DEFAULT_DB):
    if not s.policy(mid,path):return
    packet=ms.packet(mid,path)
    if 'scores' not in decision:raise ValueError('The Twin must provide a full scorecard before accepting this packet')
    flow.scorecard(mid,packet['id'],packet['digest'],decision['scores'],'twin',path)
