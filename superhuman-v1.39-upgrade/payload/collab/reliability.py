"""Explicit task requirements and deterministic final-output checks."""
import json
import re

FINAL_SCHEMA={'type':'object','properties':{
    'deliverable':{'type':'string'},
    'verification_needed':{'type':'array','items':{'type':'string'}}},
    'required':['deliverable','verification_needed'],'additionalProperties':False}

def requirements_for(details,provided=None):
    req=dict(provided or {})
    if not req.get('max_words'):
        # Only the current brief, not identity or dependency source excerpts.
        current=details.split('USER-CURATED IDENTITY',1)[0].split('DEPENDENCY REFERENCES',1)[0]
        limits=re.findall(r'(?:under|fewer than|less than|at most|maximum(?: of)?|max|no more than)\s+(\d+)\s+words',current,re.I)
        if limits:req['max_words']=min(int(x) for x in limits)
    req.setdefault('required_terms',[])
    if req.get('max_words') and (type(req['max_words']) is not int or not 1<=req['max_words']<=5000):
        raise ValueError('Invalid word limit')
    if not isinstance(req['required_terms'],list) or any(not isinstance(x,str) for x in req['required_terms']):
        raise ValueError('Invalid required terms')
    return req

def confirmed_preferences(project):
    try:
        from superhuman.identity.store import list_records
    except ImportError:return '',False
    rules=[r for r in list_records('rules',active_only=True) if r.get('project') in ('global',project) and r.get('source') in ('user_confirmed','user_revision')]
    text='\n'.join(r['label']+': '+r['content'] for r in rules)
    forbid=any(r['label']=='Prose punctuation preference' for r in rules)
    return text,forbid

def contract(req,forbid):
    limit='No explicit word ceiling.'
    if req.get('max_words'):limit=f"Combined deliverable and verification notes must not exceed {req['max_words']} words. Aim below the ceiling to leave room for necessary notes."
    return ('TASK REQUIREMENTS: '+json.dumps(req)+'\n'+limit+'\n'+
        ('No spaced dash clause separators. Use sentences, commas or semicolons.\n' if forbid else '')+
        'Use the supplied facts; do not invent identities, contact details, capabilities, availability, metrics, commitments or task requirements. '
        'Preserve every requested topic during review. Proposed additions must remain suggestions, not facts. '
        'Do not add reviewer instructions to the deliverable. Mention verification only for genuine unresolved facts, not facts explicitly supplied in the task.')

def parse_final(text):
    try:value=json.loads(text)
    except json.JSONDecodeError as error:raise ValueError('Final editor returned incomplete/invalid JSON; no automatic retry') from error
    if not isinstance(value,dict) or set(value)!={'deliverable','verification_needed'}:
        raise ValueError('Final editor response does not match required fields')
    if not isinstance(value['deliverable'],str) or not value['deliverable'].strip():raise ValueError('Empty final deliverable')
    if not isinstance(value['verification_needed'],list) or any(not isinstance(x,str) for x in value['verification_needed']):
        raise ValueError('Invalid verification notes')
    return value

def render_final(value,forbid=False):
    text=value['deliverable'].strip()
    notes=[x.strip() for x in value['verification_needed'] if x.strip()]
    if notes:text+='\n\nVerification needed:\n'+'\n'.join('- '+x for x in notes)
    changes=[]
    if forbid:
        # Only mechanical punctuation correction; no semantic shortening.
        def punctuation(match):
            # Do not guess the meaning of numeric ranges or arithmetic.
            if text[match.start()-1].isdigit() and text[match.end()].isdigit():return match.group()
            return '; '
        changed=re.sub(r'(?<=\S)[ \t]+[\u2014\u2013-][ \t]+(?=\S)',punctuation,text)
        if changed!=text:changes.append('Replaced spaced dash separators with semicolons')
        text=changed
    return text,changes

def validate_final(text,req,forbid=False):
    errors=[]
    count=len(text.split())
    if req.get('max_words') and count>req['max_words']:errors.append('Word limit exceeded')
    for term in req.get('required_terms',[]):
        if term.casefold() not in text.casefold():errors.append('Missing required term: '+term)
    if forbid and re.search(r'(?<=\S)[ \t]+[\u2014\u2013-][ \t]+(?=\S)',text):errors.append('Dash clause separator violates preference')
    if re.search(r'(?im)^\s*(?:reviewer checklist|reviewer notes|review notes \(for reviewer\))',text):
        errors.append('Reviewer instructions leaked into deliverable')
    return {'passes':not errors,'errors':errors,'word_count':count,'requirements':req,
            'factual_accuracy':'Not independently verified'}
