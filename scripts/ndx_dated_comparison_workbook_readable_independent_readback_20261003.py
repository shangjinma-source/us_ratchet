"""Immutable saved XLSX readback; numeric acceptance is not visual acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import types
import io,posixpath,zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
EXPORT=ROOT/'outputs/01a0cc4a-c717-7813-843e-86aca0d15714/dated_comparison_workbook_readable_20261003_v1'
OUTPUT=ROOT/'data/cache/research/dated_comparison_workbook_readable_independent_readback_20261003_v1'
BOUND={
 'manifest':{'path':str(EXPORT/'export_manifest.json'),'sha256':'d1178c54c296eb92083d85c3240dc43ebc070138d125ffb212e879e366c00caa'},
 'presentation':{'path':str(ROOT/'data/cache/research/dated_comparison_presentation_20261003_v1/presentation.json'),'sha256':'a586ab8ee02f6cc0b87bd0bddda9b38bb4cfcc5364873b40e6f77458afd3231c'},
 'publication':{'path':str(ROOT/'data/cache/research/dated_comparison_presentation_20261003_v1/publication.json'),'sha256':'79120009b95bd74675112ddb120dd29b2cab4deb4f67748acbd0af03ba2397ef'},
 'exporter':{'path':str(ROOT/'scripts/ndx_dated_comparison_workbook_readable_publish_20261003.mjs'),'sha256':'b81335a8b69b59322b1a32e0440373bda39ec531e4e08e65cb6cc92d619d9de9'},
 'builder':{'path':str(ROOT/'scripts/ndx_dated_comparison_workbook_20261003.mjs'),'sha256':'8bbbc945191a9ca4166574f5fdb916e9aa09f48bb710f0ddba056fc1763714b1'},
 'layout':{'path':str(ROOT/'scripts/ndx_dated_comparison_workbook_readable_layout_20261003.mjs'),'sha256':'1e34dfb4e203c835c7519077b98edf34b346269c653a518032e933b5f16f3b02'},
 'core':{'path':str(ROOT/'backtest/ndx_dated_comparison_xlsx_inspection_research.py'),'sha256':'9bfc477ceb4c1b0bbcb6155e6e7e48856645e5d3a3db877ef303403207b4d273'},
 'style_core':{'path':str(ROOT/'backtest/ndx_dated_exact_text_style_inspection_research.py'),'sha256':'5a7d48b1c52031b03e1ebbbc128534b42bcea003f259d2390f5a3ff9c8401d69'}}
LIMITATION='Layout adjusted for security identifiers and source paths; full visual acceptance remains pending'
FALSE=('formal_comparison_passed','future_independent_oos','economics_recomputed')
def require(ok,message):
    if not ok:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def reference(ref):require(type(ref) is dict and set(ref)=={'path','sha256'} and type(ref['path']) is str and type(ref['sha256']) is str and re.fullmatch('[a-f0-9]{64}',ref['sha256']),'Explicit reference')
def merge(sources,path,sha):
    reference(dict(path=path,sha256=sha));require(path not in sources or sources[path]==sha,'Source conflict');sources[path]=sha

def validate(manifest,presentation,publication,refs):
    require(manifest['schema']=='DATED_COMPARISON_READABLE_WORKBOOK_EXPORT_V1' and manifest['status']=='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Export state')
    require(presentation['schema']=='SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1','Presentation schema')
    require(publication['schema']=='DATED_COMPARISON_PRESENTATION_PUBLICATION_V1' and publication['status']=='PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY','Presentation receipt')
    exact(publication['presentation_reference'],refs['presentation'],'Presentation receipt reference');exact(publication['source_hashes'],presentation['source_hashes'],'Presentation source map')
    exact(manifest['input_references'],{k:refs[k] for k in ('presentation','publication','builder','layout')},'Export inputs')
    expected={refs[k]['path']:refs[k]['sha256'] for k in ('exporter','presentation','publication','builder','layout')}
    for path,h in presentation['source_hashes'].items():merge(expected,path,h)
    exact(manifest['source_hashes'],expected,'Full direct export closure')
    for r in presentation['input_references'].values():reference(r);require(presentation['source_hashes'][r['path']]==r['sha256'],'Original reference covered')
    for obj in (manifest,presentation,publication):
        for key in FALSE:require(obj[key] is False,'No authority')
    for obj in (presentation,publication):
        for key in ('promotion_allowed','point_in_time_verified','workbook_created'):require(obj[key] is False,'Presentation scope')
    require(manifest['in_memory_table_values_verified'] is True and manifest['exported_cell_values_independently_verified'] is False and manifest['visual_acceptance_passed'] is False,'Pending independent acceptance')
    require(manifest['known_preview_limitation']==LIMITATION and manifest['runtime_bundle']=='26.909.12148','Preserved rendering limitation')
    reference(manifest['workbook_reference']);require(Path(manifest['workbook_reference']['path'])==EXPORT/'条件历史比较.xlsx','Fixed workbook')
    previews=manifest['previews'];require(type(previews) is list and len(previews)==6,'Six preview references')
    for i,(preview,table) in enumerate(zip(previews,presentation['display']['tables'])):
        require(set(preview)=={'path','sha256','sheet','range'},'Preview reference fields');reference({k:preview[k] for k in ('path','sha256')})
        require(Path(preview['path'])==EXPORT/f'preview_{i}.png' and preview['sheet']==table['name'],'Ordered preview files')
        require(preview['range']==f"A1:{chr(64+len(table['headers']))}{min(len(table['rows'])+4,18)}",'Preview is bounded, not full visual proof')
    exact(manifest['layout_adjustments'],expected_layout(presentation),'Independent same-data layout plan')
    return expected

def authenticate_runtime_attachment(attachment):
    require(type(attachment) is dict and set(attachment)=={'status','reference','byte_count','manifest_bound','content_interpreted','numeric_input'},'Diagnostic declaration')
    require(attachment['status']=='OBSERVED_RUNTIME_DIAGNOSTIC_ATTACHMENT' and attachment['manifest_bound'] is True and attachment['content_interpreted'] is False and attachment['numeric_input'] is False,'Diagnostic-only scope')
    r=attachment['reference'];reference(r)
    require(Path(r['path'])==EXPORT/'条件历史比较.xlsx.inspect.ndjson','Manifest-bound fixed diagnostic path')
    require(type(attachment['byte_count']) is int and attachment['byte_count']>0,'Declared diagnostic size')
    h=hashlib.sha256();size=0
    with Path(r['path']).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block);size+=len(block)
    require(size==attachment['byte_count'] and h.hexdigest()==r['sha256'],'Diagnostic bytes differ')
    return dict(attachment)


def export_inventory():
    require({p.name for p in EXPORT.iterdir()}=={'started.json','export_manifest.json','条件历史比较.xlsx','条件历史比较.xlsx.inspect.ndjson',*[f'preview_{i}.png' for i in range(6)]},'Exact successful export files')

def guard(sources):
    for path,h in sources.items():
        hasher=hashlib.sha256()
        with Path(path).open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):hasher.update(block)
        require(hasher.hexdigest()==h,'Saved source drift')
def save(path,value):
    raw=encode(value)
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Written bytes');return dict(path=str(path),sha256=digest(raw))

def readback(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execution required')
    for r in BOUND.values():reference(r)
    require(not OUTPUT.exists(),'No overwrite or retry')
    sources={str(SOURCE):LOADED_SHA};blobs={}
    def read(r):
        reference(r);raw=Path(r['path']).read_bytes();require(digest(raw)==r['sha256'],'Consumed bytes');merge(sources,r['path'],r['sha256']);return raw
    for role,r in BOUND.items():
        blobs[role]=read(r)
    docs={k:json.loads(blobs[k]) for k in ('manifest','presentation','publication')}
    inherited=validate(docs['manifest'],docs['presentation'],docs['publication'],BOUND)
    for path,h in inherited.items():merge(sources,path,h)
    manifest=docs['manifest'];attachment=authenticate_runtime_attachment(manifest['runtime_diagnostic_attachment']);merge(sources,attachment['reference']['path'],attachment['reference']['sha256']);xlsx=read(manifest['workbook_reference'])
    for p in manifest['previews']:read({k:p[k] for k in ('path','sha256')})
    export_inventory()
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='DATED_WORKBOOK_READBACK_STARTED_V1',input_references=BOUND,retry_allowed=False))
        core=types.ModuleType('saved_xlsx_inspection');core.__file__=BOUND['core']['path'];exec(compile(blobs['core'],core.__file__,'exec'),core.__dict__)
        style_core=types.ModuleType('saved_xlsx_style_inspection');style_core.__file__=BOUND['style_core']['path'];exec(compile(blobs['style_core'],style_core.__file__,'exec'),style_core.__dict__)
        style_result=style_core.inspect_text_styles(xlsx,docs['presentation']);require(style_result['status']=='PASS','Exact display text styles required')
        result=core.inspect_export(xlsx,docs['presentation']);require(result['status']=='PASS' and result['layout']=='ACTUAL_FIXED_ROW4','Only actual workbook may pass')
        layout_result=inspect_readable_layout(xlsx,docs['presentation'],manifest['layout_adjustments'])
        report=dict(schema='DATED_COMPARISON_READABLE_WORKBOOK_INDEPENDENT_READBACK_V1',status='PASS',input_references=BOUND,workbook_reference=manifest['workbook_reference'],source_hashes=sources,inspection=result,exported_cell_values_independently_verified=True,visual_acceptance_passed=False,final_delivery_accepted=False,known_preview_limitation=LIMITATION,png_bytes_checked_but_visual_content_not_accepted=True,source_binding_scope='EXACT_DIRECT_EXPORT_AND_PRESENTATION_SOURCE_BYTES_NO_ECONOMIC_REPLAY',producer_called=False,economics_recomputed=False,formal_comparison_passed=False,future_independent_oos=False)
        report['layout_inspection']=layout_result
        report['started_dispatch_timing_verified']=False
        report['text_style_inspection']=style_result
        report['runtime_inspection_attachment']=attachment
        guard(sources);export_inventory();ref=save(OUTPUT/'independent_readback.json',report);guard(sources);export_inventory()
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact independent output');require(digest(Path(ref['path']).read_bytes())==ref['sha256'],'Report readback');return ref
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise
def expected_layout(presentation):
    tables=presentation['display']['tables'];require(len(tables)==6,'Six tables')
    weights,paths=tables[4:];require(weights['name']=='原始目标权重' and paths['name']=='来源索引' and len(paths['rows'])==5,'Fixed layout tables')
    def units(value):
        require(type(value) is str,'Layout source text')
        return sum(2 if ord(c)>255 else 1 for c in value)
    maximum=max([units(weights['headers'][3])]+[units(r[3]) for r in weights['rows']])
    width=max(48,maximum+6);require(width<=120,'Supported security width')
    rows=[dict(row=i+5,height=max(72,((units(r[1])+79)//80)*20+16)) for i,r in enumerate(paths['rows'])]
    require(all(r['height']<=400 for r in rows),'Supported source height')
    return dict(schema='DATED_SIX_TABLE_READABLE_LAYOUT_V1',security_id=dict(sheet=weights['name'],column='D',column_index=3,width=width,maximum_display_units=maximum,wrap=False),source_paths=dict(sheet=paths['name'],column='B',column_index=1,width=100,wrap=True,rows=rows),values_changed=False,text_styles_changed=False)


def inspect_readable_layout(xlsx_bytes,presentation,declared):
    """Check OOXML instructions, not pixel clipping or visual acceptance."""
    plan=expected_layout(presentation);exact(declared,plan,'Declared layout must match original data')
    require(type(xlsx_bytes) is bytes and 0<len(xlsx_bytes)<=128*1024*1024,'Bounded XLSX bytes')
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        info=z.infolist();names=[p.filename for p in info]
        require(len(names)==len(set(names)) and len(names)<=256 and sum(p.file_size for p in info)<=512*1024*1024,'ZIP bounds')
        def xml(path):
            b=z.read(path);require(b'<!DOCTYPE' not in b and b'<!ENTITY' not in b,'XML declarations forbidden');return ET.fromstring(b)
        mapping={}
        for r in xml('xl/_rels/workbook.xml.rels'):
            require(r.get('Id') not in mapping and r.get('TargetMode')!='External','Internal unique relationship')
            target=r.get('Target','');q=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            require(q.startswith('xl/') and '..' not in q.split('/'),'Internal worksheet');mapping[r.get('Id')]=q
        sheets=xml('xl/workbook.xml').findall('s:sheets/s:sheet',ns)
        require([s.get('name') for s in sheets]==[t['name'] for t in presentation['display']['tables']],'Exact sheet order')
        require(len({mapping[s.get('{'+rel+'}id')] for s in sheets})==6,'Six unique worksheet parts')
        xfs=xml('xl/styles.xml').findall('s:cellXfs/s:xf',ns);require(0<len(xfs)<=60000,'Style count')
        checked=0
        for number,key,col in ((4,'security_id',4),(5,'source_paths',2)):
            sh=sheets[number];require(sh.get('state','visible')=='visible','Relevant sheet hidden')
            doc=xml(mapping[sh.get('{'+rel+'}id')]);settings=plan[key]
            columns=doc.findall('s:cols/s:col',ns)
            match=[c for c in columns if int(c.get('min'))<=col<=int(c.get('max'))]
            require(len(match)==1,'One unambiguous column definition');definition=match[0]
            require(definition.get('hidden','0') in ('0','false') and Decimal(definition.get('width','NaN'))==Decimal(settings['width']),'Column width/visibility')
            rows={}
            for row in doc.findall('s:sheetData/s:row',ns):
                n=int(row.get('r'));require(n not in rows,'Duplicate row');rows[n]=row
            end=len(presentation['display']['tables'][number]['rows'])+4
            for n in range(5,end+1):
                require(n in rows,'Missing layout row');row=rows[n]
                require(row.get('hidden','0') in ('0','false'),'Hidden data row')
                if key=='source_paths':
                    require(row.get('customHeight') in ('1','true') and Decimal(row.get('ht','NaN'))==Decimal(settings['rows'][n-5]['height']),'Explicit source row height')
                address=settings['column']+str(n);cells=[c for c in row.findall('s:c',ns) if c.get('r')==address]
                require(len(cells)==1,'Missing/duplicate layout cell');index=int(cells[0].get('s','0'));require(0<=index<len(xfs),'Cell style index')
                xf=xfs[index];alignment=xf.find('s:alignment',ns)
                wrap='0' if alignment is None else alignment.get('wrapText','0')
                require(wrap in ('0','1','false','true') and (wrap in ('1','true')) is settings['wrap'],'Explicit effective wrap')
                if alignment is not None:
                    require(alignment.get('shrinkToFit','0') in ('0','false') and alignment.get('textRotation','0')=='0','No shrinking/rotation workaround')
                require(xf.get('applyAlignment','1') in ('1','true'),'Direct alignment must not be disabled')
                checked+=1
    return dict(schema='DATED_READABLE_LAYOUT_OOXML_INSPECTION_V1',status='PASS',layout_plan=plan,checked_layout_cell_count=checked,column_width_unit='OOXML_EXCEL_CHARACTER_WIDTH',row_height_unit='OOXML_POINTS',source_bytes_authenticated=False,visual_acceptance_passed=False,clipping_absence_proved=False,workbook_modified=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
