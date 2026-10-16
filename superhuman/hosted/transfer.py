"""Private deployment bundle: consistent SQLite copies, integrity and path rebasing.

Do not publish bundles to Git. They contain the owner's working data.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import sqlite3
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED

PATH_KEYS={'path','file','filename','directory','output','output_path','final_path','old_output','new_output',
           'stage_archive','archive','source_path','project_db','workspace_path','source','files'}
DB_FIELDS={'output','output_path','old_output','new_output','source'}
JSON_FIELDS={'result_json','invalidated_json','original_json','detail_json'}


def digest(raw):return hashlib.sha256(raw).hexdigest()


def sqlite_file(path):
    with Path(path).open('rb') as f:return f.read(16)==b'SQLite format 3\x00'


def bundle(root,output):
    root=Path(root).resolve();output=Path(output).resolve()
    if not (root/'superhuman/hosted').is_dir():raise ValueError('Install v1.9 first')
    if output.is_relative_to(root/'data'):raise ValueError('Save the transfer archive outside data/')
    if output.exists():raise ValueError('Output already exists; choose a new filename')
    files=[]
    for path in (root/'superhuman').rglob('*.py'):
        if '__pycache__' not in path.parts:files.append(path)
    for name in ('.gitignore','requirements.txt','requirements-v19.txt'):
        if (root/name).is_file():files.append(root/name)
    if (root/'superhuman-deploy-v19').exists():files.extend(p for p in (root/'superhuman-deploy-v19').rglob('*') if p.is_file())
    if (root/'data').exists():files.extend(p for p in (root/'data').rglob('*') if p.is_file())
    output.parent.mkdir(parents=True,exist_ok=True);manifest={'version':1,'original_root':str(root),'files':[]}
    temporary=output.with_suffix('.tmp')
    if temporary.exists():raise ValueError('Temporary export exists; inspect it before retrying')
    try:
        with tempfile.TemporaryDirectory() as directory,ZipFile(temporary,'w',ZIP_DEFLATED) as archive:
            for index,path in enumerate(sorted(set(files))):
                relative=path.relative_to(root)
                if path.is_symlink():raise ValueError('Resolve symbolic links before transfer: '+str(relative))
                if any(part.startswith('.env') or part in ('.git','.venv','__pycache__') for part in relative.parts):continue
                if path.name.endswith(('-wal','-shm','-journal','.runtime.lock')):continue
                if sqlite_file(path):
                    copy=Path(directory)/str(index)
                    with closing(sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(copy)) as dst:src.backup(dst)
                    raw=copy.read_bytes()
                else:raw=path.read_bytes()
                archive.writestr(relative.as_posix(),raw)
                manifest['files'].append({'name':relative.as_posix(),'sha256':digest(raw),'bytes':len(raw)})
            archive.writestr('bundle-manifest.json',json.dumps(manifest,indent=2))
        os.chmod(temporary,0o600);temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True);raise
    return {'file':str(output),'files':len(manifest['files']),'private_data':True,'api_calls':0}


def rebase(value,old_root,new_root,key=None):
    if isinstance(value,dict):return {k:rebase(v,old_root,new_root,k) for k,v in value.items()}
    if isinstance(value,list):return [rebase(v,old_root,new_root,key) for v in value]
    if not isinstance(value,str) or key not in PATH_KEYS:return value
    normalized=value.replace('\\','/');prefix=old_root.replace('\\','/').rstrip('/')
    if normalized.casefold()==prefix.casefold():return str(new_root)
    if normalized.casefold().startswith(prefix.casefold()+'/'):
        relative=PurePosixPath(normalized[len(prefix)+1:])
        if '..' in relative.parts:raise ValueError('Invalid saved metadata path')
        return str(Path(new_root).joinpath(*relative.parts))
    if normalized.startswith('data/') and '\\' in value:
        if '..' in PurePosixPath(normalized).parts:raise ValueError('Invalid saved relative path')
        return normalized
    return value


def migrate_state(stage,old_root,new_root):
    data=Path(stage)/'data'
    if not data.exists():return
    for path in data.rglob('*'):
        if not path.is_file():continue
        if sqlite_file(path):
            # Uploaded source databases are not supported inputs; only known
            # application databases directly in data/ and data/hosted/ migrate.
            if path.parent not in (data,data/'hosted'):continue
            with closing(sqlite3.connect(path)) as db:
                db.row_factory=sqlite3.Row
                tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for table in tables:
                    quoted='"'+table.replace('"','""')+'"'
                    columns={r[1] for r in db.execute('PRAGMA table_info('+quoted+')')}
                    fields=columns&(DB_FIELDS|JSON_FIELDS)
                    if not fields:continue
                    for row in db.execute('SELECT rowid AS _transfer_rowid,* FROM '+quoted).fetchall():
                        changed={}
                        for field in fields:
                            value=row[field]
                            if value is None:continue
                            if field in JSON_FIELDS:
                                try:
                                    parsed=json.loads(value);updated=rebase(parsed,old_root,new_root)
                                    if updated!=parsed:changed[field]=json.dumps(updated)
                                except (json.JSONDecodeError,TypeError):continue
                            else:
                                updated=rebase(value,old_root,new_root,field)
                                if updated!=value:changed[field]=updated
                        if changed:
                            sql='UPDATE '+quoted+' SET '+','.join('"'+k+'"=?' for k in changed)+' WHERE rowid=?'
                            db.execute(sql,(*changed.values(),row['_transfer_rowid']))
                if path==data/'hosted/auth.sqlite3':db.execute('DELETE FROM sessions')
                db.commit()
        elif path.suffix.lower()=='.json':
            try:
                raw=path.read_text(encoding='utf-8');parsed=json.loads(raw);updated=rebase(parsed,old_root,new_root)
                if updated!=parsed:path.write_text(json.dumps(updated,indent=2),encoding='utf-8')
            except (UnicodeError,json.JSONDecodeError):continue


def restore(archive,target):
    target=Path(target).resolve()
    if target.exists() and any(target.iterdir()):raise ValueError('Restore requires an empty target directory')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.superhuman-restore-',dir=target.parent) as temporary:
        stage=Path(temporary)/'root';stage.mkdir(mode=0o700)
        with ZipFile(archive) as z:
            entries=z.infolist()
            if len(entries)>50000 or sum(x.file_size for x in entries)>1024*1024*1024:
                raise ValueError('Transfer archive exceeds 1 GB / 50,000 entries')
            names=[x.filename for x in entries]
            if len(set(names))!=len(names):raise ValueError('Duplicate archive paths')
            manifest=json.loads(z.read('bundle-manifest.json'))
            expected={f['name']:f for f in manifest['files']}
            if set(names)!=set(expected)|{'bundle-manifest.json'}:raise ValueError('Archive does not match its manifest')
            for name,item in expected.items():
                rel=PurePosixPath(name)
                if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name or name=='bundle-manifest.json':
                    raise ValueError('Invalid transfer archive path')
                if rel.parts[0] not in ('superhuman','data','superhuman-deploy-v19','.gitignore','requirements.txt','requirements-v19.txt'):
                    raise ValueError('Unexpected archive content')
                raw=z.read(name)
                if len(raw)!=item['bytes'] or digest(raw)!=item['sha256']:raise ValueError('Archive integrity check failed')
                dest=stage.joinpath(*rel.parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            migrate_state(stage,manifest['original_root'],target)
            if (stage/'data').is_dir():os.chmod(stage/'data',0o700)
        if target.exists():target.rmdir()
        stage.rename(target)
    return {'restored_to':str(target),'sessions_revoked':True,'api_calls':0}
