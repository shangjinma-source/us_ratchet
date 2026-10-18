"""Immutable saved XLSX readback; numeric acceptance is not visual acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import types
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
EXPORT=ROOT/'outputs/01a0cc4a-c717-7813-843e-86aca0d15714/dated_comparison_workbook_20261003_v1'
OUTPUT=ROOT/'data/cache/research/dated_comparison_workbook_independent_readback_20261003_v1'
RUNTIME_INSPECTION_SIZE=120313835
BOUND={
 'runtime_inspection':{'path':str(EXPORT/'条件历史比较.xlsx.inspect.ndjson'),'sha256':'e18b3c5da117c5fc80fbbe84686ede80416cb4341d0910123b3bbffe041670fc'},
 'manifest':{'path':str(EXPORT/'export_manifest.json'),'sha256':'214a2dde89115a130dd0f803b69e65f45374fe59f1d4579724fe26ecac903aee'},
 'presentation':{'path':str(ROOT/'data/cache/research/dated_comparison_presentation_20261003_v1/presentation.json'),'sha256':'a586ab8ee02f6cc0b87bd0bddda9b38bb4cfcc5364873b40e6f77458afd3231c'},
 'publication':{'path':str(ROOT/'data/cache/research/dated_comparison_presentation_20261003_v1/publication.json'),'sha256':'79120009b95bd74675112ddb120dd29b2cab4deb4f67748acbd0af03ba2397ef'},
 'exporter':{'path':str(ROOT/'scripts/ndx_dated_comparison_workbook_publish_20261003.mjs'),'sha256':'c36ba82c307fc5ad0dd965578accffe44896170155f02d9435e5c0bb735fef43'},
 'builder':{'path':str(ROOT/'scripts/ndx_dated_comparison_workbook_20261003.mjs'),'sha256':'8bbbc945191a9ca4166574f5fdb916e9aa09f48bb710f0ddba056fc1763714b1'},
 'core':{'path':str(ROOT/'backtest/ndx_dated_comparison_xlsx_inspection_research.py'),'sha256':'9bfc477ceb4c1b0bbcb6155e6e7e48856645e5d3a3db877ef303403207b4d273'},
 'style_core':{'path':str(ROOT/'backtest/ndx_dated_exact_text_style_inspection_research.py'),'sha256':'5a7d48b1c52031b03e1ebbbc128534b42bcea003f259d2390f5a3ff9c8401d69'}}
LIMITATION='Numeric-looking text may render rounded or without leading zeros; exported text requires independent verification'
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
    require(manifest['schema']=='DATED_COMPARISON_WORKBOOK_EXPORT_V1' and manifest['status']=='EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE','Export state')
    require(presentation['schema']=='SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1','Presentation schema')
    require(publication['schema']=='DATED_COMPARISON_PRESENTATION_PUBLICATION_V1' and publication['status']=='PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY','Presentation receipt')
    exact(publication['presentation_reference'],refs['presentation'],'Presentation receipt reference');exact(publication['source_hashes'],presentation['source_hashes'],'Presentation source map')
    exact(manifest['input_references'],{k:refs[k] for k in ('presentation','publication','builder')},'Export inputs')
    expected={refs[k]['path']:refs[k]['sha256'] for k in ('exporter','presentation','publication','builder')}
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
    return expected

def authenticate_runtime_attachment():
    r=BOUND['runtime_inspection'];reference(r)
    require(Path(r['path'])==EXPORT/'条件历史比较.xlsx.inspect.ndjson','Fixed runtime diagnostic path')
    h=hashlib.sha256();size=0
    with Path(r['path']).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block);size+=len(block)
    require(size==RUNTIME_INSPECTION_SIZE and h.hexdigest()==r['sha256'],'Runtime diagnostic bytes')
    return dict(status='OBSERVED_RUNTIME_DIAGNOSTIC_ATTACHMENT',reference=dict(r),byte_count=size,manifest_bound=False,content_interpreted=False,numeric_input=False)

def export_inventory():
    require({p.name for p in EXPORT.iterdir()}=={'started.json','export_manifest.json','条件历史比较.xlsx','条件历史比较.xlsx.inspect.ndjson',*[f'preview_{i}.png' for i in range(6)]},'Exact successful export files')

def guard(sources):
    for path,h in sources.items():
        if path==BOUND['runtime_inspection']['path']:authenticate_runtime_attachment()
        else:require(digest(Path(path).read_bytes())==h,'Saved source drift')
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
    attachment=authenticate_runtime_attachment();merge(sources,BOUND['runtime_inspection']['path'],BOUND['runtime_inspection']['sha256'])
    for role,r in BOUND.items():
        if role!='runtime_inspection':blobs[role]=read(r)
    docs={k:json.loads(blobs[k]) for k in ('manifest','presentation','publication')}
    inherited=validate(docs['manifest'],docs['presentation'],docs['publication'],BOUND)
    for path,h in inherited.items():merge(sources,path,h)
    manifest=docs['manifest'];xlsx=read(manifest['workbook_reference'])
    for p in manifest['previews']:read({k:p[k] for k in ('path','sha256')})
    export_inventory()
    guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(schema='DATED_WORKBOOK_READBACK_STARTED_V1',input_references=BOUND,retry_allowed=False))
        core=types.ModuleType('saved_xlsx_inspection');core.__file__=BOUND['core']['path'];exec(compile(blobs['core'],core.__file__,'exec'),core.__dict__)
        style_core=types.ModuleType('saved_xlsx_style_inspection');style_core.__file__=BOUND['style_core']['path'];exec(compile(blobs['style_core'],style_core.__file__,'exec'),style_core.__dict__)
        style_result=style_core.inspect_text_styles(xlsx,docs['presentation']);require(style_result['status']=='PASS','Exact display text styles required')
        result=core.inspect_export(xlsx,docs['presentation']);require(result['status']=='PASS' and result['layout']=='ACTUAL_FIXED_ROW4','Only actual workbook may pass')
        report=dict(schema='DATED_COMPARISON_WORKBOOK_INDEPENDENT_READBACK_V1',status='PASS',input_references=BOUND,workbook_reference=manifest['workbook_reference'],source_hashes=sources,inspection=result,exported_cell_values_independently_verified=True,visual_acceptance_passed=False,final_delivery_accepted=False,known_preview_limitation=LIMITATION,png_bytes_checked_but_visual_content_not_accepted=True,source_binding_scope='EXACT_DIRECT_EXPORT_AND_PRESENTATION_SOURCE_BYTES_NO_ECONOMIC_REPLAY',producer_called=False,economics_recomputed=False,formal_comparison_passed=False,future_independent_oos=False)
        report['text_style_inspection']=style_result
        report['runtime_inspection_attachment']=attachment
        guard(sources);export_inventory();ref=save(OUTPUT/'independent_readback.json',report);guard(sources);export_inventory()
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact independent output');require(digest(Path(ref['path']).read_bytes())==ref['sha256'],'Report readback');return ref
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))
