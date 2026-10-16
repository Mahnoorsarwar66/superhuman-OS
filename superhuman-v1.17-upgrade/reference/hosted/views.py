import html


def esc(value):return html.escape(str(value if value is not None else ''),quote=True)

STYLE='''*{box-sizing:border-box}body{margin:0;background:#f4f6f1;color:#18352d;font:16px/1.6 system-ui,sans-serif}a{color:#14624e}header{background:#163b30;color:#fff;padding:20px max(20px,calc((100vw - 960px)/2));display:flex;align-items:center;justify-content:space-between;gap:12px}header a{color:#fff;text-decoration:none}header strong{font-size:24px}main{max-width:1000px;margin:0 auto;padding:24px 20px 64px}nav{display:flex;gap:16px;flex-wrap:wrap;margin:0 0 24px}.card{background:#fff;border:1px solid #d9e2d7;padding:22px;border-radius:16px;margin:16px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.grid .card{margin:0}h1{font-size:clamp(26px,5vw,36px);line-height:1.2;margin:12px 0 18px}h2{font-size:21px;margin:0 0 12px}p{margin:10px 0}label{display:block;margin:14px 0}input,textarea,select{display:block;width:100%;font:inherit;padding:12px;margin-top:6px;border:1px solid #b8cbbd;border-radius:9px;background:#fff}textarea{min-height:140px}button,.button{display:inline-block;border:0;border-radius:9px;padding:12px 18px;background:#16604b;color:white;font:inherit;cursor:pointer;text-decoration:none;min-height:44px}.secondary{background:#e8efe6;color:#214a37}.muted,small{color:#60756b}.badge{display:inline-block;padding:4px 10px;border-radius:20px;background:#edf2e8;font-size:13px}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between}.stack{display:flex;gap:10px;flex-wrap:wrap}.stack form{margin:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:600px;overflow:auto;background:#f5f7f1;padding:16px;border-radius:10px;font:14px/1.6 ui-monospace,monospace}.error{padding:15px;background:#fff0e8;border-radius:10px}header form button{background:#315b4a;padding:7px 12px}.login{max-width:440px;margin:8vh auto}.login h1{margin-bottom:12px}@media(max-width:640px){.grid{grid-template-columns:1fr}header{padding:16px 20px}main{padding:20px 16px 50px}.card{padding:18px}nav{gap:12px;font-size:14px}.stack>*{flex:1}button,.button{width:100%;text-align:center}header button{width:auto}h2{overflow-wrap:anywhere}}'''


def page(body,title='Superhuman',signed_in=True):
    controls='<form method="post" action="/logout"><button>Sign out</button></form>' if signed_in else ''
    nav='<nav><a href="/">Today</a><a href="/projects">Projects</a><a href="/tools">Files</a><a href="/documents">Documents</a><a href="/coding">Coding</a><a href="/memory">Memory</a><a href="/talk">Talk</a><a href="/tasks">Tasks</a><a href="/calendar">Calendar</a><a href="/inboxes">Inboxes</a><a href="/briefing">Briefing</a></nav>' if signed_in else ''
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+STYLE+'</style></head><body><header><a href="/"><strong>superhuman.</strong></a>'+controls+'</header><main>'+nav+body+'</main></body></html>'


def login(csrf,error=''):
    return page('<section class="card login"><p class="muted">YOUR PRIVATE WORKSPACE</p><h1>Welcome back.</h1><p>Sign in to review your work and keep things moving.</p>'+('<p class="error">'+esc(error)+'</p>' if error else '')+'<form method="post" action="/login"><input type="hidden" name="csrf" value="'+esc(csrf)+'"><label>Username<input name="username" autocomplete="username" maxlength="80" required></label><label>Password<input name="password" type="password" autocomplete="current-password" maxlength="1024" required></label><button>Sign in</button></form></section>',signed_in=False)


LABELS={'new':'Ready to plan','plan_review':'Plan needs approval','active':'In progress','needs_review':'Ready for review','approved':'Approved','quality_blocked':'Needs correction','budget_blocked':'Request limit reached','dependency_blocked':'Dependency blocked','plan_failed':'Planning stopped','pending':'Not started','failed':'Stopped','rejected':'Changes requested','running':'Working','interrupted':'Interrupted'}


def label(value):return LABELS.get(value,value.replace('_',' ').capitalize())

# knowledge-v110
