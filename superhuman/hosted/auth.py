"""Opaque server-side sessions. No credentials or session tokens in logs."""
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time

COOKIE='sh_session'
LOGIN_COOKIE='sh_login'


def token_hash(value):return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password,salt):
    return hashlib.scrypt(password.encode('utf-8'),salt=bytes.fromhex(salt),n=32768,r=8,p=3,maxmem=64*1024*1024).hex()


class Store:
    def __init__(self,path):self.path=Path(path)
    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            os.chmod(self.path,0o600)
            db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=30000')
            with db:yield db
        finally:db.close()
    def initialize(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY CHECK(id=1),username TEXT NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,kind TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(ip_hash TEXT NOT NULL,at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS attempts_at ON attempts(at);
            ''')
    def configured(self):
        if not self.path.is_file():return False
        try:
            with self.connect() as db:return db.execute('SELECT 1 FROM owner WHERE id=1').fetchone() is not None
        except sqlite3.OperationalError:return False
    def setup(self,username,password):
        if not username.strip() or len(username)>80:raise ValueError('Username must contain 1 to 80 characters')
        if not 12<=len(password)<=1024:raise ValueError('Use a password of 12 to 1024 characters')
        salt=secrets.token_hex(16);hashed=password_hash(password,salt)
        self.initialize()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM owner').fetchone():raise ValueError('Owner already configured; use password reset')
            db.execute('INSERT INTO owner VALUES(1,?,?,?)',(username.strip(),salt,hashed))
    def new_session(self,kind='owner',duration=86400):
        now=time.time();raw=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            if kind=='login':
                db.execute("DELETE FROM sessions WHERE kind='login' AND token_hash NOT IN (SELECT token_hash FROM sessions WHERE kind='login' ORDER BY created DESC LIMIT 99)")
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',(token_hash(raw),csrf,kind,now,now+duration,now))
        return raw,{'csrf':csrf,'kind':kind,'created':now,'expires':now+duration,'last_seen':now}
    def session(self,raw,kind='owner',idle=43200):
        if not raw or len(raw)>200:return None
        now=time.time()
        with self.connect() as db:
            row=db.execute('SELECT * FROM sessions WHERE token_hash=? AND kind=?',(token_hash(raw),kind)).fetchone()
            if not row:return None
            if row['expires']<now or row['last_seen']+idle<now:
                db.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(raw),));return None
            db.execute('UPDATE sessions SET last_seen=? WHERE token_hash=?',(now,token_hash(raw)))
            return dict(row)
    def revoke(self,raw):
        if raw:
            with self.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(raw),))
    def login(self,username,password,ip):
        now=time.time();key=token_hash(ip)
        # Serialize the rate check and expensive hash calculation across workers.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE at<?',(now-900,))
            local=db.execute('SELECT COUNT(*) FROM attempts WHERE ip_hash=?',(key,)).fetchone()[0]
            total=db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
            if local>=5 or total>=30:return 'limited'
            owner=db.execute('SELECT * FROM owner WHERE id=1').fetchone()
            good=False
            if owner and len(password)<=1024:
                supplied=password_hash(password,owner['salt'])
                good=hmac.compare_digest(supplied,owner['password_hash']) & hmac.compare_digest(username.encode('utf-8'),owner['username'].encode('utf-8'))
            if good:db.execute('DELETE FROM attempts WHERE ip_hash=?',(key,))
            else:db.execute('INSERT INTO attempts VALUES(?,?)',(key,now))
            return 'ok' if good else 'invalid'
    def reset_password(self,password):
        if not 12<=len(password)<=1024:raise ValueError('Use a password of 12 to 1024 characters')
        salt=secrets.token_hex(16);hashed=password_hash(password,salt)
        with self.connect() as db:
            cur=db.execute('UPDATE owner SET salt=?,password_hash=? WHERE id=1',(salt,hashed))
            if not cur.rowcount:raise ValueError('Owner is not configured')
            db.execute('DELETE FROM sessions');db.execute('DELETE FROM attempts')
