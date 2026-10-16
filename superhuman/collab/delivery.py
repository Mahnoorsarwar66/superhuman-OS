"""Scoped delivery policies and checks, without extra model requests."""
import json
import re
from .reliability import validate_final

__version__='1.8.1'

REVIEW_SCHEMA={'type':'object','properties':{'issues':{'type':'array','items':{
    'type':'object','properties':{
        'category':{'type':'string','enum':['requirements','unsupported_claim','scope','format','length']},
        'requirement':{'type':'string'},'evidence':{'type':'string'},'correction':{'type':'string'}},
    'required':['category','requirement','evidence','correction'],'additionalProperties':False}}},
    'required':['issues'],'additionalProperties':False}


def current_brief(title,details=''):
    # The project runner wraps the actual task with identity and source context.
    # Classify only the task, never a cited email or another task in the objective.
    text=details
    for marker in ('USER-CURATED IDENTITY','TASK-SELECTED REFERENCES','DEPENDENCY REFERENCES','ATTACHED LOCAL SOURCE TEXT'):
        text=text.split(marker,1)[0]
    task=re.search(r'(?m)^TASK:\s*(.*)',text)
    if task:text=text[task.start()+len('TASK:'):].strip()
    return title+'\n'+text


def classify(title,details=''):
    text=current_brief(title,details).lower()
    if re.search(r'\b(consolidated project deliverable|consolidate (?:all )?dependency|consolidate (?:the )?drafts)\b',text):return 'consolidation'
    if re.search(r'\b(personal letter|love letter|message to (?:my )?(?:husband|wife|partner)|letter to (?:my )?(?:husband|wife|partner))\b',text):return 'personal_writing'
    # A message containing an agenda is still a message when explicitly requested.
    if re.search(r'\b(?:write|draft|prepare|compose)\s+(?:a |an |the )?(?:short |brief )?(?:email|linkedin message|outreach message|cover letter)\b',text) or re.search(r'\b(email|linkedin message|outreach message|cover letter)\b',title.lower()):return 'outreach'
    if re.search(r'\b(blank|fillable)\b.{0,70}\b(record|form|template|checklist|worksheet|log)\b',text,re.S) or re.search(r'\b(?:record|form|template|checklist|worksheet|log)\b.{0,30}\b(?:blank|fillable)\b',text,re.S):return 'template'
    if re.search(r'\bagenda\b',text):return 'agenda'
    if re.search(r'\b(statement of purpose|motivation letter|sop|admissions essay)\b',text):return 'admissions_writing'
    if re.search(r'\b(email|outreach|cover letter|linkedin|message|discovery|interview guide)\b',text):return 'outreach'
    if re.search(r'\b(prioriti[sz]e|priorities|trade.?offs?|schedule|allocation|decision|decide|competing|hours)\b',text):return 'decision'
    if re.search(r'\b(research|verify|sources|licen[cs]ing|compare evidence)\b',text):return 'research'
    if re.search(r'\b(write|draft|guide|proposal|article|speech|copy|statement)\b',text):return 'writing'
    return 'general'


def scope_rules(rules,family):
    selected=[];excluded=[]
    for rule in rules:
        label=rule.get('label','');reason=None
        if rule.get('source') not in ('user_confirmed','user_revision'):
            reason='Rule is not a confirmed preference'
        explicit=rule.get('task_types')
        if explicit is not None and (not isinstance(explicit,list) or family not in explicit):
            reason='Explicit task-type scope does not match'
        lower=label.lower()
        if reason is None and 'personal' in lower and ('outreach' in lower or 'calibration' in lower) and family!='personal_writing':
            reason='Personal communication calibration excluded from this document type'
        if reason is None and 'personal' not in lower and 'outreach' in lower and 'calibration' in lower and family!='outreach':
            reason='Outreach calibration excluded from this document type'
        if reason:
            excluded.append({'id':rule.get('id'),'kind':'rule','label':label,'reason':reason,'source':rule.get('source')})
        else:selected.append(rule)
    return selected,excluded


