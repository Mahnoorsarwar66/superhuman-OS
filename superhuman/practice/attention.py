"""One owner-facing queue for interview questions and unreviewed milestone impact."""
from . import store as s
from superhuman.team import store as team
from superhuman.milestones import store as ms

def items(path=s.p.DEFAULT_DB):
 result=[]
 for q in team.projects(path):
  pid=q['id'];interview=s.interview(pid,path)
  if not interview:continue
  if not s.current(pid,path):result.append({'title':q['title'],'reason':'Project expectations need confirmation','url':'/project-briefs/'+pid+'?step=5'})
  pending=s.read('practice_questions',"SELECT id FROM practice_questions WHERE project_id=? AND status='open'",(pid,),path)
  if pending:result.append({'title':q['title']+' · '+str(len(pending))+' team questions','reason':'Project interview clarification','url':'/project-briefs/'+pid+'?step=5'})
  unreviewed=[]
  for milestone in ms.listing(pid,path):
   if milestone['state']!='approved':continue
   packet=ms.packet(milestone['id'],path)
   if packet and not s.read('practice_impacts','SELECT id FROM practice_impacts WHERE milestone_id=? AND packet_id=? AND packet_digest=?',(milestone['id'],packet['id'],packet['digest']),path):unreviewed.append(milestone)
  if unreviewed:result.append({'title':q['title']+' · milestone impact','reason':str(len(unreviewed))+' approved milestone outcomes need review','url':'/project-briefs/'+pid+'/impact'})
 return result
