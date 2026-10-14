"""Local-only dashboard for the v0.7 durable queue. No external actions."""
import html
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from superhuman.queue.engine import enqueue, list_jobs, get_job, review
from superhuman.core.router import WORKSTREAMS

app = FastAPI(title="Superhuman OS", docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path.cwd().resolve()
OUTPUTS = (ROOT / "data" / "outputs").resolve()

@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0].lower()
    if host not in {'127.0.0.1', 'localhost'}:
        return PlainTextResponse('Local access only', status_code=403)
    if request.method == 'POST':
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') not in {'http://127.0.0.1:8000', 'http://localhost:8000'}:
            return PlainTextResponse('Origin not allowed', status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)

def page(body, title="Command Center"):
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} — Superhuman OS</title><style>
    :root{{--bg:#0b1020;--panel:#151d32;--border:#2c3953;--text:#e9f0ff;--muted:#9caec9;--accent:#7da7ff;--ok:#58d1a2;--warn:#f6be67}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}}header{{padding:24px 6%;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}header strong{{font-size:24px}}header span{{color:var(--muted)}}main{{max-width:1200px;margin:32px auto;padding:0 20px}}a{{color:var(--accent)}}h1{{font-size:30px}}h2{{font-size:19px}}.muted{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0}}.card,.panel{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:20px}}.card b{{font-size:30px;display:block;margin-top:6px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}label{{display:block;margin:12px 0;color:var(--muted)}}input,select,textarea{{display:block;width:100%;margin-top:7px;padding:11px;border:1px solid var(--border);border-radius:8px;background:#0c1527;color:var(--text);font:inherit}}textarea{{min-height:90px}}button{{padding:10px 18px;border:0;border-radius:8px;background:var(--accent);color:#0b1020;font-weight:700;cursor:pointer}}button.danger{{background:#ffa19b}}table{{border-collapse:collapse;width:100%}}td,th{{padding:11px 8px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}}th{{color:var(--muted)}}.tag{{font-size:12px;padding:4px 7px;background:#26344e;border-radius:6px;white-space:nowrap}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;color:#dce7ff;background:#0c1527;border-radius:9px;padding:20px;max-height:600px;overflow:auto}}.stack{{display:flex;gap:10px;flex-wrap:wrap;align-items:end}}.stack form{{flex:1}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}table{{font-size:13px}}header{{padding:18px}}}}</style></head><body><header><strong>✦ Superhuman OS</strong><span>Private local command center · v0.8</span></header><main>{body}</main></body></html>''')

@app.get('/', response_class=HTMLResponse)
def home():
    jobs = list_jobs()
    counts = {k: sum(j['status'] == k for j in jobs) for k in ['queued','running','needs_review','approved','failed']}
    cards = ''.join(f'<div class="card"><span class="muted">{esc(k.replace("_"," ").title())}</span><b>{v}</b></div>' for k,v in counts.items())
    options = ''.join(f'<option value="{esc(k)}">{esc(v["name"])}</option>' for k,v in WORKSTREAMS.items())
    rows = ''.join(f'<tr><td><a href="/jobs/{esc(j["id"])}">{esc(j["title"][:85])}</a></td><td>{esc(j["project"])}</td><td><span class="tag">{esc(j["status"])}</span></td><td>{esc(j["kind"])}</td></tr>' for j in jobs[:100]) or '<tr><td colspan="4">No assignments yet</td></tr>'
    return page(f'''<h1>Command Center</h1><p class="muted">Assign research or drafting work. Start the separate queue worker to process assignments.</p><section class="cards">{cards}</section><div class="grid"><section class="panel"><h2>New assignment</h2><form method="post" action="/jobs"><label>Workstream<select name="project">{options}</select></label><label>Task type<select name="kind"><option value="research">Research with sources</option><option value="collab">Collaborative draft and review</option></select></label><label>Title<input name="title" maxlength="200" required></label><label>Instructions<textarea name="details" maxlength="12000"></textarea></label><button>Create queued task</button></form></section><section class="panel"><h2>Agent workforce</h2><p class="muted">Workstreams available for routing and review.</p>{''.join(f'<p>• {esc(cfg["name"])} <span class="muted">— {esc(cfg["agent"])}</span></p>' for cfg in WORKSTREAMS.values())}<p class="muted">v0.8 does not launch workers, send messages or spend money on your behalf.</p></section></div><section class="panel" style="margin-top:22px"><h2>Task queue</h2><table><tr><th>Assignment</th><th>Project</th><th>Status</th><th>Mode</th></tr>{rows}</table></section>''')

@app.post('/jobs')
def add_job(project: str = Form(...), kind: str = Form(...), title: str = Form(...), details: str = Form('')):
    if len(title) > 200 or len(details) > 12000:
        raise HTTPException(400, 'Input too long')
    try:
        job_id = enqueue(kind, project, title, details)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(f'/jobs/{job_id}', status_code=303)

@app.get('/jobs/{job_id}', response_class=HTMLResponse)
def job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, 'Job not found')
    output = ''
    path = job.get('output_path')
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        candidate = candidate.resolve()
        if candidate.is_relative_to(OUTPUTS) and candidate.is_file():
            output = candidate.read_text(encoding='utf-8', errors='replace')[:150000]
        else:
            output = 'Output path unavailable or outside the approved output directory.'
    controls = ''
    if job['status'] == 'needs_review':
        controls = f'''<div class="stack"><form action="/jobs/{esc(job_id)}/review" method="post"><input type="hidden" name="action" value="approve"><label>Review note<input name="note" maxlength="2000" placeholder="Why accepted?"></label><button>Approve draft</button></form><form action="/jobs/{esc(job_id)}/review" method="post"><input type="hidden" name="action" value="reject"><label>Rejection note<input name="note" maxlength="2000" placeholder="What needs improvement?"></label><button class="danger">Reject draft</button></form></div>'''
    return page(f'''<p><a href="/">← Command Center</a></p><h1>{esc(job['title'])}</h1><p><span class="tag">{esc(job['status'])}</span> · {esc(job['kind'])} / {esc(job['project'])} · Attempts: {esc(job['attempts'])}</p><section class="panel"><h2>Instructions</h2><p>{esc(job['details'])}</p><h2>Agent output</h2><pre>{esc(output or 'No output yet. Check the worker terminal and refresh.')}</pre><p class="muted">{esc(job.get('last_error') or '')}</p>{controls}<p class="muted">Review status accepts drafts; it never authorizes external actions.</p></section>''', title=job['title'])

@app.post('/jobs/{job_id}/review')
def review_job(job_id: str, action: str = Form(...), note: str = Form('')):
    if len(note) > 2000 or action not in {'approve','reject'}:
        raise HTTPException(400, 'Invalid review')
    try:
        review(job_id, action, note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(f'/jobs/{job_id}', status_code=303)
