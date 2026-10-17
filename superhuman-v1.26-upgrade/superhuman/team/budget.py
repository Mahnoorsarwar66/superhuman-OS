"""Atomic USD-micro reservations with pinned rates and conservative usage accounting."""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal,ROUND_CEILING,InvalidOperation
import json,time
from types import SimpleNamespace
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.departments.store import readonly,tables,rows

billing_context=ContextVar('team_billing_context',default={'actor':'legacy','task_id':None})
class BudgetBlocked(ValueError):pass

def micro(value):
    try:d=Decimal(str(value))
    except InvalidOperation:raise ValueError('Invalid dollar amount') from None
    if not d.is_finite() or d<0 or d>2000:raise ValueError('Dollar amount must be between 0 and 2000')
    return int((d*1000000).to_integral_value(rounding=ROUND_CEILING))
def usd(value):return format(Decimal(value)/1000000,'.6f')
def cost(rate,tokens):return int((Decimal(str(rate))*tokens).to_integral_value(rounding=ROUND_CEILING))

def initialize(path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS team_budget_periods(id TEXT PRIMARY KEY,start REAL NOT NULL,end REAL NOT NULL,total INTEGER NOT NULL,twin_cap INTEGER NOT NULL,staff_cap INTEGER NOT NULL,tools_cap INTEGER NOT NULL,reserve INTEGER NOT NULL,hold INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS team_rates(model TEXT PRIMARY KEY,input_rate TEXT NOT NULL,output_rate TEXT NOT NULL,source TEXT NOT NULL,confirmed_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS team_costs(id TEXT PRIMARY KEY,period_id TEXT NOT NULL,actor TEXT NOT NULL,task_id TEXT,pool TEXT NOT NULL,model TEXT NOT NULL,state TEXT NOT NULL,reserved_text INTEGER NOT NULL,reserved_tools INTEGER NOT NULL,charged_text INTEGER NOT NULL,charged_tools INTEGER NOT NULL,input_tokens INTEGER,output_tokens INTEGER,rate_json TEXT NOT NULL,response_id TEXT,error TEXT,created_at TEXT NOT NULL,finished_at TEXT);
        ''')
def configured(path=p.DEFAULT_DB):
    with readonly(path) as db:return 'team_budget_periods' in tables(db) and bool(db.execute('SELECT 1 FROM team_budget_periods LIMIT 1').fetchone())
def current(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_budget_periods' not in tables(db):return None
        row=db.execute('SELECT * FROM team_budget_periods ORDER BY start DESC LIMIT 1').fetchone();return dict(row) if row else None

def rate(model,path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_rates' not in tables(db):return None
        row=db.execute('SELECT * FROM team_rates WHERE model=?',(model,)).fetchone();return dict(row) if row else None

def set_rate(model,input_rate,output_rate,source,path=p.DEFAULT_DB):
    from .store import text,event
    model=text(model,100,'Exact model identifier',True);source=text(source,1000,'Rate source',True)
    for value in (input_rate,output_rate):
        try:d=Decimal(str(value))
        except InvalidOperation:raise ValueError('Invalid model rate') from None
        if not d.is_finite() or not 0<d<=1000:raise ValueError('Rates must be positive USD per million tokens')
    initialize(path)
    with p.connect(path) as db:
        db.execute('INSERT INTO team_rates(model,input_rate,output_rate,source,confirmed_at) VALUES(?,?,?,?,?) ON CONFLICT(model) DO UPDATE SET input_rate=excluded.input_rate,output_rate=excluded.output_rate,source=excluded.source,confirmed_at=excluded.confirmed_at,version=version+1',(model,str(input_rate),str(output_rate),source,p.stamp()));event(db,'owner','rate_confirmed',{'model':model,'input':str(input_rate),'output':str(output_rate),'source':source})

def create_period(total=200,twin=60,staff=80,tools=20,days=30,path=p.DEFAULT_DB):
    from .store import initialize as init,event
    init(path);amounts=[micro(v) for v in (total,twin,staff,tools)]
    if type(days) is not int or not 1<=days<=31 or not 0<amounts[0]<=micro(200) or sum(amounts[1:])>amounts[0]:raise ValueError('Use a 1–31 day pilot period, total <=$200 and pools within that total')
    old=current(path)
    if old and old['end']>time.time():raise ValueError('An active budget period exists; adjust pools instead of resetting spending')
    ident=uuid4().hex;now=time.time()
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM team_budget_periods WHERE end>?',(now,)).fetchone():raise ValueError('Another budget period is active')
        db.execute('INSERT INTO team_budget_periods(id,start,end,total,twin_cap,staff_cap,tools_cap,reserve) VALUES(?,?,?,?,?,?,?,?)',(ident,now,now+days*86400,*amounts,amounts[0]-sum(amounts[1:])));event(db,'owner','budget_period_created',{'period_id':ident,'total_micro_usd':amounts[0],'days':days})
    return ident

def release_reserve(expected,pool,amount,path=p.DEFAULT_DB):
    from .store import event
    amount=micro(amount)
    if pool not in ('twin','staff','tools') or amount<=0:raise ValueError('Choose a pool and a positive amount')
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM team_budget_periods ORDER BY start DESC LIMIT 1').fetchone()
        if not row or row['version']!=expected or row['reserve']<amount:raise ValueError('Budget changed or reserve is insufficient')
        db.execute('UPDATE team_budget_periods SET '+pool+'_cap='+pool+'_cap+?,reserve=reserve-?,version=version+1 WHERE id=?',(amount,amount,row['id']));event(db,'owner','reserve_released',{'pool':pool,'amount_micro_usd':amount})

def ready(model,path=p.DEFAULT_DB):
    row=current(path);return bool(row and row['start']<=time.time()<row['end'] and not row['hold'] and rate(model,path))

@contextmanager
def scope(actor,task_id=None):
    token=billing_context.set({'actor':actor,'task_id':task_id})
    try:yield
    finally:billing_context.reset(token)

def report(path=p.DEFAULT_DB):
    row=current(path)
    if not row:return {'period':None,'costs':[],'totals':{}}
    with readonly(path) as db:costs=rows(db,'SELECT * FROM team_costs WHERE period_id=? ORDER BY created_at DESC',(row['id'],))
    return {'period':row,'costs':costs[:100],'totals':{'text':sum(c['charged_text'] for c in costs),'tools':sum(c['charged_tools'] for c in costs),'twin':sum(c['charged_text'] for c in costs if c['pool']=='twin'),'staff':sum(c['charged_text'] for c in costs if c['pool']=='staff'),'uncertain':sum(c['state'] in ('reserved','uncertain') for c in costs)}}

def reserve(model,kwargs,endpoint,path=p.DEFAULT_DB):
    card=rate(model,path)
    if not card:raise BudgetBlocked('No confirmed rate card for '+model)
    if endpoint=='chat':
        if set(kwargs)-{'model','messages','response_format','max_completion_tokens','max_tokens','temperature','top_p','presence_penalty','frequency_penalty','seed'}:raise BudgetBlocked('This request has unmetered options')
        if not isinstance(kwargs.get('messages'),list) or any(not isinstance(m,dict) or not isinstance(m.get('content'),str) for m in kwargs['messages']):raise BudgetBlocked('Dollar accounting currently supports text messages only')
        out=kwargs.get('max_completion_tokens',kwargs.get('max_tokens',4000));search=False
    else:
        if set(kwargs)-{'model','instructions','input','tools','tool_choice','max_output_tokens','max_tool_calls'} or not isinstance(kwargs.get('input'),str):raise BudgetBlocked('Dollar accounting currently supports bounded text research only')
        tools=kwargs.get('tools',[])
        if any(t.get('type') not in ('web_search','web_search_preview') for t in tools):raise BudgetBlocked('Unmetered hosted tool')
        search=bool(tools);out=kwargs.get('max_output_tokens',4000)
        if search:kwargs['max_tool_calls']=1
    if type(out) is not int or not 1<=out<=8000:raise BudgetBlocked('Output bound must be 1–8000 tokens')
    if endpoint=='chat':kwargs['max_completion_tokens']=out;kwargs.pop('max_tokens',None)
    else:kwargs['max_output_tokens']=out
    payload=json.dumps(kwargs,ensure_ascii=False).encode()
    if len(payload)>400000:raise BudgetBlocked('Request exceeds the metered input limit')
    # Conservative serialized byte allowance plus protocol overhead; hosted search
    # reserves a full 128k search context. Actual billing can still vary by provider.
    tokens=len(payload)*2+4096+(128000 if search else 0)
    reserved=cost(card['input_rate'],tokens)+cost(card['output_rate'],out)
    reserved=int((Decimal(reserved)*Decimal('1.25')).to_integral_value(rounding=ROUND_CEILING))
    tools_reserve=25000 if search else 0;ident=uuid4().hex;ctx=billing_context.get();pool='twin' if ctx['actor']=='twin' else 'staff'
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');period=db.execute('SELECT * FROM team_budget_periods ORDER BY start DESC LIMIT 1').fetchone()
        if not period or not period['start']<=time.time()<period['end'] or period['hold']:raise BudgetBlocked('Dollar budget period expired, missing or held')
        sums=db.execute("SELECT COALESCE(SUM(charged_text),0) text,COALESCE(SUM(charged_tools),0) tools,COALESCE(SUM(CASE WHEN pool=? THEN charged_text ELSE 0 END),0) pool FROM team_costs WHERE period_id=?",(pool,period['id'])).fetchone()
        if sums['text']+sums['tools']+reserved+tools_reserve>period['total'] or sums['pool']+reserved>period[pool+'_cap'] or sums['tools']+tools_reserve>period['tools_cap']:raise BudgetBlocked('Insufficient unreserved dollars in the budget/pool')
        if ctx['task_id']:
            task=db.execute('SELECT cost_limit FROM team_tasks WHERE id=?',(ctx['task_id'],)).fetchone()
            spent=db.execute('SELECT COALESCE(SUM(charged_text+charged_tools),0) FROM team_costs WHERE task_id=?',(ctx['task_id'],)).fetchone()[0]
            if not task or spent+reserved+tools_reserve>task['cost_limit']:raise BudgetBlocked('Task dollar ceiling reached')
        db.execute("INSERT INTO team_costs(id,period_id,actor,task_id,pool,model,state,reserved_text,reserved_tools,charged_text,charged_tools,rate_json,created_at) VALUES(?,?,?,?,?,?,'reserved',?,?,?,?,?,?)",(ident,period['id'],ctx['actor'],ctx['task_id'],pool,model,reserved,tools_reserve,reserved,tools_reserve,json.dumps(card),p.stamp()))
    return ident

def value(obj,key,default=None):return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)
def settle(ident,response=None,error=None,path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM team_costs WHERE id=?',(ident,)).fetchone()
        if not row or row['state']!='reserved':raise ValueError('Cost reservation already settled')
        usage=value(response,'usage');inp=value(usage,'prompt_tokens',value(usage,'input_tokens'));out=value(usage,'completion_tokens',value(usage,'output_tokens'))
        if error or type(inp) is not int or type(out) is not int or inp<0 or out<0:
            db.execute("UPDATE team_costs SET state='uncertain',error=?,response_id=?,finished_at=? WHERE id=?",(error or 'No usable usage metadata; full reservation retained',value(response,'id'),p.stamp(),ident));return
        card=json.loads(row['rate_json']);charged=cost(card['input_rate'],inp)+cost(card['output_rate'],out)
        toolcost=0
        if row['reserved_tools']:
            output=value(response,'output',[]);calls=sum(value(x,'type')=='web_search_call' for x in output)
            # Missing tool metadata is not proof that no paid search occurred.
            toolcost=max(1,calls)*25000
        exceeded=charged>row['reserved_text'] or toolcost>row['reserved_tools']
        db.execute("UPDATE team_costs SET state=?,charged_text=?,charged_tools=?,input_tokens=?,output_tokens=?,response_id=?,finished_at=? WHERE id=?",('overrun' if exceeded else 'metered',charged,toolcost,inp,out,value(response,'id'),p.stamp(),ident))
        if exceeded:db.execute('UPDATE team_budget_periods SET hold=1,version=version+1 WHERE id=?',(row['period_id'],))

def reconcile(ident,total_dollars,note,path=p.DEFAULT_DB):
    from .store import text,event
    amount=micro(total_dollars);note=text(note,2000,'Provider reconciliation evidence',True)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM team_costs WHERE id=?',(ident,)).fetchone()
        if not row or row['state']=='reserved':raise ValueError('Wait for in-flight requests before reconciliation')
        db.execute("UPDATE team_costs SET state='reconciled',charged_text=?,charged_tools=0,error=? WHERE id=?",(amount,note,ident));event(db,'owner','cost_reconciled',{'cost_id':ident,'micro_usd':amount,'evidence':note})

class Client:
    def __init__(self,actual,path):
        self.actual=actual;self.path=path;self._team_metered=True
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:self.call('chat',kw)))
        self.responses=SimpleNamespace(create=lambda **kw:self.call('responses',kw))
    def call(self,endpoint,kwargs):
        if not configured(self.path):return self.invoke(endpoint,kwargs)
        ctx=billing_context.get()
        if ctx['actor']!='legacy':
            from .store import settings
            kwargs['model']=settings(self.path)['model']
        if endpoint=='responses' and kwargs.get('tools'):
            import inspect
            parameters=inspect.signature(self.actual.responses.create).parameters
            if 'max_tool_calls' not in parameters and not any(p.kind==inspect.Parameter.VAR_KEYWORD for p in parameters.values()):raise BudgetBlocked('The installed SDK cannot bound hosted searches; update it before enabling research')
        ident=reserve(kwargs['model'],kwargs,endpoint,self.path)
        try:response=self.invoke(endpoint,kwargs)
        except Exception as exc:settle(ident,error=type(exc).__name__,path=self.path);raise
        settle(ident,response,path=self.path);return response
    def invoke(self,endpoint,kw):return self.actual.chat.completions.create(**kw) if endpoint=='chat' else self.actual.responses.create(**kw)
    def close(self):
        if hasattr(self.actual,'close'):self.actual.close()

def wrap(actual,path=None):
    path=(getattr(actual,'path',p.DEFAULT_DB) if (getattr(actual,'_team_metered',False) is True) else p.DEFAULT_DB) if path is None else path
    if (getattr(actual,'_team_metered',False) is True):
        if actual.path!=path:raise ValueError('Model client belongs to another project database')
        return actual
    return Client(actual,path)

def recover(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'team_costs' not in tables(db):return 0
    with p.connect(path) as db:return db.execute("UPDATE team_costs SET state='uncertain',error='Worker restarted; full reservation retained',finished_at=? WHERE state='reserved'",(p.stamp(),)).rowcount

def clear_hold(expected,note,path=p.DEFAULT_DB):
    from .store import text,event
    note=text(note,2000,'Inspection/reconciliation note',True)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM team_budget_periods ORDER BY start DESC LIMIT 1').fetchone()
        if not row or row['version']!=expected:raise ValueError('Budget changed; reload')
        totals=db.execute("SELECT COALESCE(SUM(charged_text),0) text,COALESCE(SUM(charged_tools),0) tools,COALESCE(SUM(CASE WHEN pool='twin' THEN charged_text ELSE 0 END),0) twin,COALESCE(SUM(CASE WHEN pool='staff' THEN charged_text ELSE 0 END),0) staff FROM team_costs WHERE period_id=?",(row['id'],)).fetchone()
        if totals['twin']>row['twin_cap'] or totals['staff']>row['staff_cap'] or totals['tools']>row['tools_cap'] or totals['text']+totals['tools']>row['total']:raise ValueError('Reconcile charges or release available reserve before clearing the hold')
        db.execute('UPDATE team_budget_periods SET hold=0,version=version+1 WHERE id=?',(row['id'],))
        event(db,'owner','budget_hold_cleared',{'note':note})
