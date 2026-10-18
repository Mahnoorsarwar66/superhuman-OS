"""Project-scoped links to saved channels and topics, including retained archives."""
import html
from urllib.parse import urlencode
from superhuman.projects import engine as p
from . import store as s


def channels(pid,kind='team',path=p.DEFAULT_DB):
    if kind!='team':return []
    return s.read('SELECT * FROM hub_channels WHERE project_id=? ORDER BY archived,title,id',(pid,),path)


def rooms(pid,kind='team',path=p.DEFAULT_DB):
    from superhuman.experience import store as ux
    values=ux.project_rooms(kind,pid,path)
    if kind!='team':return values
    internal={r['thread_id'] for r in s.read('SELECT d.thread_id FROM hub_steps h JOIN dialogue_turns d ON d.id=h.turn_id JOIN hub_rounds r ON r.id=h.round_id JOIN hub_topics t ON t.id=r.topic_id JOIN hub_channels c ON c.id=t.channel_id WHERE c.project_id=?',(pid,),path)}
    return [r for r in values if r['id'] not in internal]


def section(pid,kind='team',path=p.DEFAULT_DB):
    rows=channels(pid,kind,path)
    if not rows:return ''
    E=lambda x:html.escape(str(x),quote=True)
    link=lambda values,text:'<a href="/team-hub?'+E(urlencode(values))+'">'+E(text)+'</a>'
    body='<section aria-label="Project team discussions"><h3>Team channels &amp; milestone discussions</h3>'
    for c in rows:
        body+='<article class="card"><h4>'+link({'channel':c['id']},'# '+c['title'])+'</h4><p>'+('Archived channel · saved history' if c['archived'] else 'Project channel')+'</p>'
        topics=s.read('SELECT t.*,m.title AS milestone_title FROM hub_topics t LEFT JOIN milestones m ON m.id=t.milestone_id WHERE t.channel_id=? ORDER BY t.created_at DESC,t.id DESC LIMIT 101',(c['id'],),path)
        for t in topics[:100]:
            body+='<p>'+link({'topic':t['id']},t['title'])+(' · '+E(t['milestone_title']) if t['milestone_title'] else ' · General project discussion')+'</p>'
        if len(topics)>100:body+='<p>'+link({'channel':c['id']},'Browse all channel threads')+'</p>'
        if not topics:body+='<p>No discussion threads yet. Open the channel to start one.</p>'
        body+='</article>'
    return body+'</section>'
