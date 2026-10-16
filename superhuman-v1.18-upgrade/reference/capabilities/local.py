"""Local file tools with explicit workspace boundaries and inspectable run records."""
import ast
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import zipfile
from xml.etree import ElementTree as ET
from uuid import uuid4

ROOT = Path('data/workspaces')
MAX_BYTES = 10_000_000
MAX_CHARS = 40_000
MAX_ROWS = 10_000
FORMATS = {'.txt','.md','.csv','.json','.docx','.pdf','.xlsx'}
TOOLS = {
 'inspect_file':'Read text, page-numbered PDF text, DOCX paragraphs, or XLSX cached values.',
 'search_files':'Search supported files in this workstream for literal text.',
 'profile_table':'Profile a CSV with exact decimal totals, missing cells and malformed rows.',
 'calculate':'Evaluate bounded decimal arithmetic without executing code.'}

def workspace(project):
    from superhuman.core.router import WORKSTREAMS
    if project not in WORKSTREAMS or not re.fullmatch(r'[a-zA-Z0-9_]+',project): raise ValueError('Unknown workstream')
    root=ROOT.resolve();path=root/project
    if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Workspace must remain inside data/workspaces')
    path.mkdir(parents=True,exist_ok=True)
    return path

def inputs(project):
    root=workspace(project);path=root/'inputs'
    if path.is_symlink():raise ValueError('Input directory cannot be a symlink')
    path.mkdir(exist_ok=True)
    return path

def valid_name(name):
    if not name or name!=Path(name).name or any(x in name for x in ('/', '\\', ':')):raise ValueError('Use a filename, not a path')
    if name.startswith('.') or re.search(r'(?i)(^|[._ -])(env|credentials|secrets?|tokens?|private[-_ ]?key)([._ -]|$)',name):raise ValueError('Configuration or credential files are not supported inputs')
    if Path(name).suffix.lower() not in FORMATS:raise ValueError('Supported formats: '+', '.join(sorted(FORMATS)))
    return name

def file_for(project,name):
    valid_name(name);root=inputs(project);path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('File escapes workspace')
    if not path.is_file():raise ValueError('Input file not found: '+name)
    if path.stat().st_size>MAX_BYTES:raise ValueError('File exceeds 10 MB limit')
    return path

def store_bytes(project,name,content):
    valid_name(name)
    if len(content)>MAX_BYTES:raise ValueError('File exceeds 10 MB limit')
    path=inputs(project)/name
    # Refuse overwrite of user inputs, including symlinks.
    with path.open('xb') as stream:stream.write(content)
    return {'filename':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}

def import_file(project,source):
    path=Path(source);valid_name(path.name)
    if not path.is_file() or path.is_symlink():raise ValueError('Provide a regular source file')
    with path.open('rb') as stream:content=stream.read(MAX_BYTES+1)
    return store_bytes(project,path.name,content)

def xml_member(archive,name):
    info=archive.getinfo(name)
    if info.file_size>8_000_000:raise ValueError('Office XML part exceeds extraction limit')
    payload=archive.read(info)
    if b'<!DOCTYPE' in payload or b'<!ENTITY' in payload:raise ValueError('XML entities are not supported')
    return ET.fromstring(payload)

def office(path,payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.infolist())>2000 or sum(x.file_size for x in archive.infolist())>40_000_000:raise ValueError('Office archive exceeds extraction limit')
        if path.suffix.lower()=='.docx':
            root=xml_member(archive,'word/document.xml');ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return '\n'.join(''.join(x.text or '' for x in paragraph.findall('.//w:t',ns)) for paragraph in root.findall('.//w:p',ns)), ['DOCX body text only; layout, images, headers and tracked-change semantics are not evaluated.']
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(n.itertext()) for n in xml_member(archive,'xl/sharedStrings.xml').findall('s:si',ns)]
        blocks=[];has_formula=False;count=0
        for name in sorted(n for n in archive.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)):
            blocks.append('['+name+']')
            for row in xml_member(archive,name).findall('.//s:row',ns):
                cells=[]
                for cell in row.findall('s:c',ns):
                    value=cell.find('s:v',ns);text=value.text or '' if value is not None else ''
                    if cell.get('t')=='s':text=strings[int(text)] if text else ''
                    if cell.get('t')=='inlineStr':text=''.join(cell.find('s:is',ns).itertext()) if cell.find('s:is',ns) is not None else ''
                    if cell.find('s:f',ns) is not None:has_formula=True;text='[cached formula result] '+(text or '[missing]')
                    cells.append(cell.get('r','?')+': '+text)
                blocks.append(' | '.join(cells));count+=1
                if count>=MAX_ROWS:break
            if count>=MAX_ROWS:break
        warnings=['XLSX values are not recalculated; date serials and display formatting are not interpreted.']
        if has_formula:warnings.append('Formula values are cached and may be stale or missing.')
        if count>=MAX_ROWS:warnings.append('Stopped at the worksheet row limit.')
        return '\n'.join(blocks),warnings

