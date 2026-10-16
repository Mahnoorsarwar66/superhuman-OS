"""Separate coding copies, inspectable diffs and bounded Docker unittest runs."""
import ast
from collections import deque
from datetime import datetime,timezone
import difflib
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from uuid import uuid4
from . import local

MAX_FILES=100
MAX_FILE_BYTES=200_000
MAX_TOTAL_BYTES=5_000_000
SUFFIXES={'.py','.md','.txt','.json','.toml','.cfg'}
SKIP={'.git','.venv','venv','node_modules','__pycache__','data','outputs','dist','build'}
IMAGE='python:3.13-slim'

def stamp():return datetime.now(timezone.utc).isoformat()
def digest(payload):return hashlib.sha256(payload).hexdigest()

def safe_name(name):
    if '\\' in name or ':' in name:raise ValueError('Use a relative forward-slash file path')
    p=PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or any(part.startswith('.') or part in SKIP for part in p.parts):raise ValueError('File is outside the allowed project structure')
    if not re.fullmatch(r'[a-zA-Z0-9_./ -]+',name) or p.suffix.lower() not in SUFFIXES:raise ValueError('Unsupported source filename')
    if re.search(r'(?i)(^|[._ /-])(env|credentials|secrets?|tokens?|private[-_ ]?key)([._ /-]|$)',name):raise ValueError('Credential/configuration secrets are not supported source files')
    if any(part.split('.')[0].upper() in {'CON','PRN','AUX','NUL','COM1','COM2','COM3','COM4','LPT1','LPT2','LPT3'} for part in p.parts):raise ValueError('Reserved Windows filename')
    if len(name)>180:raise ValueError('Source path is too long')
    return p.as_posix()

def root(project):
    workspace=local.workspace(project);path=workspace/'coding'
    if path.is_symlink():raise ValueError('Coding directory cannot be a symlink')
    path.mkdir(exist_ok=True);return path

def session(project,sid):
    if not re.fullmatch(r'[a-f0-9]{12}',sid):raise ValueError('Invalid coding workspace identifier')
    base=root(project);path=base/sid
    if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()) or not(path/'session.json').is_file():raise ValueError('Coding workspace not found')
    return path,json.loads((path/'session.json').read_text(encoding='utf-8'))

def source_file(folder,name,area='work'):
    safe_name(name)
    base=folder/area;path=base/name
    if area not in ('work','original') or base.is_symlink() or not path.resolve().is_relative_to(base.resolve()):raise ValueError('Source path escapes coding workspace')
    for parent in (path,*path.parents):
        if parent==folder:break
        if parent.is_symlink():raise ValueError('Symlink source files are not supported')
    return path

def create(project,label,files):
    if not label.strip() or len(label)>120:raise ValueError('Workspace title must be 1 to 120 characters')
    if not files or len(files)>MAX_FILES:raise ValueError('Provide 1 to 100 source files')
    checked={};seen=set()
    for name,content in files.items():
        name=safe_name(name)
        if name.casefold() in seen:raise ValueError('Duplicate source names on Windows')
        seen.add(name.casefold())
        if not isinstance(content,bytes):content=content.encode('utf-8')
        if len(content)>MAX_FILE_BYTES:raise ValueError('Source file exceeds 200 KB: '+name)
        content.decode('utf-8-sig')
        checked[name]=content
    if sum(map(len,checked.values()))>MAX_TOTAL_BYTES:raise ValueError('Source project exceeds 5 MB')
    sid=uuid4().hex[:12];folder=root(project)/sid;folder.mkdir()
    try:
        for area in ('original','work'):
            for name,content in checked.items():
                path=folder/area/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        record={'id':sid,'project':project,'label':label,'created_at':stamp(),'original_hashes':{name:digest(content) for name,content in checked.items()},'api_calls':0}
        (folder/'session.json').write_text(json.dumps(record,indent=2),encoding='utf-8');(folder/'events').mkdir()
        return record
    except Exception:shutil.rmtree(folder);raise

