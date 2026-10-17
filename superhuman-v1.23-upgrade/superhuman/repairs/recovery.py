"""Run only after acquiring the existing exclusive worker lock."""
def recover(path):
    from superhuman.projects import engine as p
    from superhuman.runtime import engine as r
    count=0
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        tasks=[dict(x) for x in db.execute("SELECT project_id,id FROM project_tasks WHERE status='running'")]
        for t in tasks:
            db.execute("UPDATE project_tasks SET status='interrupted',token=NULL,error='Worker restarted before completion. Inspect saved outputs and explicitly authorize retry.' WHERE project_id=? AND id=?",(t['project_id'],t['id']))
            count+=1
        planners=[dict(x) for x in db.execute("SELECT project_id FROM hosted_plans WHERE status='running'")]
        for row in planners:
            db.execute("UPDATE hosted_plans SET status='interrupted',token=NULL,error_type='InterruptedPlanning' WHERE project_id=?",(row['project_id'],))
            db.execute("UPDATE projects SET status='plan_failed',error='Planner interrupted. Inspect before requesting another paid plan.',updated_at=? WHERE id=?",(p.stamp(),row['project_id']))
    for t in tasks:r.event('task_interrupted',t['project_id'],t['id'],{'reason':'worker_restart'},path)
    for row in planners:r.event('planning_interrupted',row['project_id'],detail={'reason':'worker_restart'},path=path)
    return {'tasks':count,'plans':len(planners)}
