"""Guarded v1.37 → v1.38 source repair; data remains on the installed host."""
import argparse,ast,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone
SOURCE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name('.'+p.name+'.v138.tmp')
 try:
  tmp.write_bytes(data)
  if p.exists():os.chmod(tmp,p.stat().st_mode & 0o777)
  os.replace(tmp,p)
 finally:tmp.unlink(missing_ok=True)
def matches(p,reference):
 if not p.is_file():return False
 if p.suffix=='.py':
  try:return ast.dump(ast.parse(p.read_text()),include_attributes=False)==ast.dump(ast.parse(reference.read_text()),include_attributes=False)
  except (SyntaxError,UnicodeError):return False
 return p.read_bytes()==reference.read_bytes()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--rollback');a=parser.parse_args()
 if sum([a.preflight,a.check,bool(a.rollback)])>1:parser.error('Choose one action')
 root=Path.cwd().resolve();files=json.loads((SOURCE/'FILES.json').read_text());marker=root/'backups/v138-installed.json'
 try:
  if a.rollback:
   backup=Path(a.rollback).resolve()
   if not backup.is_relative_to(root/'backups'):raise ValueError('Choose the v1.38 backup inside this app/backups')
   m=json.loads((backup/'manifest.json').read_text())
   if m['root']!=str(root) or set(m['installed'])!=set(files):raise ValueError('Backup belongs to another installation')
   for name,sha in m['installed'].items():
    if not (root/'superhuman'/name).is_file() or digest(root/'superhuman'/name)!=sha:raise ValueError('Changed installed file; rollback refused: '+name)
   for name,sha in m['before'].items():
    if sha and digest(backup/'source'/name)!=sha:raise ValueError('Backup changed: '+name)
   sys.path.insert(0,str(root))
   from superhuman.hosted import jobs
   jobs.pause(True)
   for name,sha in m['before'].items():
    dest=root/'superhuman'/name
    if sha:atomic(dest,(backup/'source'/name).read_bytes())
    else:dest.unlink()
   marker.unlink(missing_ok=True)
   print('Code rolled back to v1.37; records and accounting retained. Worker paused. Review queued discussions before resuming.');return
  for name,item in files.items():
   if digest(SOURCE/'payload'/name)!=item['after']:raise ValueError('Upgrade payload changed: '+name)
  if marker.exists():
   m=json.loads(marker.read_text())
   if m['root']!=str(root) or set(m['installed'])!=set(files):raise ValueError('Different v1.38 installation manifest')
   for name,sha in m['installed'].items():
    if sha!=files[name]['after'] or not (root/'superhuman'/name).is_file() or digest(root/'superhuman'/name)!=sha:raise ValueError('Installed source changed: '+name)
   print('v1.38 already installed; exact source verified. No changes made.');return
  for name,item in files.items():
   p=root/'superhuman'/name
   if item['before'] is None:
    if p.exists():raise ValueError('New repair path already exists: '+name)
   elif not matches(p,SOURCE/'reference'/name):raise ValueError('Unrecognised v1.37 source: '+name+'; nothing overwritten')
  before={n:digest(root/'superhuman'/n) if (root/'superhuman'/n).is_file() else None for n in files}
  if a.preflight:print('v1.38 preflight passed; source checks only, no changes.');return
  with tempfile.TemporaryDirectory(prefix='superhuman-v138-check-') as directory:
   stage=Path(directory);shutil.copytree(root/'superhuman',stage/'superhuman',ignore=shutil.ignore_patterns('__pycache__','.env','.env.*','*.bak','installation.json'))
   for name in files:atomic(stage/'superhuman'/name,(SOURCE/'payload'/name).read_bytes())
   env=dict(os.environ);env.pop('OPENAI_API_KEY',None)
   for key in list(env):
    if key.startswith('SUPERHUMAN_'):env.pop(key)
   env['PYTHONPATH']=str(stage)+os.pathsep+str(SOURCE/'tests');env['PYTHONDONTWRITEBYTECODE']='1'
   result=subprocess.run([sys.executable,str(SOURCE/'run_checks.py')],cwd=stage,env=env)
   if result.returncode:raise ValueError('Staged regression checks failed; installed source and data unchanged')
  for name,sha in before.items():
   if (digest(root/'superhuman'/name) if (root/'superhuman'/name).exists() else None)!=sha:raise ValueError('Source changed during checks: '+name)
   if digest(SOURCE/'payload'/name)!=files[name]['after']:raise ValueError('Payload changed during checks: '+name)
  if a.check:print('v1.38 checks passed. No installation or provider calls.');return
  backup=root/'backups'/('v1.38-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir(parents=True,mode=0o700)
  for name,sha in before.items():
   if sha:dest=backup/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/'superhuman'/name,dest)
  try:
   for name in files:atomic(root/'superhuman'/name,(SOURCE/'payload'/name).read_bytes())
   manifest=dict(version='1.38.0',root=str(root),backup=str(backup),before=before,installed={n:digest(root/'superhuman'/n) for n in files})
   raw=(json.dumps(manifest,indent=2)+'\n').encode();atomic(backup/'manifest.json',raw);atomic(marker,raw)
  except Exception:
   for name,sha in before.items():
    dest=root/'superhuman'/name
    if sha:atomic(dest,(backup/'source'/name).read_bytes())
    else:dest.unlink(missing_ok=True)
   marker.unlink(missing_ok=True);raise
  print('Installed v1.38.0. Existing data, credentials, portraits, CLI/orchestrator and service configuration retained.')
  print('Rollback backup:',backup)
  print('Discussion readiness guards installed. No team activation, sharing or spending has been authorized.')
 except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:parser.exit(1,str(exc)+'\n')
if __name__=='__main__':main()
