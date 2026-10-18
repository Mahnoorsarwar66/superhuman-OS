"""Owner-editable shared professional memory; no inferred facts or automatic promotion."""
import hashlib,json,re
from datetime import date
from pathlib import Path
from superhuman.projects import engine as p
from superhuman.departments.store import readonly,tables
STATUSES=('active','historical','unresolved','draft','archived')
CATEGORIES=('foundation','business_history','department','project_context')

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def seed():
    records=json.loads(Path(__file__).with_name('seed.json').read_text(encoding='utf-8'))
    return [dict(r,version=1,updated_at='2026-10-18T00:00:00+00:00',origin='chatgpt_transfer') for r in records]

def initialize(path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS org_memory(id TEXT PRIMARY KEY,title TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,source TEXT NOT NULL,source_date TEXT NOT NULL,review_on TEXT NOT NULL,category TEXT NOT NULL,version INTEGER NOT NULL,updated_at TEXT NOT NULL,origin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS org_memory_history(id TEXT NOT NULL,version INTEGER NOT NULL,snapshot TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(id,version));
CREATE TABLE IF NOT EXISTS org_context_receipts(cost_id TEXT PRIMARY KEY,actor TEXT NOT NULL,signature TEXT NOT NULL,snapshot TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL);''')
        db.execute('BEGIN IMMEDIATE')
        for record in seed():
            cols=tuple(record);cur=db.execute('INSERT OR IGNORE INTO org_memory('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',tuple(record.values()))
            if cur.rowcount:db.execute('INSERT INTO org_memory_history VALUES(?,?,?,?)',(record['id'],1,encode(record),p.stamp()))

def records(path=p.DEFAULT_DB):
    with readonly(path) as db:
        if 'org_memory' not in tables(db):return seed()
        return [dict(r) for r in db.execute('SELECT * FROM org_memory ORDER BY id')]

def get(ident,path=p.DEFAULT_DB):
    row=next((r for r in records(path) if r['id']==ident),None)
    if not row:raise ValueError('Shared memory record not found')
    return row

def clean(value,maximum,label,required=True):
    if not isinstance(value,str):raise ValueError('Invalid '+label)
    value=value.strip()
    if len(value)>maximum or required and not value or any(ord(c)<32 and c not in '\n\r\t' for c in value):raise ValueError(label+' is missing, too long or contains control characters')
    return value

def save(ident,expected,title,content,status,source,source_date='',review_on='',category='foundation',path=p.DEFAULT_DB):
    if not isinstance(ident,str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,79}',ident):raise ValueError('Use a stable lowercase key with letters, numbers, hyphens or underscores')
    if type(expected) is not int or expected<0 or status not in STATUSES or category not in CATEGORIES:raise ValueError('Invalid memory status, category or version')
    title=clean(title,180,'Title');content=clean(content,6000,'Memory');source=clean(source,1000,'Source')
    for value in (source_date,review_on):
        if value and (not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value):raise ValueError('Use dates in YYYY-MM-DD format')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM org_memory WHERE id=?',(ident,)).fetchone()
        if (old['version'] if old else 0)!=expected:raise ValueError('Memory changed; reload the current version')
        record=dict(id=ident,title=title,content=content,status=status,source=source,source_date=source_date,review_on=review_on,category=category,version=expected+1,updated_at=p.stamp(),origin='owner_revision' if old else 'owner_entry')
        cols=tuple(record)
        db.execute('INSERT INTO org_memory('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+') ON CONFLICT(id) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in cols if k!='id'),tuple(record.values()))
        db.execute('INSERT INTO org_memory_history VALUES(?,?,?,?)',(ident,record['version'],encode(record),p.stamp()))
    return record

def history(ident,path=p.DEFAULT_DB):
    with readonly(path) as db:
        return [dict(r) for r in db.execute('SELECT * FROM org_memory_history WHERE id=? ORDER BY version DESC',(ident,))] if 'org_memory_history' in tables(db) else []

def receipt(cost_id,actor,snapshot,state,path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:db.execute('INSERT INTO org_context_receipts VALUES(?,?,?,?,?,?)',(cost_id,actor,snapshot['signature'],encode(snapshot),state,p.stamp()))

def receipt_state(cost_id,state,path=p.DEFAULT_DB):
    with p.connect(path) as db:db.execute('UPDATE org_context_receipts SET state=? WHERE cost_id=?',(state,cost_id))
