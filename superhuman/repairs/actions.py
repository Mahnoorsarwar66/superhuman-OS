"""Ready actions precede waiting milestones; operational reviews remain visible."""
def actions(scope,plan=None):
    from superhuman.planning import store,priority
    plan=plan or store.snapshot(scope);g=plan['goal']
    if plan['warnings'] or g.get('status','active')!='active':return []
    result=[];byid={m['id']:m for m in plan['milestones']};opened=[b for b in plan['blockers'] if b['status']=='open']
    def add(title,kind,due,path,reason,state='ready'):
        result.append(dict(scope=scope,title=title,kind=kind,due=due,url=path,priority=g['priority'],reason=reason,state=state))
    for b in opened:add(b['description'],'Missing input',b['target_date'],priority.edit_url(scope,'blocker',b['id']),'Needed from: '+(b['needed_from'] or 'Not assigned'))
    for m in plan['milestones']:
        if m['status'] in ('complete','archived'):continue
        pending=[byid.get(i,{'title':'Unavailable dependency'}) for i in m['depends_on'] if byid.get(i,{}).get('status')!='complete']
        blockers=[b for b in opened if b['milestone_id']==m['id']]
        if pending:state='waiting';reason='Waiting for: '+', '.join(x['title'] for x in pending)
        elif blockers:state='waiting';reason='Resolve the linked missing inputs before advancing this milestone.'
        elif m['status']=='on_hold':state='on_hold';reason='On hold. Review whether to resume.'
        else:state='ready';reason='Dependencies complete. Review the linked projects and next step.'
        add(m['title'],'Milestone',m['target_date'],priority.edit_url(scope,'milestone',m['id']),reason,state)
    if not any(m['status']!='archived' for m in plan['milestones']) and g['version']:
        add('Define the next milestone','Planning',g['target_date'],priority.edit_url(scope,'milestone','new'),'No non-archived milestones are recorded.')
    return sorted(result,key=sort_key)
def sort_key(a):
    from superhuman.planning.priority import RANK
    from superhuman.knowledge.store import today
    return (0 if a.get('state','ready')=='ready' else 1,RANK.get(a['priority'],4),0 if a['due'] and a['due']<today().isoformat() else 1,a['due'] or '9999-12-31',0 if a['kind']=='Missing input' else 1,a['scope'],a['title'])
def queue():
    from superhuman.planning import priority
    records=priority.all_departments();items=[a for scope,_,p in records for a in actions(scope,p)]
    return records,sorted(items,key=sort_key)
def next_step(scope,fallback):
    from superhuman.planning import store,priority
    # Review or repair is a necessary next action even when a milestone is dated.
    if fallback[0].startswith(('Review the prepared plan:','Review the completed draft:','Inspect the blocked','Review a proposed task:')):return fallback
    plan=store.snapshot(scope)
    if plan['warnings']:return ('Check unreadable planning records.',priority.edit_url(scope))
    if plan['goal'].get('status','active')!='active':return ('Department goal is '+plan['goal']['status'].replace('_',' ')+'. Review the plan.',priority.edit_url(scope))
    items=actions(scope,plan);ready=[a for a in items if a['state']=='ready']
    if ready:return (ready[0]['title']+' — '+ready[0]['reason'],ready[0]['url'])
    if items:return ('Resolve milestone dependencies or holds before advancing.',priority.edit_url(scope))
    if not plan['goal']['version']:return ('Set this department’s goal and priority.',priority.edit_url(scope))
    return fallback

def milestone_progress(scope,plan=None):
    from superhuman.planning import store
    from superhuman.departments.store import snapshot
    plan=plan or store.snapshot(scope);data=snapshot(scope);projects={p['id']:p for p in data['projects']}
    result={}
    for m in plan['milestones']:
        tasks=[t for t in data['tasks'] if t['project_id'] in m['project_ids']]
        ready=plan['goal'].get('status','active')=='active' and bool(m['project_ids']) and all(projects.get(i,{}).get('status')=='approved' for i in m['project_ids']) and m['status'] not in ('complete','archived')
        ready=ready and all(next((x['status'] for x in plan['milestones'] if x['id']==dep),'missing')=='complete' for dep in m['depends_on']) and not any(b['status']=='open' and b['milestone_id']==m['id'] for b in plan['blockers'])
        result[m['id']]={'approved_tasks':sum(t['status']=='approved' for t in tasks),'total_tasks':len(tasks),'ready_for_review':ready}
    return result
