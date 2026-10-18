"""Packet-linked owner impact assessments and complete lifetime assignment costs."""
import json
from decimal import Decimal,InvalidOperation
from uuid import uuid4
from . import store as s
from superhuman.projects import engine as p
from superhuman.team import store as team
from superhuman.milestones import store as ms,workflow as mw
from superhuman.departments.store import tables
CHECKS={'sections':'Required sections accepted','evidence':'Critical claims supported','consistency':'No unresolved material contradictions','delivery':'Agreed deadline and budget met','independent':'Independent assessment completed','usefulness':'Confident to use externally'}
def money(value):
 try:d=Decimal(str(value))
 except InvalidOperation:raise ValueError('Use a valid nonnegative amount') from None
 if not d.is_finite() or d<0 or d>Decimal('10000000'):raise ValueError('Amount out of range')
 return str(d)
def costs(pid,path=p.DEFAULT_DB):
 team.project(pid,path)
 with s.readonly(path) as db:
  if 'team_costs' not in tables(db):return {'charged_usd':'0','reserved_usd':'0','uncertain_entries':0,'entries':0}
  # Include every period and revision; task IDs and milestone coordination IDs both used by existing accounting.
  ids={r['id'] for r in db.execute('SELECT id FROM team_tasks WHERE project_id=?',(pid,))}
  if 'milestone_cycles' in tables(db):ids|={r['id'] for r in db.execute('SELECT id FROM milestone_cycles WHERE project_id=?',(pid,))}
  ids.add(pid)
  links={r['cost_id'] for r in db.execute('SELECT cost_id FROM practice_cost_links WHERE project_id=?',(pid,))} if 'practice_cost_links' in tables(db) else set()
  rows=[dict(r) for r in db.execute('SELECT * FROM team_costs') if r['task_id'] in ids or r['id'] in links]
  charged=sum(r['charged_text']+r['charged_tools'] for r in rows)
  outstanding=sum(r['reserved_text']+r['reserved_tools'] for r in rows if r['state'] in ('reserved','uncertain'))
 return {'charged_usd':str(Decimal(charged)/1000000),'reserved_usd':str(Decimal(outstanding)/1000000),'uncertain_entries':sum(r['state'] in ('reserved','uncertain') for r in rows),'entries':len(rows)}
def add(mid,packet_id,assessments,readiness,outcome,note,extras,path=p.DEFAULT_DB):
 m=ms.milestone(mid,path);packet=mw.verify_packet(mid,path)
 if m['state']!='approved' or packet['id']!=packet_id:raise ValueError('Review the currently owner-approved packet')
 if set(assessments)!=set(CHECKS) or any(v not in ('met','revise','not_assessed') for v in assessments.values()):raise ValueError('Assess every success measure explicitly')
 readiness=team.text(readiness,1600,'Readiness change',True);outcome=team.text(outcome,1600,'Observable outcome',True);note=team.text(note,1600,'Evidence and limits',True)
 allowed={'paid_data','hosting','external','owner_review','rework','hours_low','hours_high','rate_low','rate_high'}
 if set(extras)-allowed:raise ValueError('Unknown cost or time field')
 extras={k:money(v) for k,v in extras.items() if str(v).strip()}
 for a,b in [('hours_low','hours_high'),('rate_low','rate_high')]:
  if (a in extras)!=(b in extras) or a in extras and Decimal(extras[a])>Decimal(extras[b]):raise ValueError('Provide a complete low/high range in ascending order')
 ident=uuid4().hex
 with p.connect(path) as db:
  db.execute('BEGIN IMMEDIATE');live=db.execute('SELECT state,current_packet FROM milestones WHERE id=?',(mid,)).fetchone()
  if not live or live['state']!='approved' or live['current_packet']!=packet_id:raise ValueError('Packet changed before saving review')
  db.execute('INSERT INTO practice_impacts VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,mid,packet_id,packet['digest'],json.dumps(assessments),readiness,outcome,note,json.dumps(extras),p.stamp()))
  team.event(db,'owner','milestone_impact_reviewed',{'id':ident,'milestone_id':mid,'packet_id':packet_id})
 return ident
