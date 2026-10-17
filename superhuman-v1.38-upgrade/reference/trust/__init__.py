"""Read-only readiness shared by the repaired workspaces."""
from superhuman.projects import engine as p
from superhuman.team import store as team,budget
def readiness(path=p.DEFAULT_DB):
 cfg=team.settings(path);paid=budget.ready(cfg['model'],path);enabled=bool(cfg['enabled'])
 reason=('Team execution enabled; paid requests require current budget checks' if enabled and paid else 'Work blocked: '+('; '.join(x for x in ['Team coordination is disabled' if not enabled else '', 'authorize a dollar period and confirm model rates' if not paid else ''] if x)))
 return dict(work_ready=enabled and paid,paid_ready=paid,reason=reason)
def preview(text):
 import re
 return re.sub(r'(?i)\b(password|passwd|api[ _-]?key|access[ _-]?token)(\s*[:=]\s*)([^\s<>,;]+)',lambda m:m.group(1)+m.group(2)+'[redacted]',text)