def from_zip(project,label,payload):
    if len(payload)>10_000_000:raise ValueError('ZIP exceeds 10 MB')
    files={};skipped=[]
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.infolist())>500:raise ValueError('ZIP contains too many entries')
        total=0
        for entry in archive.infolist():
            if entry.is_dir():continue
            if (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP symlinks are not supported')
            # Reject escape attempts even if this entry would otherwise be skipped.
            if entry.filename.startswith(('/', '\\')) or '..' in PurePosixPath(entry.filename.replace('\\','/')).parts or ':' in entry.filename:raise ValueError('Unsafe ZIP path')
            try:name=safe_name(entry.filename)
            except ValueError:skipped.append(entry.filename);continue
            if entry.file_size>MAX_FILE_BYTES:raise ValueError('ZIP source file exceeds 200 KB')
            total+=entry.file_size
            if total>MAX_TOTAL_BYTES:raise ValueError('ZIP expands beyond source limit')
            if name in files:raise ValueError('Duplicate ZIP entry')
            files[name]=archive.read(entry)
    record=create(project,label,files);return {**record,'skipped_files':skipped}

def demo(project):
    return create(project,'Python workspace example',{
        'calculator.py':'def total(values):\n    return sum(values)\n',
        'test_calculator.py':'import unittest\nfrom calculator import total\n\nclass TotalTests(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([2, 3]), 5)\n    def test_empty(self):\n        self.assertEqual(total([]), 0)\n'})

def event(folder,kind,result):
    record={'id':uuid4().hex[:12],'kind':kind,'created_at':stamp(),'api_calls':0,**result}
    with (folder/'events'/(record['id']+'.json')).open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2,ensure_ascii=False)
    return record

def inspect(project,sid):
    folder,record=session(project,sid);files=[]
    for name,original_hash in record['original_hashes'].items():
        old=source_file(folder,name,'original');path=source_file(folder,name)
        if digest(old.read_bytes())!=original_hash:raise ValueError('Original snapshot changed; stop and restore it')
        payload=path.read_bytes()
        files.append({'name':name,'bytes':len(payload),'sha256':digest(payload),'changed':digest(payload)!=original_hash})
    return {**record,'files':files}

def read(project,sid,name):
    folder,_=session(project,sid);inspect(project,sid)
    path=source_file(folder,name)
    if not path.is_file():raise ValueError('Source file not found')
    payload=path.read_bytes();return {'filename':name,'text':payload.decode('utf-8-sig'),'sha256':digest(payload)}

def syntax(project,sid):
    folder,_=session(project,sid);snapshot=inspect(project,sid);errors=[];checked=[]
    for file in snapshot['files']:
        if Path(file['name']).suffix.lower()!='.py':continue
        checked.append(file['name'])
        try:ast.parse(source_file(folder,file['name']).read_text(encoding='utf-8-sig'),filename=file['name'])
        except SyntaxError as exc:errors.append({'file':file['name'],'line':exc.lineno,'message':exc.msg})
    return event(folder,'syntax',{'status':'failed' if errors else 'passed' if checked else 'not_run','files_checked':checked,'errors':errors,'snapshot':{f['name']:f['sha256'] for f in snapshot['files']},'scope':'Parsing only. This does not execute code or prove correct behavior.'})

def preview(project,sid,name,text,expected):
    current=read(project,sid,name)
    if current['sha256']!=expected:raise ValueError('File changed. Reload before editing')
    payload=text.encode('utf-8')
    if len(payload)>MAX_FILE_BYTES:raise ValueError('Edited file exceeds 200 KB')
    diff=''.join(difflib.unified_diff(current['text'].splitlines(True),text.splitlines(True),fromfile='before/'+name,tofile='after/'+name))
    return {'filename':name,'diff':diff,'before_hash':current['sha256'],'after_hash':digest(payload),'text':text}

def edit(project,sid,name,text,expected,note):
    if not note.strip() or len(note)>2000:raise ValueError('Provide a change note up to 2000 characters')
    folder,record=session(project,sid)
    if name not in record['original_hashes']:raise ValueError('Editing is limited to existing files in this first version')
    proposed=preview(project,sid,name,text,expected);path=source_file(folder,name)
    if digest(path.read_bytes())!=expected:raise ValueError('File changed; reload')
    backup=folder/'events'/(uuid4().hex[:12]+'.before.txt');backup.write_bytes(path.read_bytes())
    temporary=path.with_name(path.name+'.coding.tmp')
    try:temporary.write_text(text,encoding='utf-8',newline='');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return event(folder,'edit',{**{key:value for key,value in proposed.items() if key!='text'},'note':note,'previous_copy':backup.name,'status':'saved'})

def full_diff(project,sid):
    folder,_=session(project,sid);snapshot=inspect(project,sid);parts=[]
    for file in snapshot['files']:
        if file['changed']:
            name=file['name'];old=source_file(folder,name,'original').read_text(encoding='utf-8-sig');new=source_file(folder,name).read_text(encoding='utf-8-sig')
            parts.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original/'+name,tofile='work/'+name)))
    return ''.join(parts)

def runtime():
    executable=shutil.which('docker')
    if not executable:return {'ready':False,'reason':'Docker is not installed or is unavailable in PATH. Syntax checks still work.'}
    try:
        check=subprocess.run([executable,'image','inspect',IMAGE],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,shell=False)
        if check.returncode:return {'ready':False,'reason':'Start Docker Desktop in Linux container mode and prepare the test image: docker pull '+IMAGE}
        return {'ready':True,'image':IMAGE}
    except (OSError,subprocess.TimeoutExpired):return {'ready':False,'reason':'Docker did not respond. Start Docker Desktop; syntax checks remain available.'}

