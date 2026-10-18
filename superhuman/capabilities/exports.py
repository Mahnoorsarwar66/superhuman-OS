"""Create local office files from explicit source text. Never model calls."""
import csv
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4
from xml.sax.saxutils import escape
from . import local

def blocks(text):
    for chunk in re.split(r'\n\s*\n',text.strip()):
        lines=chunk.splitlines()
        if any(re.match(r'^#{1,3} |^[-*] |^\d+[.)] ',line) for line in lines):
            for line in lines:
                match=re.match(r'^(#{1,3}) (.*)',line)
                yield (len(match[1]) if match else 0,match[2] if match else line)
        else:yield 0,' '.join(lines)

def check_text(title,text):
    if not title.strip() or len(title)>200:raise ValueError('Use a title between 1 and 200 characters')
    if not text.strip() or len(text)>100_000:raise ValueError('Use nonempty text under 100,000 characters')
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]',title+text):raise ValueError('Text contains unsupported control characters')

def _v133_make_docx(path,title,text):
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    doc=Document();section=doc.sections[0]
    section.top_margin=section.bottom_margin=Inches(.8)
    section.left_margin=section.right_margin=Inches(.9)
    normal=doc.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(9);normal.paragraph_format.line_spacing=1.15
    for name,size in [('Title',24),('Heading 1',17),('Heading 2',14),('Heading 3',12)]:
        style=doc.styles[name];style.font.name='Arial';style.font.size=Pt(size);style.font.color.rgb=RGBColor(0,0,0)
        style.paragraph_format.keep_with_next=True
    from docx.oxml.ns import qn
    for style in doc.styles:
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    doc.add_paragraph(title,style='Title')
    for level,content in blocks(text):
        paragraph=doc.add_paragraph(style='Heading '+str(level) if level else 'Normal')
        for i,part in enumerate(re.split(r'\*\*(.*?)\*\*',content)):
            run=paragraph.add_run(part);run.bold=bool(i%2)
        paragraph.paragraph_format.widow_control=True
    footer=section.footer.paragraphs[0];footer.text=title;footer.style='Normal'
    for run in footer.runs:run.font.size=Pt(8);run.font.color.rgb=RGBColor(0,0,0)
    doc.save(path)
    # Reopen the actual bytes to validate the container and title/body presence.
    loaded=Document(path)
    if loaded.paragraphs[0].text!=title:raise ValueError('DOCX validation failed')
    return ['Basic text, headings and bold formatting only. Tables, images and complex Markdown are not converted to native document objects.']

def pdf_fonts(text):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates=[(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/arial.ttf',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/arialbd.ttf'),(Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))]
    for regular,bold in candidates:
        if regular.is_file() and bold.is_file():
            if 'SHExport' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('SHExport',str(regular)));pdfmetrics.registerFont(TTFont('SHExportBold',str(bold)))
                pdfmetrics.registerFontFamily('SHExport',normal='SHExport',bold='SHExportBold',italic='SHExport',boldItalic='SHExportBold')
            cmap=pdfmetrics.getFont('SHExport').face.charToGlyph
            if any(ord(char) not in cmap for char in text if not char.isspace()):raise ValueError('PDF font does not support some characters. Export Word instead.')
            return 'SHExport','SHExportBold'
    if any(ord(char)>126 for char in text):raise ValueError('A Unicode font is unavailable. Export Word or install Arial/DejaVu Sans.')
    return 'Helvetica','Helvetica-Bold'

def _v133_make_pdf(path,title,text):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
    normal,bold=pdf_fonts(title+text)
    style=ParagraphStyle('Body',fontName=normal,fontSize=10.5,leading=16,spaceAfter=10,textColor=colors.black,splitLongWords=True)
    titles=ParagraphStyle('Title',parent=style,fontName=bold,fontSize=22,leading=28,spaceAfter=20,keepWithNext=True)
    styles={i:ParagraphStyle('H'+str(i),parent=style,fontName=bold,fontSize=17-i,leading=21-i,spaceBefore=12,spaceAfter=8,keepWithNext=True) for i in (1,2,3)}
    story=[Paragraph(escape(title),titles)]
    for level,content in blocks(text):
        content=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',escape(content))
        story.append(Paragraph(content,styles[level] if level else style))
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont(normal,8);canvas.setFillColor(colors.HexColor('#66716b'))
        canvas.drawRightString(A4[0]-54,30,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=54,leftMargin=54,topMargin=52,bottomMargin=48,title=title).build(story,onFirstPage=footer,onLaterPages=footer)
    if not path.read_bytes().startswith(b'%PDF-'):raise ValueError('PDF validation failed')
    return ['PDF export uses basic text layout. Complex scripts, tables and images need visual review.']

