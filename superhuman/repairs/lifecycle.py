"""Goal lifecycle uses the planning transaction and history."""
STATUSES=('active','on_hold','complete','archived')
def initialize(db):
    db.execute("CREATE TABLE IF NOT EXISTS department_goal_lifecycle(scope TEXT PRIMARY KEY,status TEXT NOT NULL,completion_note TEXT NOT NULL)")
def read(db,scope):
    found=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='department_goal_lifecycle'").fetchone() if db else None
    row=db.execute('SELECT status,completion_note FROM department_goal_lifecycle WHERE scope=?',(scope,)).fetchone() if found else None
    return dict(row) if row else {'status':'active','completion_note':''}
def save(db,scope,status,note,criteria):
    from superhuman.planning.store import text
    if status not in STATUSES:raise ValueError('Choose a valid department goal status')
    note=text(note,2000,'Goal completion note')
    if status=='complete':
        if not criteria or not note:raise ValueError('Add goal success criteria and a completion note before completing the department goal')
        if db.execute("SELECT 1 FROM department_milestones WHERE scope=? AND status NOT IN ('complete','archived')",(scope,)).fetchone():raise ValueError('Complete or archive the remaining milestones before completing this goal')
        if db.execute("SELECT 1 FROM department_blockers WHERE scope=? AND status='open'",(scope,)).fetchone():raise ValueError('Resolve department blockers before completing this goal')
    db.execute('INSERT INTO department_goal_lifecycle VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET status=excluded.status,completion_note=excluded.completion_note',(scope,status,note))
    return {'status':status,'completion_note':note}
