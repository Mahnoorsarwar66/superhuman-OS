"""Read-only readiness shared by the repaired workspaces."""
from superhuman.projects import engine as p
from superhuman.team import store as team,budget
def readiness(path=p.DEFAULT_DB):
 cfg=team.settings(path);paid=budget.ready(cfg['model'],path);enabled=bool(cfg['enabled'])
 from superhuman.departments.store import readonly,tables
 with readonly(path) as db:
  worker=db.execute('SELECT paused FROM hosted_worker WHERE id=1').fetchone() if 'hosted_worker' in tables(db) else None
 reasons=[x for x in ['Team coordination is disabled' if not enabled else '', 'Team coordination is held for inspection' if cfg['hold'] else '', 'worker is paused' if worker and worker['paused'] else '', 'authorize a dollar period and confirm model rates' if not paid else ''] if x]
 reason='Work blocked: '+'; '.join(reasons) if reasons else 'Task controls ready; project, assignment and request-specific budget checks still apply'
 return dict(work_ready=not reasons,paid_ready=paid,reason=reason)
def employee_status(employee,path=p.DEFAULT_DB):
 if employee['paused']:return 'Employee paused'
 return readiness(path)['reason']
def preview(text):
 import re
 return re.sub(r'(?i)\b(password|passwd|api[ _-]?key|access[ _-]?token)(\s*[:=]\s*)([^\s<>,;]+)',lambda m:m.group(1)+m.group(2)+'[redacted]',text)
