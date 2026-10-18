"""Conversation state in the canonical project DB, for atomic task approval."""
import hashlib
import json
import sqlite3
from uuid import uuid4
from superhuman.projects import engine as p
from superhuman.runtime import engine as r


def initialize(path=p.DEFAULT_DB):
    r.initialize(path)
    with p.connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS dialogue_threads(
            id TEXT PRIMARY KEY,scope TEXT NOT NULL,title TEXT NOT NULL,
            max_calls INTEGER NOT NULL,used_calls INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dialogue_turns(
            id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
            submission_key TEXT NOT NULL UNIQUE,user_text TEXT NOT NULL,
            status TEXT NOT NULL,reply TEXT,raw_response TEXT,context_json TEXT,
            error TEXT,token TEXT,created_at TEXT NOT NULL,finished_at TEXT,
            UNIQUE(thread_id,ordinal));
        CREATE TABLE IF NOT EXISTS dialogue_suggestions(
            id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,turn_id TEXT NOT NULL,
            kind TEXT NOT NULL,title TEXT NOT NULL,details TEXT NOT NULL,
            rationale TEXT NOT NULL,status TEXT NOT NULL,proposal_hash TEXT NOT NULL,
            approved_hash TEXT,project_id TEXT,created_at TEXT NOT NULL,
            decided_at TEXT);
        ''')


def event(db, action, thread_id, turn_id=None, project_id=None, **metadata):
    db.execute('INSERT INTO runtime_events(project_id,task_id,action,detail_json,created_at) VALUES(?,NULL,?,?,?)',
               (project_id, action, json.dumps(dict(thread_id=thread_id, turn_id=turn_id, **metadata)), p.stamp()))


def scopes():
    from superhuman.core.router import WORKSTREAMS
    return tuple(WORKSTREAMS)


def text(value, maximum, label):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError(f'{label} must contain 1–{maximum} characters')
    return value.strip()


def get(thread_id, path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        row = db.execute('SELECT * FROM dialogue_threads WHERE id=?', (thread_id,)).fetchone()
    if row is None:
        raise ValueError('Conversation not found')
    return dict(row)


def create(scope, title, max_calls=20, path=p.DEFAULT_DB):
    if scope not in scopes() or type(max_calls) is not int or not 1 <= max_calls <= 100:
        raise ValueError('Choose a valid workstream and request limit from 1 to 100')
    title = text(title, 180, 'Conversation title')
    initialize(path); thread_id = uuid4().hex
    with p.connect(path) as db:
        db.execute('INSERT INTO dialogue_threads VALUES(?,?,?, ?,0,?,?)',
                   (thread_id, scope, title, max_calls, p.stamp(), p.stamp()))
        event(db, 'conversation_created', thread_id)
    return thread_id


def listing(path=p.DEFAULT_DB, limit=50, offset=0):
    initialize(path)
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError('Invalid page size')
    with p.connect(path) as db:
        return [dict(row) for row in db.execute('SELECT * FROM dialogue_threads ORDER BY updated_at DESC,id LIMIT ? OFFSET ?', (limit, offset))]


def turns(thread_id, path=p.DEFAULT_DB, limit=50, before=None):
    get(thread_id, path)
    sql = 'SELECT * FROM dialogue_turns WHERE thread_id=?'
    args = [thread_id]
    if before is not None:
        sql += ' AND ordinal<?'; args.append(before)
    sql += ' ORDER BY ordinal DESC LIMIT ?'; args.append(limit)
    with p.connect(path) as db:
        return list(reversed([dict(row) for row in db.execute(sql, args)]))


def turn(turn_id, path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        row = db.execute('SELECT * FROM dialogue_turns WHERE id=?', (turn_id,)).fetchone()
    if row is None:
        raise ValueError('Message not found')
    return dict(row)


def send(thread_id, user_text, submission_key, path=p.DEFAULT_DB):
    user_text = text(user_text, 6000, 'Message')
    if not isinstance(submission_key, str) or not 16 <= len(submission_key) <= 80:
        raise ValueError('Invalid submission key. Reload the page.')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM dialogue_turns WHERE submission_key=?', (submission_key,)).fetchone()
        if old:
            if old['thread_id'] != thread_id or old['user_text'] != user_text:
                raise ValueError('Submission key was already used with different content')
            return old['id']
        thread = db.execute('SELECT * FROM dialogue_threads WHERE id=?', (thread_id,)).fetchone()
        if thread is None:
            raise ValueError('Conversation not found')
        from superhuman.departments.store import tables
        if 'hub_rooms' in tables(db) and db.execute('SELECT 1 FROM hub_rooms WHERE id=? AND archived=1',(thread_id,)).fetchone():raise ValueError('Restore this archived conversation before sending')
        if db.execute("SELECT 1 FROM dialogue_turns WHERE thread_id=? AND status IN ('queued','running')", (thread_id,)).fetchone():
            raise ValueError('Wait for the current reply or cancel the queued message first')
        if thread['used_calls'] >= thread['max_calls']:
            raise ValueError('Conversation request limit reached. Explicitly increase it before sending.')
        ordinal = db.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM dialogue_turns WHERE thread_id=?', (thread_id,)).fetchone()[0]
        tid = uuid4().hex
        db.execute("INSERT INTO dialogue_turns(id,thread_id,ordinal,submission_key,user_text,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
                   (tid, thread_id, ordinal, submission_key, user_text, p.stamp()))
        db.execute('UPDATE dialogue_threads SET updated_at=? WHERE id=?', (p.stamp(), thread_id))
        event(db, 'conversation_message_queued', thread_id, tid)
    return tid


def set_budget(thread_id, maximum, path=p.DEFAULT_DB):
    if type(maximum) is not int or not 1 <= maximum <= 100:
        raise ValueError('Limit must be from 1 to 100')
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT used_calls FROM dialogue_threads WHERE id=?', (thread_id,)).fetchone()
        if row is None or maximum < row['used_calls']:
            raise ValueError('Limit cannot be below attempts already reserved')
        db.execute('UPDATE dialogue_threads SET max_calls=?,updated_at=? WHERE id=?', (maximum, p.stamp(), thread_id))
        event(db, 'conversation_budget_changed', thread_id, maximum=maximum)


def cancel(thread_id, turn_id, path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        changed = db.execute("UPDATE dialogue_turns SET status='cancelled',finished_at=? WHERE id=? AND thread_id=? AND status='queued'", (p.stamp(), turn_id, thread_id))
        if not changed.rowcount:
            raise ValueError('Only a queued message can be cancelled. An active request may already be billed.')
        event(db, 'conversation_message_cancelled', thread_id, turn_id)


def recover_running(path=p.DEFAULT_DB):
    """Call once while holding the existing global worker lock, after restart."""
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute("SELECT id,thread_id FROM dialogue_turns WHERE status='running'").fetchall()
        for row in rows:
            db.execute("UPDATE dialogue_turns SET status='interrupted',error=?,finished_at=? WHERE id=?",
                       ('Worker restarted during this request; no automatic retry. The attempt may have been billed.', p.stamp(), row['id']))
            event(db, 'conversation_message_interrupted', row['thread_id'], row['id'])
    return len(rows)


def claim(path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT t.*,c.scope,c.title AS thread_title,c.used_calls,c.max_calls FROM dialogue_turns t JOIN dialogue_threads c ON c.id=t.thread_id WHERE t.status='queued' ORDER BY t.created_at,t.id LIMIT 1").fetchone()
        if row is None:
            return None
        row = dict(row)
        if row['used_calls'] >= row['max_calls']:
            db.execute("UPDATE dialogue_turns SET status='budget_blocked',error='Conversation request limit reached',finished_at=? WHERE id=?", (p.stamp(), row['id']))
            return {'id': row['id'], 'thread_id': row['thread_id'], 'budget_blocked': True}
        token = uuid4().hex
        db.execute("UPDATE dialogue_turns SET status='running',token=? WHERE id=?", (token, row['id']))
        db.execute('UPDATE dialogue_threads SET used_calls=used_calls+1,updated_at=? WHERE id=?', (p.stamp(), row['thread_id']))
        event(db, 'conversation_request_reserved', row['thread_id'], row['id'])
        row['token'] = token
    return row


def proposal_hash(kind, title, details, rationale):
    return hashlib.sha256(json.dumps([kind, title, details, rationale], ensure_ascii=False).encode()).hexdigest()


def finish(claimed, reply, proposals, raw, context, error=None, path=p.DEFAULT_DB):
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if not error and context.get('execution_plan'):
            from superhuman.conversationwork.bridge import commit
            current=db.execute("SELECT token,status FROM dialogue_turns WHERE id=?",(claimed['id'],)).fetchone()
            if not current or current['token']!=claimed['token'] or current['status']!='running':raise ValueError('Request ownership changed; work was not queued')
            work_reply=commit(db,claimed,context['execution_plan'],context,path)
            if work_reply:reply=work_reply;proposals=[]
        status = 'failed' if error else 'done'
        changed = db.execute("UPDATE dialogue_turns SET status=?,reply=?,raw_response=?,context_json=?,error=?,finished_at=? WHERE id=? AND token=? AND status='running'",
                             (status, reply, raw, json.dumps(context, ensure_ascii=False), error, p.stamp(), claimed['id'], claimed['token']))
        if not changed.rowcount:
            raise ValueError('Request ownership changed; reply was not committed')
        for value in proposals if not error else []:
            db.execute("INSERT INTO dialogue_suggestions(id,thread_id,turn_id,kind,title,details,rationale,status,proposal_hash,created_at) VALUES(?,?,?,?,?,?,?,'proposed',?,?)",
                       (uuid4().hex, claimed['thread_id'], claimed['id'], value['kind'], value['title'], value['details'], value['rationale'],
                        proposal_hash(value['kind'], value['title'], value['details'], value['rationale']), p.stamp()))
        db.execute('UPDATE dialogue_threads SET updated_at=? WHERE id=?', (p.stamp(), claimed['thread_id']))
        event(db, 'conversation_reply_' + status, claimed['thread_id'], claimed['id'])


def suggestions(thread_id, path=p.DEFAULT_DB, turn_ids=None):
    get(thread_id, path)
    sql = 'SELECT s.*,c.scope FROM dialogue_suggestions s JOIN dialogue_threads c ON c.id=s.thread_id WHERE s.thread_id=?'
    args = [thread_id]
    if turn_ids is not None:
        if not turn_ids: return []
        sql += ' AND s.turn_id IN (' + ','.join('?' for _ in turn_ids) + ')'; args.extend(turn_ids)
    with p.connect(path) as db:
        return [dict(row) for row in db.execute(sql + ' ORDER BY s.created_at,s.id', args)]


def approve(thread_id,suggestion_id,expected_hash,title,details,path=p.DEFAULT_DB,scope=None):
    from superhuman.taskdesk.store import approve as routed_approve
    return routed_approve(thread_id,suggestion_id,expected_hash,title,details,path=path,scope=scope)


def dismiss(thread_id, suggestion_id, expected_hash, path=p.DEFAULT_DB):
    initialize(path)
    with p.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM dialogue_suggestions WHERE id=? AND thread_id=?', (suggestion_id, thread_id)).fetchone()
        if row is None or row['proposal_hash'] != expected_hash:
            raise ValueError('Suggestion changed or unavailable')
        if row['status'] == 'dismissed': return
        if row['status'] != 'proposed': raise ValueError('Approved work cannot be dismissed here')
        db.execute("UPDATE dialogue_suggestions SET status='dismissed',decided_at=? WHERE id=?", (p.stamp(), suggestion_id))
        event(db, 'conversation_task_dismissed', thread_id, row['turn_id'], suggestion_id=suggestion_id)
