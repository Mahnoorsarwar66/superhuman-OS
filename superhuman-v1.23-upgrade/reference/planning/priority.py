"""Transparent, deterministic ordering; suggestions never execute tasks."""
from . import store
from superhuman.knowledge.store import today

RANK={'critical':0,'high':1,'normal':2,'low':3,'unset':4}

def edit_url(scope,kind='',ident=''):
    from urllib.parse import quote
    base='/department-plans/'+quote(scope,safe='')
    return base+('/'+kind+'/'+quote(ident,safe='') if kind else '')

def actions(scope,plan=None):
    plan=plan or store.snapshot(scope);goal=plan['goal'];result=[]
    if plan['warnings']:return []
    def add(title,kind,due,path,explanation):
        result.append(dict(scope=scope,title=title,kind=kind,due=due,url=path,priority=goal['priority'],reason=explanation))
    byid={m['id']:m for m in plan['milestones']}
    blockers=[b for b in plan['blockers'] if b['status']=='open']
    for b in blockers:
        add(b['description'],'Missing input',b['target_date'],edit_url(scope,'blocker',b['id']),'Needed from: '+(b['needed_from'] or 'Not assigned'))
    for m in plan['milestones']:
        if m['status'] in ('complete','archived'):continue
        pending=[byid[i] for i in m['depends_on'] if i in byid and byid[i]['status']!='complete']
        opened=[b for b in blockers if b['milestone_id']==m['id']]
        if pending:
            explanation='Waiting for: '+', '.join(x['title'] for x in pending)
        elif opened:explanation=str(len(opened))+' open linked blocker(s); resolve them before completion.'
        elif m['status']=='on_hold':explanation='On hold; review whether to resume.'
        else:explanation='Dependencies complete; '+('continue recorded work.' if m['status']=='in_progress' else 'ready for your review before starting.')
        add(m['title'],'Milestone',m['target_date'],edit_url(scope,'milestone',m['id']),explanation)
    if not plan['milestones'] and goal['version']:
        add('Define the first milestone','Planning',goal['target_date'],edit_url(scope,'milestone','new'),'A department plan is saved, but it has no milestones yet.')
    def order(item):
        due=item['due'];overdue=bool(due and due<today().isoformat())
        return (RANK.get(item['priority'],4),0 if overdue else 1,0 if due else 1,due or '9999-12-31',0 if item['kind']=='Missing input' else 1,item['scope'],item['title'])
    return sorted(result,key=order)

def all_departments():
    from superhuman.departments.store import departments
    return [(scope,name,store.snapshot(scope)) for scope,name in departments()]

def queue():
    records=all_departments();items=[a for scope,_,plan in records for a in actions(scope,plan)]
    items.sort(key=lambda a:(RANK.get(a['priority'],4),0 if a['due'] and a['due']<today().isoformat() else 1,0 if a['due'] else 1,a['due'] or '9999-12-31',0 if a['kind']=='Missing input' else 1,a['scope'],a['title']))
    return records,items

def next_step(scope,fallback):
    items=actions(scope)
    if items:return (items[0]['title']+' — '+items[0]['reason'],items[0]['url'])
    plan=store.snapshot(scope)
    if plan['warnings']:return ('Check this department’s planning records.',edit_url(scope))
    if not plan['goal']['version']:return ('Set this department’s goal and priority.',edit_url(scope))
    return fallback
