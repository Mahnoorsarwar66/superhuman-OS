"""Concurrent SQLite notes, optimistic edits and history; legacy memory is untouched."""
from contextlib import contextmanager
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

KINDS = ('fact', 'decision', 'preference', 'feedback', 'update')
STATUSES = ('proposed', 'confirmed', 'archived')
SOURCES = ('user', 'document', 'inferred')
GENRES = ('all', 'general', 'template', 'agenda', 'consolidation', 'outreach',
          'admissions_writing', 'writing', 'personal_writing', 'decision', 'research')
FIELDS = ('scope', 'kind', 'title', 'content', 'source_type', 'source', 'status',
          'sensitive', 'genre', 'expires_on')


def default_path():
    return Path(os.getenv('SUPERHUMAN_KNOWLEDGE_DB', 'data/knowledge/notes.db')).resolve()


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    name = os.getenv('SUPERHUMAN_TIMEZONE', 'Asia/Karachi')
    try:
        zone = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Windows may not ship the IANA database. Pakistan currently uses UTC+5.
        if name == 'Asia/Karachi':
            zone = timezone(timedelta(hours=5))
        elif name == 'UTC':
            zone = timezone.utc
        else:
            raise ValueError('Timezone data missing; choose UTC/Asia/Karachi or install tzdata') from None
    return datetime.now(zone).date()


def validate(values):
    value = {key: values.get(key, '') for key in FIELDS}
    for key in ('scope', 'kind', 'title', 'content', 'source_type', 'source', 'status', 'genre', 'expires_on'):
        if not isinstance(value[key], str):
            raise ValueError('Invalid ' + key)
        value[key] = value[key].strip()
    value['scope'] = value['scope'].lower()
    if not re.fullmatch(r'[a-z0-9_]{1,64}', value['scope']):
        raise ValueError('Choose a workstream or global scope')
    if value['kind'] not in KINDS or value['status'] not in STATUSES:
        raise ValueError('Invalid note kind or status')
    if value['source_type'] not in SOURCES or value['genre'] not in GENRES:
        raise ValueError('Invalid source type or task genre')
    if not 1 <= len(value['title']) <= 180 or not 1 <= len(value['content']) <= 4000:
        raise ValueError('Use a title of 1–180 characters and a note of 1–4000 characters')
    if len(value['source']) > 500 or any('\x00' in value[k] for k in value if isinstance(value[k], str)):
        raise ValueError('Invalid source or null character')
    if value['sensitive'] not in (0, 1, False, True):
        raise ValueError('Invalid sensitive flag')
    value['sensitive'] = int(value['sensitive'])
    if value['expires_on']:
        try:
            if date.fromisoformat(value['expires_on']).isoformat() != value['expires_on']:
                raise ValueError()
        except ValueError:
            raise ValueError('Use an expiry date in YYYY-MM-DD format') from None
    return value


def fingerprint(note):
    return hashlib.sha256(json.dumps({key: note[key] for key in FIELDS}, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


class Store:
    def __init__(self, path=None):
        self.path = Path(path).resolve() if path is not None else default_path()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()
        os.chmod(self.path, 0o600)

    def initialize(self):
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS notes(
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL,
                    title TEXT NOT NULL, content TEXT NOT NULL, source_type TEXT NOT NULL,
                    source TEXT NOT NULL, status TEXT NOT NULL, sensitive INTEGER NOT NULL,
                    genre TEXT NOT NULL, expires_on TEXT NOT NULL, version INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS note_history(
                    note_id TEXT NOT NULL REFERENCES notes(id), version INTEGER NOT NULL,
                    snapshot TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(note_id, version));
            ''')

    def add(self, scope, kind, title, content, source_type='user', source='',
            status='proposed', sensitive=False, genre='all', expires_on=''):
        values = validate(locals())
        self.initialize()
        record = dict(id=uuid4().hex, **values, version=1, created_at=now(), updated_at=now())
        columns = tuple(record)
        with self.connect() as db:
            db.execute('INSERT INTO notes(' + ','.join(columns) + ') VALUES(' +
                       ','.join('?' for _ in columns) + ')', tuple(record.values()))
            self._history(db, record)
        return record

    @staticmethod
    def _history(db, record):
        db.execute('INSERT INTO note_history VALUES(?,?,?,?)',
                   (record['id'], record['version'], json.dumps(record, ensure_ascii=False), now()))

    def get(self, note_id):
        if not self.path.exists():
            raise ValueError('Note not found')
        with self.connect() as db:
            row = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
        if row is None:
            raise ValueError('Note not found')
        return dict(row)

    def list(self, scope=None, status=None, query='', limit=200, offset=0):
        if not self.path.exists():
            return []
        if not isinstance(limit, int) or not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('Invalid page size')
        clauses, values = [], []
        if scope:
            clauses.append('scope=?'); values.append(scope)
        if status:
            if status not in STATUSES:
                raise ValueError('Invalid status')
            clauses.append('status=?'); values.append(status)
        if query:
            # SQL parameters and escaped LIKE wildcards make search literal.
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            values.extend(['%' + escaped + '%'] * 2)
        sql = 'SELECT * FROM notes' + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
        sql += ' ORDER BY updated_at DESC,id LIMIT ? OFFSET ?'
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, (*values, limit, offset))]

    def candidates(self, scope):
        """Read all potentially usable notes; no arbitrary recent-page cutoff."""
        if not self.path.exists():
            return []
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM notes WHERE status='confirmed' AND scope IN ('global',?) "
                'ORDER BY updated_at DESC,id', (scope,))]

    def update(self, note_id, expected_version, **changes):
        if not changes or set(changes) - set(FIELDS):
            raise ValueError('Unsupported note change')
        self.initialize()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
            if row is None:
                raise ValueError('Note not found')
            record = dict(row)
            if record['version'] != expected_version:
                raise ValueError('This note changed in another window. Reload before saving.')
            values = validate({**record, **changes})
            record.update(values, version=record['version'] + 1, updated_at=now())
            db.execute('UPDATE notes SET ' + ','.join(k + '=?' for k in FIELDS) +
                       ',version=?,updated_at=? WHERE id=?',
                       (*[record[k] for k in FIELDS], record['version'], record['updated_at'], note_id))
            self._history(db, record)
        return record

    def history(self, note_id):
        self.get(note_id)
        with self.connect() as db:
            return [json.loads(row['snapshot']) for row in db.execute(
                'SELECT snapshot FROM note_history WHERE note_id=? ORDER BY version DESC', (note_id,))]
