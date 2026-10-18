"""Independent saved double selection reduction; never imports its publisher."""
import argparse
import hashlib
import json
import types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
IO=ROOT/'scripts/ndx_double_stream_selection_sources_20261008.py';IO_SHA=None
CHECKER=ROOT/'backtest/ndx_double_stream_selection_inspection_research.py';CHECKER_SHA=None
PUBLISHER=ROOT/'scripts/ndx_double_stream_selection_20261008.py';PUBLISHER_SHA=None
PURE=ROOT/'backtest/ndx_double_stream_selection_research.py';PURE_SHA=None
OUTPUT=ROOT/'data/cache/research/double_stream_selection_independent_readback_20261008_v1'
SELECTION_REFERENCE=None
PUBLICATION_REFERENCE=None
BOUND={k:(None,None)for k in ('preparation','request','publication','audit','reader','worker','registration','decoder')}
FLAGS=dict.fromkeys(('evaluation_reperformed','account_executed','orders_executed','fit_executed','future_returns_used','cross_family_winner_selected','point_in_time_verified','promotion_allowed','full_ndx_certified','execution_authorized'),False)

def module(path,sha):
    if type(sha)is not str or len(sha)!=64 or set(sha)-set('0123456789abcdef'):raise ValueError('Pending source SHA')
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Source SHA')
    value=types.ModuleType('_double_selection_readback_'+Path(path).stem);value.__file__=str(path);exec(compile(raw,str(path),'exec'),value.__dict__);return value

def run(*,execute=False):
    if execute is not True:raise ValueError('Explicit independent readback')
    if SELECTION_REFERENCE is None or PUBLICATION_REFERENCE is None:raise ValueError('Pending original publication anchors')
    io=module(IO,IO_SHA);checker=module(CHECKER,CHECKER_SHA);refs={k:dict(path=p,sha256=h)for k,(p,h)in BOUND.items()};state=io.prepare(refs)
    document=io.read(SELECTION_REFERENCE,32*1024**2);publication=io.read(PUBLICATION_REFERENCE,1024**2)
    io.require(document['schema']=='DOUBLE_STREAM_SELECTION_DOCUMENT_V1'and publication['schema']=='DOUBLE_STREAM_SELECTION_PUBLICATION_V1','Saved selection roles')
    io.require(publication['status']=='PUBLISHED_COMPLETE_DOMAIN_SELECTION_PENDING_INDEPENDENT_READBACK','Original publication state')
    io.exact(publication['selection_reference'],SELECTION_REFERENCE,'Published selection SHA')
    io.exact(document['input_references'],refs,'Independent source anchors');io.exact(publication['input_references'],refs,'Publication anchors')
    io.exact(document['observed_original_audit_start_reference'],state['observed_audit_start_reference'],'Observed original audit START bytes');io.require(document['original_audit_start_externally_anchored']is False,'No invented upstream START authentication')
    for value in (document,publication):
        for k in FLAGS:io.require(value[k]is False,'No gained authority')
    expected=dict(state['sources'])
    for path,sha in ((IO,IO_SHA),(PURE,PURE_SHA),(PUBLISHER,PUBLISHER_SHA)):io.merge(expected,str(path),sha)
    io.exact(document['source_hashes'],expected,'Exact producer source closure');io.exact(publication['source_hashes'],expected,'Published source closure')
    original=Path(SELECTION_REFERENCE['path']).parent;io.exact(PUBLICATION_REFERENCE['path'],str(original/'publication.json'),'Original publication namespace')
    io.exact(document['started_reference']['path'],str(original/'started.json'),'Original started namespace')
    started=io.read(document['started_reference']);io.require(started['schema']=='DOUBLE_STREAM_SELECTION_STARTED_V1','Original started role');io.exact(started['source_hashes'],expected,'Original start closure');io.exact(started['input_references'],refs,'Original start refs')
    for k in FLAGS:io.require(started[k]is False,'Original START false authority')
    state['sources']=expected
    for r in (SELECTION_REFERENCE,PUBLICATION_REFERENCE,document['started_reference']):io.merge(state['sources'],r['path'],r['sha256'])
    for path,sha in ((SOURCE,LOADED),(CHECKER,CHECKER_SHA)):io.merge(state['sources'],str(path),sha)
    def guard():
        io.exact_inventory(original,{'started.json','selection.json','publication.json'})
        for unused in io.records(state,metadata_only=True):raise ValueError('Unexpected economics')
    guard();io.safe(OUTPUT);io.require(not OUTPUT.exists(),'Create-only independent namespace');OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        own_start=io.save(OUTPUT/'started.json',dict(schema='DOUBLE_STREAM_SELECTION_READBACK_STARTED_V1',selection_reference=SELECTION_REFERENCE,source_hashes=state['sources'],**FLAGS))
        inspection=checker.inspect(prepared=state['prepared'],audit=state['audit'],records=io.records(state),selection=document['selection'])
        guard();result=io.save(OUTPUT/'independent_readback.json',dict(schema='DOUBLE_STREAM_SELECTION_INDEPENDENT_READBACK_V1',status='PASS_COMPLETE_DOMAIN',selection_reference=SELECTION_REFERENCE,publication_reference=PUBLICATION_REFERENCE,input_references=refs,inspection=inspection,source_hashes=state['sources'],**FLAGS))
        guard();io.exact_inventory(OUTPUT,{'started.json','independent_readback.json'})
        for r in (own_start,result):io.require(io.filehash(r['path'])==r['sha256'],'Independent output SHA')
        return result
    except BaseException as error:
        io.save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,**FLAGS));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
