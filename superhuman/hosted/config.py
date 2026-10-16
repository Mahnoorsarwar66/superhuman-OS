from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def origin(value):
    u=urlsplit(value)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('Use an http:// or https:// origin with no path, credentials or query')
    host=u.hostname.lower()
    if any(c.isspace() for c in host) or host.endswith('.') or '*' in host:raise ValueError('Invalid hostname')
    try:port=u.port
    except ValueError as exc:raise ValueError('Invalid origin port') from exc
    authority=('['+host+']') if ':' in host else host
    if port is not None and port!=(443 if u.scheme=='https' else 80):authority+=':'+str(port)
    return u.scheme+'://'+authority


def config_path():return Path(os.getenv('SUPERHUMAN_HOSTED_CONFIG','data/hosted/config.json')).resolve()


@dataclass(frozen=True)
class Settings:
    public_origin:str
    tunnel:bool=False
    state_dir:Path=Path('data/hosted')
    session_seconds:int=86400
    idle_seconds:int=43200
    max_body:int=12*1024*1024
    def __post_init__(self):
        normalized=origin(self.public_origin)
        object.__setattr__(self,'public_origin',normalized)
        object.__setattr__(self,'state_dir',Path(self.state_dir).resolve())
        if not 600<=self.session_seconds<=604800 or not 300<=self.idle_seconds<=self.session_seconds:
            raise ValueError('Invalid session duration')
        if not 1024<=self.max_body<=20*1024*1024:raise ValueError('Invalid upload limit')
        if normalized.startswith('http://'):
            if not self.tunnel or urlsplit(normalized).hostname not in ('127.0.0.1','localhost','::1'):
                raise ValueError('HTTP is allowed only for explicit loopback tunnel testing')
        elif self.tunnel:raise ValueError('Tunnel mode uses a loopback HTTP origin; use HTTPS mode for a domain')
    @property
    def secure_cookie(self):return self.public_origin.startswith('https://')
    @property
    def auth_db(self):return self.state_dir/'auth.sqlite3'


def load(path=None):
    path=Path(path or config_path())
    value=json.loads(path.read_text(encoding='utf-8'))
    return Settings(public_origin=value['public_origin'],tunnel=value.get('tunnel',False),state_dir=path.parent,
                    session_seconds=value.get('session_seconds',86400),idle_seconds=value.get('idle_seconds',43200))


def save(settings,path=None):
    path=Path(path or config_path());path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    value={'public_origin':settings.public_origin,'tunnel':settings.tunnel,
           'session_seconds':settings.session_seconds,'idle_seconds':settings.idle_seconds}
    try:
        with temporary.open('w',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2)
        os.chmod(temporary,0o600);temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
