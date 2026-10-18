"""Read-only planning panels for existing department and Overview pages."""
from datetime import date
from urllib.parse import quote
from superhuman.navigation.shell import esc
from . import store,priority
from superhuman.knowledge.store import today

LABELS={'unset':'Not set','critical':'Critical','high':'High','normal':'Normal','low':'Low'}
def link(path,title):return '<a href="'+esc(path)+'">'+esc(title)+'</a>'
def due_label(value):
    if not value:return 'Not set'
    return value+(' · overdue' if value<today().isoformat() else ' · today' if value==today().isoformat() else '')

def card_line(scope):
    p=store.snapshot(scope);g=p['goal']
    if p['warnings']:return '<p class="error">Planning records unavailable; '+link(priority.edit_url(scope),'check plan')+'.</p>'
    return '<p><strong>Priority:</strong> '+esc(LABELS[g['priority']])+' · <strong>Target:</strong> '+esc(due_label(g['target_date']) if g.get('status','active')=='active' else 'Goal '+g['status'].replace('_',' '))+'</p>'+('<p>'+esc(g['objective'][:180])+'</p>' if g['objective'] else '')

def summary_panel(scope):
    p=store.snapshot(scope);g=p['goal']
    body=''.join('<p class="error">'+esc(w)+'</p>' for w in p['warnings'])
    pending=[m for m in p['milestones'] if m['status'] not in ('complete','archived')] if g.get('status','active')=='active' else []
    completed=sum(m['status']=='complete' for m in p['milestones'])
    dates=[m['target_date'] for m in pending if m['target_date']]+([g['target_date']] if g['target_date'] and g.get('status','active')=='active' else [])
    deadline=min(dates) if dates else ''
    body+='<dl class="department-facts"><dt>Department goal</dt><dd>'+esc(g['objective'] or 'Not set')+'</dd><dt>Goal status</dt><dd>'+esc(g.get('status','active').replace('_',' '))+'</dd><dt>Priority</dt><dd>'+esc(LABELS[g['priority']])+'</dd><dt>Next deadline</dt><dd>'+esc(due_label(deadline))
    if not deadline:body+=' — existing calendar events do not have department associations.'
    body+='</dd><dt>Success criteria</dt><dd>'+esc(g['success_criteria'] or 'Not set')+'</dd><dt>Milestones</dt><dd>'+str(completed)+' complete / '+str(sum(m['status']!='archived' for m in p['milestones']))+' non-archived</dd><dt>Missing inputs</dt><dd>'+str(sum(b['status']=='open' for b in p['blockers']))+' open</dd></dl><p>'+link(priority.edit_url(scope),'Edit plan, milestones and missing inputs')+'</p><p class="muted">Milestone completion is manually recorded against your criteria; it is separate from task approval.</p>'
    return body

def action_list(items):
    from superhuman.core.router import WORKSTREAMS
    return '<ol>'+''.join('<li><strong>'+esc(LABELS.get(a['priority'],'Not set'))+'</strong> · '+link(a['url'],a['title'])+'<p class="muted">'+esc(WORKSTREAMS.get(a['scope'],{}).get('name',a['scope']))+' · '+esc(a['kind'])+' · '+esc(due_label(a['due']))+'<br>'+esc(a['reason'])+'</p></li>' for a in items)+'</ol>'

def overview_panel():
    records,items=priority.queue()
    body='<section class="card"><div class="eyebrow">Across departments</div><h2>Your priorities and next actions</h2>'
    if any(p['warnings'] for _,_,p in records):body+='<p class="error">Some department plans could not be read. Check the full priorities view.</p>'
    ready=[a for a in items if a.get('state','ready')=='ready']
    body+=action_list(ready[:5]) if ready else '<p>No milestone or missing-input actions recorded yet. Set your department goals and milestones to build this list.</p>'
    body+='<p>'+link('/priorities','Open all department priorities')+'</p><small>Actionable items appear before waiting work, then your department priorities and dates apply. Reviews and recovery remain available in Attention. These suggestions do not start work.</small></section>'
    return body
