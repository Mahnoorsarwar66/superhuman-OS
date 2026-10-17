"""Present each milestone decision at its actual owner gate, once."""
import re
from superhuman.milestones import store as ms
from superhuman.team import store as team

def consolidate(items,path):
    result=[]
    for item in items:
        item=dict(item);match=re.fullmatch(r'/team/tasks/([a-f0-9]+)',item['url'])
        if match and item['reason'].strip().lower() in ('needs review','awaiting review'):
            assignment=ms.assignment(match[1],path)
            if assignment:
                milestone=ms.milestone(assignment['milestone_id'],path)
                # The lead integration is reviewed through the packet gate. Routine
                # contributions are reviewed by the lead, not the owner queue.
                if assignment['role']=='lead':continue
                if not team.needs_owner(team.task(match[1],path),path):continue
                item['url']='/milestones/'+milestone['id']+'?view=deliverable'
                item['reason']='Specialist contribution needs your review'
        if item['reason'] in ('Milestone strategic approval','Milestone requires owner inspection') and re.fullmatch(r'/milestones/[a-f0-9]+',item['url']):item['url']+='?view=reviews'
        result.append(item)
    return result