def extract(project,name):
    path=file_for(project,name);suffix=path.suffix.lower();warnings=[];payload=path.read_bytes()
    if len(payload)>MAX_BYTES:raise ValueError('File exceeds 10 MB limit')
    try:
        if suffix in ('.docx','.xlsx'):text,warnings=office(path,payload)
        elif suffix=='.pdf':
            try:from pypdf import PdfReader
            except ImportError:raise ValueError('PDF support needs: python -m pip install pypdf')
            reader=PdfReader(io.BytesIO(payload))
            if reader.is_encrypted:raise ValueError('Encrypted PDFs are not supported')
            text='\n\n'.join('[Page '+str(i+1)+']\n'+(page.extract_text() or '') for i,page in enumerate(reader.pages[:100]))
            warnings=['PDF text extraction does not verify layout, tables, images or scanned pages; no OCR is available.']
            if len(reader.pages)>100:warnings.append('Only the first 100 pages were extracted.')
            if not any(c.isalpha() for c in re.sub(r'\[Page \d+\]','',text)):warnings.append('No useful text found. This may require OCR.')
        else:text=payload.decode('utf-8-sig')
    except (UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError) as exc:raise ValueError('Cannot read this file as the declared format') from exc
    truncated=len(text)>MAX_CHARS
    if truncated:warnings.append('Text excerpt truncated at '+str(MAX_CHARS)+' characters.')
    return {'filename':name,'sha256':hashlib.sha256(payload).hexdigest(),'text':text[:MAX_CHARS], 'truncated':truncated,'warnings':warnings}

def profile(project,name):
    path=file_for(project,name)
    if path.suffix.lower()!='.csv':raise ValueError('profile_table currently supports CSV only')
    payload=path.read_bytes()
    if len(payload)>MAX_BYTES:raise ValueError('File exceeds 10 MB limit')
    with io.StringIO(payload.decode('utf-8-sig'),newline='') as stream:
        reader=csv.reader(stream);header=next(reader,None)
        if not header:raise ValueError('CSV is empty')
        if len(header)>200:raise ValueError('CSV exceeds 200 column limit')
        columns=[{'index':i,'name':name,'missing':0,'numeric_count':0,'numeric_sum':Decimal(0)} for i,name in enumerate(header)]
        count=0;malformed=0;truncated=False
        with localcontext() as ctx:
            ctx.prec=50
            for row in reader:
                if count>=MAX_ROWS:truncated=True;break
                count+=1
                if len(row)!=len(header):malformed+=1
                for i,col in enumerate(columns):
                    text=row[i].strip() if i<len(row) else ''
                    if not text:col['missing']+=1;continue
                    if not re.fullmatch(r'[+-]?\d{1,30}(?:\.\d{1,10})?',text):continue
                    col['numeric_count']+=1;col['numeric_sum']+=Decimal(text)
    for col in columns:col['numeric_sum']=str(col['numeric_sum'])
    return {'filename':name,'sha256':hashlib.sha256(payload).hexdigest(),'rows_read':count,'malformed_rows':malformed,'truncated':truncated,'columns':columns,'warnings':['Totals cover only recognized plain decimal cells in rows read. Mixed or nonnumeric columns are not complete totals. Currency symbols, thousands separators and formulas are not interpreted.']}

