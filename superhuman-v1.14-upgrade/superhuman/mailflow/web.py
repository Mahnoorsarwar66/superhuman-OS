"""Visible sync scope and report coverage, without claiming human review."""
from datetime import datetime,timezone
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from superhuman.hosted.views import esc
from superhuman.briefing.engine import local_time
from . import state


def panel(slot):
    value=state.summary(slot);scan=value['scan']
    body='<div class="card"><h3>Reading and report coverage</h3><p>'+str(value['saved'])+' saved previews · '+str(value['included'])+' included in completed reports · '+str(value['pending'])+' reserved by pending reports · <strong>'+str(value['waiting'])+' waiting for a report</strong>.</p>'
    if scan:
        body+='<p>Scan: '+esc(scan['status'].replace('_',' '))+'. '+str(scan['processed'])+' / '+str(scan['found'])+' discovered candidates processed. '+str(scan['saved'])+' previews saved this scan; '+str(scan['unavailable'])+' unavailable or outside its exact time bounds.</p>'
        body+='<p>Window: '+esc(local_time(datetime.fromtimestamp(scan['start'],timezone.utc).isoformat()))+' to '+esc(local_time(datetime.fromtimestamp(scan['end'],timezone.utc).isoformat()))+'. INBOX only.</p>'
        body+='<p>'+esc(scan['note'] or 'Read in progress.')+'</p>'
    else:body+='<p>No paged scan yet. Click Read to start a seven-day INBOX scan.</p>'
    body+='<p class="muted">Included means supplied as an excerpt to a completed model report. It does not mean you read it, the model understood every detail, or the email was marked read. Attachments and omitted body content remain outside coverage.</p>'
    body+='<details><summary>Restart a failed provider scan</summary><p>Use this if retrying Read cannot recover an expired provider page token. Starts a new seven-day scan, retaining saved emails, report history and deduplication.</p><form method="post" action="/mailflow/'+esc(slot)+'/restart"><button class="secondary">Restart scoped scan · 0 model requests</button></form></details></div>'
    return body


def install(app):
    @app.post('/mailflow/{slot}/restart')
    def restart(slot:str):
        try:state.restart(slot)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return RedirectResponse('/inboxes/'+slot,status_code=303)
