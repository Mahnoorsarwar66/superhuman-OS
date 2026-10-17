"""Guarded integration with the delivered v1.21 application."""
import ast
from pathlib import Path
FILES=('navigation/shell.py','navigation/web.py','departments/web.py','hosted/web.py')
def canonical(name,text):return ast.dump(ast.parse(text),include_attributes=False)
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected planning source anchor missing or repeated')
    return text.replace(old,new,1)
def build(name,text,reference):
    if canonical(name,text)!=canonical(name,(Path(reference)/name).read_text(encoding='utf-8')):raise ValueError('Unrecognised source in superhuman/'+name+'. Install v1.21 first; no files changed.')
    if name=='navigation/web.py':text+='\n    from superhuman.planning.web import install as install_planning\n    install_planning(app)\n'
    elif name=='navigation/shell.py':
        text=once(text,"    if path.startswith('/departments'): return 'departments'","    if path.startswith(('/departments','/department-plans')): return 'departments'")
        text=once(text,"('/memory/briefing','Work briefing')","('/memory/briefing','Work briefing'),('/priorities','Department priorities')")
    elif name=='hosted/web.py':
        text=once(text,'        return HTMLResponse(views.page(body))','        from superhuman.planning.presentation import overview_panel\n        body=overview_panel()+body\n        return HTMLResponse(views.page(body))')
    else:
        text=once(text,"def url(scope,tab='summary'):return '/departments/'+quote(scope,safe='')+('/'+tab if tab!='summary' else '')","def url(scope,tab='summary'):\n    if tab=='planning':return '/department-plans/'+quote(scope,safe='')\n    return '/departments/'+quote(scope,safe='')+('/'+tab if tab!='summary' else '')")
        text=once(text,"    body+='<p class=\"department-caption\">Last record update: '","    from superhuman.planning.presentation import card_line\n    body+=card_line(d['scope'])\n    body+='<p class=\"department-caption\">Last record update: '")
        text=once(text,'        try:return store.snapshot(scope)',"        try:\n            from superhuman.planning.priority import next_step\n            result=store.snapshot(scope)\n            result['next']=next_step(scope,result['next'])\n            return result")
        text=once(text,"('activity','Activity & Decisions')])","('activity','Activity & Decisions'),('planning','Plan & Priorities')])")
        text=text.replace('Department goals and deadlines are not yet configured.','Set goals, priorities and milestone dates under Plan &amp; Priorities.')
        start="            body+='<dl class=\"department-facts\"><dt>Department goal</dt>"
        lines=text.splitlines(True);found=[i for i,line in enumerate(lines) if line.startswith(start)]
        if len(found)!=1:raise ValueError('Expected department facts section')
        lines[found[0]]="            from superhuman.planning.presentation import summary_panel\n            body+=summary_panel(scope)+'<p class=\"department-caption\">Last work record update: '+esc(when(d['last_update']))+'</p></section>'\n"
        text=''.join(lines)
        text=once(text,'Suggestions follow simple status rules; they do not set your priorities.','Suggestions reflect your saved planning priorities and recorded statuses; they do not execute work.')
        text=once(text,'Suggested from recorded statuses. This is not an assigned priority or an execution instruction.','Suggested from your plan and recorded statuses. Open the linked item to review it; no work starts automatically.')
    ast.parse(text);return text
