"""Department priority controls selection; existing fairness is retained on ties."""
def order(ids,path):
    from superhuman.departments.store import readonly,tables
    from superhuman.planning import store,priority
    with readonly(path) as db:
        if 'projects' not in tables(db):return ids
        scopes={r['id']:r['workstream'] for r in db.execute('SELECT id,workstream FROM projects')}
    cache={}
    def plan(scope):
        if scope not in cache:cache[scope]=store.snapshot(scope)
        return cache[scope]
    from superhuman.agentic.store import runnable
    ids=[pid for pid in ids if runnable(pid,path)]
    kept=[]
    for index,pid in enumerate(ids):
        if pid not in scopes:continue
        data=plan(scopes[pid]);g=data['goal']
        if data['warnings']:continue  # Do not execute against an unreadable owner plan.
        if g.get('status','active')!='active':continue
        linked=[m for m in data['milestones'] if pid in m['project_ids'] and m['status'] not in ('complete','archived')]
        byid={m['id']:m for m in data['milestones']}
        if linked:
            runnable=[m for m in linked if m['status']!='on_hold' and all(byid.get(i,{}).get('status')=='complete' for i in m['depends_on']) and not any(b['status']=='open' and b['milestone_id']==m['id'] for b in data['blockers'])]
            if not runnable:continue
        else:runnable=[]
        dates=[m['target_date'] for m in runnable if m['target_date']]+([g['target_date']] if g['target_date'] else [])
        due=min(dates) if dates else '9999-12-31'
        kept.append((priority.RANK.get(g['priority'],4),due,index,pid))
    return [r[-1] for r in sorted(kept)]
