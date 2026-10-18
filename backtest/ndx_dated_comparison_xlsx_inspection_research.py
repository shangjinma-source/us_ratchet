"""Read-only XLSX/JSON display verification; no workbook authoring or economics."""
import io
import math
import posixpath
import re
import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
N={'s':NS}
SHEETS=['研究概览','全部任务','四轨指标','双基准距离','原始目标权重','来源索引']

def require(ok,message):
    if not ok:raise ValueError(message)

def coordinate(value):
    m=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',value or '')
    require(m is not None,'Explicit canonical cell coordinate required')
    column=0
    for c in m[1]:column=column*26+ord(c)-64
    row=int(m[2]);require(column<=16384 and row<=1048576,'Excel coordinate bound')
    return row,column

def text(element):
    return ''.join(t.text or '' for t in element.findall('.//s:t',N))

def inspect_export(xlsx_bytes,presentation):
    require(type(xlsx_bytes) is bytes and 0<len(xlsx_bytes)<=128*1024*1024,'Bounded XLSX bytes')
    require(presentation['schema']=='SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1','Presentation outer schema')
    display=presentation['display'];require(display['schema']=='DATED_COMPARISON_CHINESE_DISPLAY_TABLES_V1','Display schema')
    tables=display['tables'];require([t['name'] for t in tables]==SHEETS,'Exact six ordered tables')
    for flag in ('source_bytes_authenticated','economics_recomputed','formal_comparison_passed','future_independent_oos'):require(display[flag] is False,'Display authority')
    stats=[];types=dict(text=0,integer=0,float=0,boolean=0,null=0);text_formats=0
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        require(len(names)==len(set(names)) and len(names)<=256,'Unique bounded ZIP parts')
        require(sum(i.file_size for i in infos)<=512*1024*1024,'Uncompressed resource bound')
        def xml(path):
            raw=z.read(path);require(b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw,'No XML entities')
            return ET.fromstring(raw)
        book=xml('xl/workbook.xml');rels=xml('xl/_rels/workbook.xml.rels');mapping={}
        for rel in rels:
            require(rel.get('Id') not in mapping,'Unique workbook relationships')
            require(rel.get('TargetMode')!='External','No external workbook relationships')
            target=rel.get('Target','');path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            require(path.startswith('xl/') and '..' not in path.split('/'),'Internal package target')
            mapping[rel.get('Id')]=(path,rel.get('Type',''))
        sheets=book.findall('s:sheets/s:sheet',N);require([s.get('name') for s in sheets]==SHEETS,'Exact workbook sheet order')
        styles=xml('xl/styles.xml');formats={49:'@'}
        for f in styles.findall('s:numFmts/s:numFmt',N):
            k=int(f.get('numFmtId'));require(k not in formats or formats[k]==f.get('formatCode'),'Conflicting number format');formats[k]=f.get('formatCode')
        xfs=styles.findall('s:cellXfs/s:xf',N);require(xfs,'Styles required')
        strings=[]
        if 'xl/sharedStrings.xml' in names:strings=[text(e) for e in xml('xl/sharedStrings.xml').findall('s:si',N)]
        used=set();layout=None
        for sheet,table in zip(sheets,tables):
            path,kind=mapping[sheet.get('{'+REL+'}id')];require(kind.endswith('/worksheet') and path not in used,'Unique worksheet target');used.add(path)
            root=xml(path);require(not root.findall('.//s:f',N),'No formulas, including cached formulas')
            require(not root.findall('s:mergeCells/s:mergeCell',N),'No merged data cells')
            matrix=[table['headers']]+table['rows'];width=len(table['headers']);require(width and all(type(r) is list and len(r)==width for r in matrix),'Rectangular source rows')
            cells={};seen_rows=set()
            for row in root.findall('s:sheetData/s:row',N):
                rn=int(row.get('r'));require(rn not in seen_rows,'Duplicate row');seen_rows.add(rn)
                for cell in row.findall('s:c',N):
                    key=coordinate(cell.get('r'));require(key[0]==rn and key not in cells,'Unique cell and row coordinate')
                    index=int(cell.get('s','0'));require(0<=index<len(xfs),'Valid cell style')
                    fmt=formats.get(int(xfs[index].get('numFmtId','0')))
                    typ=cell.get('t','n');require(typ in ('n','inlineStr','s','str','b'),'No errors or unsupported cell type')
                    vals=cell.findall('s:v',N);require(len(vals)<=1,'Single scalar value');v=vals[0].text if vals else None
                    if typ=='inlineStr':
                        elements=cell.findall('s:is',N);require(len(elements)==1 and not vals,'Single inline string');value=text(elements[0]);kind='text'
                    elif typ=='s':
                        require(v is not None and re.fullmatch(r'[0-9]+',v) is not None and int(v)<len(strings),'Shared string index');value=strings[int(v)];kind='text'
                    elif typ=='str':value=v or '';kind='text'
                    elif typ=='b':require(v in ('0','1'),'Boolean encoding');value=v=='1';kind='boolean'
                    elif v is None or not v.strip():value=None;kind='null'
                    else:
                        value=Decimal(v);require(value.is_finite() and fmt!='@','Finite typed numeric, not text formatted');kind='numeric'
                    cells[key]=(kind,value,fmt)
            title=cells.get((1,1),('null',None,None));note=cells.get((2,1),('null',None,None))
            actual_title='Nasdaq-100 条件历史研究' if table['name']=='研究概览' else table['name']
            actual_note='2026-03-20 至 2026-09-21｜单路径诊断；不授正式晋级或未来 OOS'
            qa_title='合成数据运行验证｜'+table['name'];qa_note='仅合成测试数据，不含真实研究结果，不可用于投资或晋级结论'
            current_layout='ACTUAL_FIXED_ROW4' if title[:2]==('text',actual_title) and note[:2]==('text',actual_note) else 'SYNTHETIC_QA_FIXED_ROW4' if title[:2]==('text',qa_title) and note[:2]==('text',qa_note) else None
            require(current_layout is not None and (layout is None or layout==current_layout),'Exact consistent title and scope annotation')
            layout=current_layout
            for (r,c),(kind,value,fmt) in cells.items():
                allowed=(r,c) in ((1,1),(2,1)) or (4<=r<=len(matrix)+3 and c<=width)
                if not allowed:require(kind=='null','Extra nonempty cell beyond fixed layout')
            for ri,row in enumerate(matrix,4):
                for ci,expected in enumerate(row,1):
                    kind,value,fmt=cells.get((ri,ci),('null',None,None));location=table['name']+'!'+str((ri,ci))
                    if expected is None:require(kind=='null', 'NULL is not zero/string: '+location);types['null']+=1
                    elif type(expected) is str:
                        require(kind=='text' and value==expected,'Exact Unicode text/identifier: '+location);types['text']+=1;text_formats+=fmt=='@'
                    elif type(expected) is bool:require(kind=='boolean' and value is expected,'Boolean type: '+location);types['boolean']+=1
                    elif type(expected) is int:require(kind=='numeric' and value==Decimal(expected),'Exact integer: '+location);types['integer']+=1
                    elif type(expected) is float:
                        require(math.isfinite(expected) and kind=='numeric','Finite numeric display: '+location)
                        require(expected!=0 or value==Decimal(0),'Exact zero must not underflow from nonzero')
                        actual=float(value);require(math.isfinite(actual),'Finite serialized binary value')
                        tolerance=max(4*math.ulp(expected),abs(expected)*5e-15) if expected else 0
                        require(abs(actual-expected)<=tolerance,'Binary display value differs: '+location);types['float']+=1
                    else:raise ValueError('Unsupported source value type')
            stats.append(dict(name=table['name'],header_count=width,data_row_count=len(matrix)-1,verified_cell_count=len(matrix)*width,extra_nonempty_cell_count=0))
    return dict(schema='DATED_COMPARISON_XLSX_EXPORT_INSPECTION_V1',status='PASS',sheets=stats,sheet_count=6,layout=layout,source_bytes_authentication_is_publishers_responsibility=True,value_type_counts=types,text_format_cell_count=text_formats,numeric_comparison_semantics='Finite binary64 display only; tolerance max(4 ULP, 5e-15 relative), exact zero; integers/text exact. Not exact decimal economics.',source_bytes_authenticated=False,economics_recomputed=False,workbook_modified=False,formal_comparison_passed=False)
