"""Replace only recognised upgrade-package files; never edit the installed app."""
import argparse,hashlib,json,os,shutil,tempfile
from pathlib import Path
from datetime import datetime,timezone

NAMES={'patches.py','install_v126.py','gmail_connect.py','reference/production_cli.py','reference/core/orchestrator.py','tests/test_production_cli.py'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.compat-',dir=p.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.chmod(name,0o644);os.replace(name,p)
    finally:Path(name).unlink(missing_ok=True)
def apply(upgrade,source):
    upgrade=upgrade.resolve();manifest=json.loads((source/'repair_manifest.json').read_text());payload=source/'payload'
    if set(manifest)!=NAMES:raise ValueError('Unexpected repair file list')
    if not (upgrade/'upgrade_server.sh').is_file() or not (upgrade/'superhuman/team/engine.py').is_file():raise ValueError('Choose the extracted v1.26 upgrade folder, not the installed app')
    changed=[];before={}
    for name,record in manifest.items():
        target=upgrade/name
        if not (payload/name).is_file() or sha(payload/name)!=record['updated']:raise ValueError('Repair payload changed: '+name)
        if target.is_symlink():raise ValueError('Unexpected linked upgrade file: '+name)
        if target.exists():
            current=sha(target)
            if current not in (record['original'],record['updated']):raise ValueError('Unrecognised upgrade-package file; nothing replaced: '+name)
            if current==record['updated']:continue
        elif record['original'] is not None and name!='gmail_connect.py':raise ValueError('Required upgrade-package file missing: '+name)
        before[name]=target.read_bytes() if target.exists() else None;changed.append(name)
    if not changed:print('Compatibility repair already applied; package checks match.');return
    backup=upgrade/'compatibility-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');backup.mkdir(parents=True,mode=0o700)
    for name,data in before.items():
        if data is not None:write(backup/name,data)
    write(backup/'manifest.json',json.dumps({n:hashlib.sha256(d).hexdigest() if d is not None else None for n,d in before.items()},indent=2).encode())
    try:
        for name in changed:write(upgrade/name,(payload/name).read_bytes())
    except Exception:
        for name,data in before.items():
            if data is None:(upgrade/name).unlink(missing_ok=True)
            else:write(upgrade/name,data)
        raise
    print('Repaired v1.26 upgrade-package compatibility. Installed app/data untouched by this preparation step.')
    print('Original installer-file backup:',backup)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--upgrade-dir',type=Path,required=True);args=parser.parse_args()
    try:apply(args.upgrade_dir,Path(__file__).resolve().parent)
    except (ValueError,OSError,KeyError) as exc:parser.exit(1,str(exc)+'\n')
if __name__=='__main__':main()
