"""Additional exact-text style gate; complements, never replaces, full value readback."""
import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

N={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
MAX_BYTES=128*1024*1024
MAX_UNPACKED=512*1024*1024
MAX_STYLES=60000

def require(ok,message):
    if not ok:raise ValueError(message)

class NoDoctype(ET.TreeBuilder):
    def doctype(self,name,pubid,system):
        raise ValueError('XML DTD forbidden')

def expected_format(value):
    if type(value) is not str:return None
    exact=bool(re.fullmatch('[0-9a-fA-F]{64}',value)) or bool(re.fullmatch('[0-9]+',value) and (len(value)>15 or (len(value)>1 and value.startswith('0'))))
    if not exact:return '@'
    require(len(value)<=64,'Bounded exact literal')
    return '"'+value+'"'

def inspect_text_styles(xlsx_bytes,presentation):
    require(type(xlsx_bytes) is bytes and 0<len(xlsx_bytes)<=MAX_BYTES,'Bounded XLSX')
    tables=presentation['display']['tables']; verified=0
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        parts=z.infolist();names=[x.filename for x in parts]
        require(len(names)==len(set(names)) and len(names)<=256 and sum(x.file_size for x in parts)<=MAX_UNPACKED,'ZIP bounds')
        def xml(path):
            raw=z.read(path);require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw,'XML entities')
            return ET.fromstring(raw,parser=ET.XMLParser(target=NoDoctype()))
        styles=xml('xl/styles.xml');formats={0:'General',49:'@'}
        for f in styles.findall('s:numFmts/s:numFmt',N):
            k=int(f.get('numFmtId'));require(k not in formats,'Duplicate format');formats[k]=f.get('formatCode')
        xfs=styles.findall('s:cellXfs/s:xf',N)
        require(0<len(xfs)<=MAX_STYLES and len(formats)<=MAX_STYLES,'Style bound')
        shared=[]
        if 'xl/sharedStrings.xml' in names:shared=[''.join(t.text or '' for t in x.findall('.//s:t',N)) for x in xml('xl/sharedStrings.xml').findall('s:si',N)]
        mapping={}
        for r in xml('xl/_rels/workbook.xml.rels'):
            require(r.get('Id') not in mapping and r.get('TargetMode')!='External','Relationship')
            target=r.get('Target','');p=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            require(p.startswith('xl/') and '..' not in p.split('/'),'Internal part');mapping[r.get('Id')]=p
        sheets=xml('xl/workbook.xml').findall('s:sheets/s:sheet',N)
        require([s.get('name') for s in sheets]==[t['name'] for t in tables] and len(tables)==6,'Six sheet order')
        used=set()
        for sheet,table in zip(sheets,tables):
            path=mapping[sheet.get('{'+REL+'}id')];require(path not in used,'Unique sheet');used.add(path)
            expected={}
            for rownum,row in enumerate(table['rows'],5):
                for col,v in enumerate(row,1):
                    label='';n=col
                    while n:n,k=divmod(n-1,26);label=chr(65+k)+label
                    expected[label+str(rownum)]=v
            cells={}
            sheet_xml=xml(path)
            require(not any(e.tag.rsplit('}',1)[-1]=='conditionalFormatting' for e in sheet_xml.iter()),'Conditional formatting forbidden')
            for c in sheet_xml.findall('s:sheetData/s:row/s:c',N):
                address=c.get('r');require(address not in cells,'Duplicate cell');cells[address]=c
                i=int(c.get('s','0'));require(0<=i<len(xfs),'Style index')
                fmt=formats.get(int(xfs[i].get('numFmtId','0')),'BUILTIN')
                value=expected.get(address);wanted=expected_format(value)
                if wanted and wanted!='@':
                    require(fmt==wanted and len(fmt)<=66,'Exact single literal style')
                    require(c.find('s:f',N) is None,'No formula')
                    typ=c.get('t');v=c.find('s:v',N)
                    if typ=='str':actual=v.text if v is not None and v.text else ''
                    elif typ=='inlineStr':actual=''.join(t.text or '' for t in c.findall('s:is//s:t',N))
                    elif typ=='s':
                        require(v is not None and re.fullmatch('[0-9]+',v.text or '') and int(v.text)<len(shared),'Shared index');actual=shared[int(v.text)]
                    else:raise ValueError('Exact literal must preserve string')
                    require(actual==value,'Exact underlying string');verified+=1
                else:
                    require('"' not in fmt,'No literal on other cells')
                    if wanted=='@':require(fmt=='@','Other text format')
            for address,value in expected.items():
                if expected_format(value) not in (None,'@'):require(address in cells,'Missing exact text cell')
    return dict(schema='DATED_EXACT_TEXT_STYLE_INSPECTION_V1',status='PASS',exact_literal_cell_count=verified,style_count=len(xfs),source_bytes_authenticated=False,workbook_modified=False,visual_acceptance_passed=False)