def policy(family,req):
    text=('DELIVERY POLICY v1.8.1: The current task and requested document type govern format. '
          'Apply general voice preferences only where they fit that format. '
          'A sample opening, introduction or audience convention is not mandatory across genres. '
          'Produce the usable artifact now; do not replace it with questions, promises of future work, '
          'a personal introduction, or a commentary about how it was produced. '
          'Leave unspecified details unspecified. Reviewer suggestions cannot create new user requirements. '
          'Preserve substantive requested content; never silently truncate to satisfy a limit.\n')
    if family=='template':
        text+=('DOCUMENT TYPE: blank form/template. Start with the form title and fields. '
               'Use concise labels and blank placeholders. Empty fields are intentional, not missing facts '
               'requiring verification. Do not prepend an outreach pitch or question-led introduction.\n')
    elif family=='agenda':
        text+=('DOCUMENT TYPE: agenda. Start with its title/purpose and agenda items. '
               'Do not invent a speaker biography, meeting length or timings. '
               'Include those only when supplied or explicitly requested as suggestions.\n')
    elif family=='consolidation':
        text+=('DOCUMENT TYPE: consolidation. Preserve dependency corrections and the requested artifacts. '
               'Do not expand templates into an advisory report, reopen resolved choices, '
               'invent timings or add new deliverables. Keep provenance in metadata when possible.\n')
    if req.get('max_words'):
        target=max(1,int(req['max_words']*.8))
        text+=f"WORD BUDGET: combined deliverable and verification notes <= {req['max_words']} words. Aim near {target} words, preserving every requested topic. The program checks the actual count.\n"
    return text


def parse_review(raw,draft,allowed_requirements=None):
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!={'issues'} or not isinstance(value['issues'],list) or len(value['issues'])>10:
        raise ValueError('Invalid reviewer structure')
    allowed={'requirements','unsupported_claim','scope','format','length'}
    for issue in value['issues']:
        if not isinstance(issue,dict) or set(issue)!={'category','requirement','evidence','correction'}:
            raise ValueError('Invalid reviewer issue')
        if issue['category'] not in allowed or any(not isinstance(issue[k],str) or len(issue[k])>1200 for k in ('requirement','evidence','correction')):
            raise ValueError('Invalid reviewer issue value')
        if not issue['requirement'].strip() or not issue['correction'].strip():raise ValueError('Reviewer must identify a requirement and correction')
        if allowed_requirements is not None and issue['requirement'].casefold() not in allowed_requirements.casefold():
            raise ValueError('Reviewer invented a requirement instead of quoting the current task contract')
        if issue['evidence'] and issue['evidence'].casefold() not in draft.casefold():
            raise ValueError('Reviewer evidence does not occur in the draft')
    return value


def assess(text,req,forbid,family,brief):
    report=validate_final(text,req,forbid)
    if not text.strip():report['errors'].append('Empty deliverable')
    if family in ('template','agenda','consolidation'):
        explicit=current_brief('',brief).lower()
        if not re.search(r'\b(?:include|add|use|write|start with)\b.{0,35}\b(?:introduction|introduce|question-led opening|personal opening)\b',explicit):
            start='\n'.join(text.strip().splitlines()[:7])
            preface=re.search(r'(?im)^\s*question-led opening\s*$',start)
            personal_intro=re.search(r"(?m)^\s*(?:I am|I[’']m)\s+[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2}[.!](?:\s|$)",start)
            if preface or personal_intro:
                report['errors'].append('Unrequested personal or question-led preface for this document type')
    report['passes']=not report['errors']
    report['document_type']=family
    report['scope']='Mechanical checks and structured model review; not proof of factual accuracy or complete semantic compliance'
    return report


def final_settings(plan,normalized):
    mode=plan.get('final_mode','auto')
    if mode not in ('auto','preserve','synthesize'):raise ValueError('final_mode must be auto, preserve or synthesize')
    provided=plan.get('final_checks')
    if provided is not None:
        # Reuse the existing plan validator for the supported check contract.
        from superhuman.projects.engine import validate
        probe={'tasks':[{'id':'check_probe','kind':'collab','title':'Check contract','checks':provided}]}
        # The recursive call has no final_checks, so it terminates immediately.
        validate(probe)
        checks=dict(provided)
    else:
        limits=[t['checks'].get('max_words') for t in normalized['tasks'][:-1]]
        checks={}
        if limits and all(limits) and sum(limits)+40<=5000:
            checks={'max_words':sum(limits)+40}
    normalized['tasks'][-1]['checks']=checks
    normalized['final_mode']=mode
    normalized['final_checks_source']='explicit' if provided is not None else 'component_limits' if checks else 'none'
    return normalized


def bound_final(normalized,objective,details,plan):
    # A derived component ceiling must not loosen the user's overall ceiling.
    from .reliability import requirements_for
    if 'final_checks' not in plan:
        inferred=requirements_for(objective+'\n'+details).get('max_words')
        if inferred:
            checks=normalized['tasks'][-1]['checks']
            checks['max_words']=min(inferred,checks.get('max_words',inferred))
            normalized['final_checks_source']='objective_and_component_limits'
    return normalized


if __name__=='__main__':
    print(json.dumps({'version':__version__, 'api_calls':0,
        'examples':{'blank_record':classify('Blank university discovery record'),
                    'agenda':classify('University pilot discovery agenda'),
                    'email':classify('Write a university outreach email'),
                    'consolidation':classify('Consolidated project deliverable')}},indent=2))