def calculate(expression):
    if not expression or len(expression)>500:raise ValueError('Provide an arithmetic expression up to 500 characters')
    tree=ast.parse(expression,mode='eval')
    if sum(1 for _ in ast.walk(tree))>80:raise ValueError('Expression too complex')
    def visit(node):
        if isinstance(node,ast.Expression):return visit(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            text=ast.get_source_segment(expression,node)
            if not re.fullmatch(r'\d{1,30}(?:\.\d{1,20})?',text):raise ValueError('Use plain decimal numbers')
            return Decimal(text)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=visit(node.operand);return -value if isinstance(node.op,ast.USub) else value
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Add):value=a+b
            elif isinstance(node.op,ast.Sub):value=a-b
            elif isinstance(node.op,ast.Mult):value=a*b
            else:value=a/b
            if not value.is_finite() or abs(value)>Decimal('1e100'):raise ValueError('Calculation exceeds magnitude limit')
            return value
        raise ValueError('Only numbers, parentheses and + - * / are supported')
    try:
        with localcontext() as ctx:ctx.prec=50;value=visit(tree)
    except (ArithmeticError,InvalidOperation) as exc:raise ValueError('Invalid arithmetic operation') from exc
    return {'expression':expression,'result':str(value),'precision_digits':50,'warnings':['Recurring or long results are rounded to 50 significant digits.']}

def execute(project,tool,**arguments):
    if tool not in TOOLS:raise ValueError('Unknown tool')
    workspace(project);run_id=uuid4().hex[:12]
    started=datetime.now(timezone.utc).isoformat()
    try:
        if tool=='inspect_file':result=extract(project,arguments['filename'])
        elif tool=='profile_table':result=profile(project,arguments['filename'])
        elif tool=='calculate':result=calculate(arguments['expression'])
        else:
            query=arguments.get('query','')
            if not 1<=len(query)<=200:raise ValueError('Search query must be 1 to 200 characters')
            matches=[];skipped=[];files=sorted(inputs(project).iterdir());scanned=0
            for path in files[:50]:
                try:
                    doc=extract(project,path.name);scanned+=1
                    for line_number,line in enumerate(doc['text'].splitlines(),1):
                        if query.casefold() in line.casefold():matches.append({'filename':path.name,'line':line_number,'text':line[:400],'sha256':doc['sha256']})
                        if len(matches)>=50:break
                except Exception as exc:skipped.append({'filename':path.name,'reason':str(exc)})
                if len(matches)>=50:break
            result={'query':query,'matches':matches,'files_scanned':scanned,'skipped':skipped,'warnings':['Search is limited to 50 files, extracted text excerpts and 50 matches. PDF line numbers refer to extracted text, not original layout.']}
        record={'run_id':run_id,'project':project,'tool':tool,'status':'completed','arguments':arguments,'result':result,'api_calls':0,'started_at':started}
    except Exception as exc:
        record={'run_id':run_id,'project':project,'tool':tool,'status':'failed','arguments':arguments,'error':str(exc),'api_calls':0,'started_at':started}
    folder=workspace(project)/'runs'
    if folder.is_symlink():raise ValueError('Runs directory cannot be a symlink')
    folder.mkdir(exist_ok=True);destination=folder/(run_id+'.json')
    with destination.open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2,ensure_ascii=False)
    return {**record,'record_path':str(destination)}

def source_context(project,details):
    # Only explicit markers in the current task, never markers in dependency output.
    current=re.split(r'USER-CURATED IDENTITY|DEPENDENCY REFERENCES|TASK-SELECTED REFERENCES',details,maxsplit=1)[0]
    names=list(dict.fromkeys(re.findall(r'\[\[file:([^\]\r\n]+)\]\]',current)))
    if len(names)>8:raise ValueError('Attach at most 8 source files per task')
    references=[];traces=[];remaining=12000
    for name in names:
        record=execute(project,'inspect_file',filename=name)
        if record['status']!='completed':raise ValueError('Source file unavailable: '+name+'; '+record['error'])
        result=record['result'];text=result['text'][:max(0,remaining)]
        if not text:raise ValueError('Attached file has no readable text or exceeds the source budget: '+name)
        remaining-=len(text)
        references.append(json.dumps({'filename':name,'sha256':result['sha256'],'text':text,'warnings':result['warnings'],'excerpt_truncated':len(text)<len(result['text'])},ensure_ascii=False))
        traces.append({'filename':name,'sha256':result['sha256'],'run_id':record['run_id'],'record_path':record['record_path'],'characters_used':len(text)})
    return {'text':'\n'.join(references),'files':traces}
