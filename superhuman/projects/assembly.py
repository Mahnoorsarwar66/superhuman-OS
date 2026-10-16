"""Preserve corrected dependency text without spending additional API calls."""
import hashlib
import json
from pathlib import Path
from . import engine as e
from superhuman.collab.reliability import validate_final


def mode(project):return json.loads(project.get('plan_json') or '{}').get('final_mode','auto')


def will_assemble(project,task,tasks):
    if task['id']!='final' or task['kind']!='collab':return False
    selected=mode(project)
    if selected=='synthesize':return False
    deps=json.loads(task['deps'])
    if not deps:return False  # A standalone runtime job is not a consolidation.
    records={r['id']:r for r in tasks}
    for dep in deps:
        r=records.get(dep)
        if not r or r['status'] not in ('needs_review','approved') or not r.get('result_json'):return False
        result=json.loads(r['result_json'])
        if selected=='auto' and result.get('local_revision',{}).get('action')!='revise':return False
    return selected in ('auto','preserve')


def assemble(project,task,dependencies,folder,forbid=False):
    if not dependencies:raise ValueError('Preservation requires dependency outputs')
    title='# '+project['objective'].replace('\r',' ').replace('\n',' ')
    parts=[title];provenance=[]
    for dep in dependencies:
        record,result,content=dep['task'],dep['result'],dep['text']
        # Existing report-reader delimiters must never silently shorten an artifact.
        if '## Revised deliverable' in content or '\n---\n' in content:
            raise ValueError('A dependency contains report delimiters; use a plain local revision before preservation')
        parts.append(content.strip())
        provenance.append({'task_id':record['id'],'output':record['output'],
                           'content_sha256':hashlib.sha256(content.encode()).hexdigest(),
                           'revision_id':result.get('local_revision',{}).get('id'),
                           'status_at_assembly':record['status']})
    text='\n\n'.join(parts)+'\n'
    checks=json.loads(task['checks'])
    report=validate_final(text,checks,forbid)
    report.update(basis='Local preservation and deterministic checks',
                  semantic_review='No additional model review; dependency review states are preserved in provenance',
                  factual_accuracy='Not independently verified')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    output=folder/'assembled.md'
    output.write_text('# Consolidated project deliverable\n\n**Preparation:** local preservation; zero API calls\n\n'
                      '## Revised deliverable\n\n'+text+'\n---\n\n## Final deterministic checks\n\n'+
                      json.dumps(report,indent=2)+'\n',encoding='utf-8')
    result={'output':str(output),'api_calls':0,'quality_report':report,
            'assembly':{'mode':'preserve','dependencies':provenance,'text_rewritten':False},
            'created_at':e.stamp(),'status':'needs_review' if report['passes'] else 'quality_blocked'}
    output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
