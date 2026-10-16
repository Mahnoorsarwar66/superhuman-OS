"""An isolated, deterministic smoke demonstration. No model requests."""
import os
from pathlib import Path
import tempfile
from . import engine as r
from superhuman.projects import engine as p


def run():
    old=Path.cwd()
    # Identity/source configuration is read-only; demo data lives entirely in temp.
    with tempfile.TemporaryDirectory() as directory:
        try:
            os.chdir(directory)
            db=Path('demo.db')
            pid=p.create('marketing','Build a small evidence-based briefing',max_calls=10,path=db)
            p.set_plan(pid,{'tasks':[
                {'id':'evidence','kind':'research','title':'Gather evidence','details':'Collect source evidence',
                 'checks':{'required_terms':['evidence']}},
                {'id':'brief','kind':'collab','title':'Prepare briefing','details':'Use the dependency evidence',
                 'depends_on':['evidence'],'checks':{'required_terms':['briefing']}}
            ]},db)
            def execute(task,brief,folder):
                text='Evidence and briefing for demonstration only.\n'
                if task['id'] in ('brief','final'):
                    expected='evidence' if task['id']=='brief' else 'brief'
                    if 'DEPENDENCY '+expected not in brief:raise AssertionError('Dependency missing')
                output=folder/'demo.md';output.write_text(text,encoding='utf-8')
                return {'output':str(output),'sources':[{'url':'https://example.org/demo','title':'Synthetic fixture'}]}
            before=r.work(db,max_tasks=10,include_queue=False,executor=execute)
            if before:raise AssertionError('Unapproved plan executed')
            p.approve_plan(pid,db)
            results=r.work(db,max_tasks=10,include_queue=False,executor=execute)
            if [x['task_id'] for x in results]!=['evidence','brief','final']:raise AssertionError('Unexpected task sequence')
            if p.get(pid,db)['status']!='needs_review':raise AssertionError('Final review missing')
            r.review(pid,'final','approve','Synthetic smoke test',db)
            if p.get(pid,db)['status']!='approved':raise AssertionError('Approval failed')
            return {'passes':True,'execution_order':[x['task_id'] for x in results],
                    'final_status':'approved','api_calls':0,
                    'note':'Synthetic executor; demonstrates orchestration, not live model or Windows/Docker behaviour.'}
        finally:os.chdir(old)