RUNNER="""import sys,unittest,json
sys.path.insert(0,'/work')
suite=unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
count=suite.countTestCases()
if count<1:
 print('No tests discovered');sys.exit(4)
result=unittest.TextTestRunner(verbosity=2).run(suite)
print('SUPERHUMAN_TEST_RESULT '+json.dumps({'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}))
sys.exit(0 if result.wasSuccessful() else 1)
"""

def test_command(executable,mount,name,module):
    if ',' in str(mount):raise ValueError('Docker mount path cannot contain a comma')
    return [executable,'run','--pull','never','--rm','--name',name,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64','--memory','256m','--memory-swap','256m','--cpus','1','--user','65534:65534','--mount','type=bind,src='+str(mount.resolve())+',dst=/work,readonly','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--workdir','/work','--env','PYTHONDONTWRITEBYTECODE=1',IMAGE,'python','-I','-B','-c',RUNNER,module]

def run_tests(project,sid,module,confirmed=False):
    folder,_=session(project,sid);snapshot=inspect(project,sid)
    if not confirmed:raise ValueError('Explicitly confirm execution of the selected test module')
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',module):raise ValueError('Use a Python unittest module name, such as test_calculator')
    corresponding=module.replace('.','/')+'.py'
    if corresponding not in {f['name'] for f in snapshot['files']}:raise ValueError('Choose a test module that exists in this working copy')
    environment=runtime()
    if not environment['ready']:return event(folder,'tests',{'status':'not_run','reason':environment['reason'],'module':module})
    executable=shutil.which('docker');name='superhuman-test-'+uuid4().hex[:12]
    summary={'module':module,'image':IMAGE,'snapshot':{f['name']:f['sha256'] for f in snapshot['files']},'network':'none','source_mount':'read_only','timeout_seconds':30}
    # Freeze exactly the reviewed files, never bind-mount the live source tree.
    with tempfile.TemporaryDirectory(prefix='superhuman-test-') as directory:
        mount=Path(directory)/'work';mount.mkdir()
        for file in snapshot['files']:
            payload=source_file(folder,file['name']).read_bytes()
            if digest(payload)!=file['sha256']:raise ValueError('Working copy changed before test execution')
            target=mount/file['name'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
        process=None;chunks=deque(maxlen=16);total=[0];too_much=threading.Event()
        try:
            command=test_command(executable,mount,name,module)
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=False)
            def consume():
                while True:
                    chunk=process.stdout.read(4096)
                    if not chunk:break
                    total[0]+=len(chunk);chunks.append(chunk)
                    if total[0]>1_000_000:
                        too_much.set();process.kill();break
            reader=threading.Thread(target=consume,daemon=True);reader.start()
            try:code=process.wait(timeout=30);status='passed' if code==0 else 'failed'
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5);code=None;status='timed_out'
            reader.join(timeout=2)
            if too_much.is_set():status='failed'
            output=b''.join(chunks).decode('utf-8',errors='replace')[-32000:]
            if code in (4,125,126,127):status='not_run'
            # A module with no actual passing tests must not be presented as passed.
            match=re.search(r'SUPERHUMAN_TEST_RESULT (\{[^\n]+\})',output)
            counts=json.loads(match[1]) if match else None
            if status=='passed' and (not counts or counts.get('tests_run',0)<=counts.get('skipped',0)):status='not_run'
            summary.update(status=status,exit_code=code,output=output,counts=counts,output_truncated=total[0]>32000)
        except OSError as exc:summary.update(status='not_run',reason=str(exc))
        finally:
            if process and process.poll() is None:process.kill()
            try:subprocess.run([executable,'rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,shell=False)
            except (OSError,subprocess.TimeoutExpired):pass
    return event(folder,'tests',summary)

def package(project,sid):
    folder,record=session(project,sid);snapshot=inspect(project,sid);rid=uuid4().hex[:12];destination=folder/'events'/(rid+'.zip')
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
        for file in snapshot['files']:archive.writestr('work/'+file['name'],source_file(folder,file['name']).read_bytes())
        archive.writestr('changes.diff',full_diff(project,sid));archive.writestr('manifest.json',json.dumps(snapshot,indent=2))
        for path in sorted((folder/'events').glob('*.json')):archive.writestr('history/'+path.name,path.read_bytes())
    event(folder,'package',{'filename':destination.name,'sha256':digest(destination.read_bytes()),'status':'created'})
    return destination