def make_xlsx(path,title,text,numeric=False):
    from openpyxl import Workbook,load_workbook
    from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
    from openpyxl.utils import get_column_letter
    rows=list(csv.reader(io.StringIO(text,newline='')))
    if not rows or not rows[0]:raise ValueError('CSV must have a header row')
    if len(rows)>10001 or max(map(len,rows))>100:raise ValueError('Export supports at most 10,000 data rows and 100 columns; source is not truncated')
    if any(len(row)!=len(rows[0]) for row in rows):raise ValueError('CSV has inconsistent row widths; correct the source before exporting')
    if any(len(value)>500 or value.count('\n')>20 for row in rows for value in row):raise ValueError('A cell is too long for this simple workbook layout. Use a document or shorten cells to 500 characters and 20 line breaks.')
    workbook=Workbook();sheet=workbook.active;sheet.title='Data'
    workbook.properties.title=title;sheet.freeze_panes='A2'
    for ri,row in enumerate(rows,1):
        for ci,value in enumerate(row,1):
            cell=sheet.cell(ri,ci);cell.value=value;cell.data_type='s'
            # Text is the default, including =formula, identifiers and leading zeros.
            if numeric and ri>1 and re.fullmatch(r'-?(?:0|[1-9]\d*)(?:\.\d+)?',value) and len(value.replace('-','').replace('.',''))<=15:
                cell.value=float(value) if '.' in value else int(value)
                cell.number_format='#,##0.'+'0'*len(value.split('.')[1]) if '.' in value else '#,##0'
            cell.font=Font(name='Calibri',size=11,color='172826')
            cell.alignment=Alignment(horizontal='right' if cell.data_type=='n' else 'left',vertical='center',wrap_text=True,indent=1)
            edge=Side(style='thin',color='D9D9D9');cell.border=Border(left=edge,right=edge,top=edge,bottom=edge)
            if ri==1:
                cell.fill=PatternFill('solid',fgColor='174D40');cell.font=Font(name='Calibri',size=11,bold=True,color='FFFFFF')
            elif ri%2:cell.fill=PatternFill('solid',fgColor='F1F5F0')
        sheet.row_dimensions[ri].height=max(32 if ri==1 else 24,min(400,16*(1+max(len(v)//40+v.count('\n') for v in row))))
    for ci in range(1,len(rows[0])+1):sheet.column_dimensions[get_column_letter(ci)].width=min(48,max(14,max(len(str(row[ci-1])) for row in rows)+2))
    sheet.auto_filter.ref=sheet.dimensions
    sheet.print_title_rows='1:1';sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A4;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
    workbook.save(path)
    checked=load_workbook(path,data_only=False)
    if checked.active.max_row!=len(rows) or any(cell.data_type=='f' for row in checked.active for cell in row):raise ValueError('XLSX validation failed')
    checked.close()
    return ['CSV is exported without formulas. '+('Plain numeric cells up to 15 digits are converted; leading zeros and other values remain text.' if numeric else 'All source values are preserved as text, including numbers and identifiers.')]

def generate(project,format,title,text,source=None,numeric=False):
    check_text(title,text)
    if format not in ('docx','pdf','xlsx'):raise ValueError('Supported export formats: docx, pdf, xlsx')
    workspace=local.workspace(project);exports=workspace/'exports'
    if exports.is_symlink():raise ValueError('Export directory cannot be a symlink')
    exports.mkdir(exist_ok=True);rid=uuid4().hex[:12];folder=exports/rid;folder.mkdir()
    slug=re.sub(r'[^a-zA-Z0-9_-]+','_',title).strip('_')[:60] or 'document'
    path=folder/(slug+'.'+format)
    try:
        warnings=make_xlsx(path,title,text,numeric) if format=='xlsx' else (make_docx if format=='docx' else make_pdf)(path,title,text)
        record={'export_id':rid,'project':project,'format':format,'title':title,'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source':source or {'kind':'submitted_text','sha256':hashlib.sha256(text.encode()).hexdigest()},'warnings':warnings,'status':'created','api_calls':0,'created_at':datetime.now(timezone.utc).isoformat()}
        (folder/'record.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
        return record
    except Exception:
        for child in folder.iterdir():child.unlink()
        folder.rmdir();raise

def artifact(project,rid):
    if not re.fullmatch(r'[a-f0-9]{12}',rid):raise ValueError('Invalid export identifier')
    root=local.workspace(project);folder=root/'exports'/rid
    if folder.is_symlink() or (root/'exports').is_symlink() or not folder.resolve().is_relative_to(root.resolve()):raise ValueError('Invalid export path')
    record_path=folder/'record.json'
    if record_path.is_symlink() or not record_path.is_file():raise ValueError('Export record unavailable')
    record=json.loads(record_path.read_text(encoding='utf-8'))
    format=record.get('format')
    if format not in ('docx','pdf','xlsx'):raise ValueError('Invalid export format')
    filename=record.get('filename','')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}\.'+format,filename):raise ValueError('Invalid export filename')
    path=folder/filename
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record.get('sha256'):raise ValueError('Export changed or missing')
    return path,record


def make_docx(path,title,text):
    from superhuman.practice.exports import docx
    return docx(path,title,text)

def make_pdf(path,title,text):
    from superhuman.practice.exports import pdf
    return pdf(path,title,text)
