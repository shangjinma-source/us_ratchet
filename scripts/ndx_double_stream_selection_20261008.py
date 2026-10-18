"""Pending full-domain double selection publisher; saved bytes only."""
import argparse
import hashlib
import json
import types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
IO=ROOT/'scripts/ndx_double_stream_selection_sources_20261008.py';IO_SHA=None
PURE=ROOT/'backtest/ndx_double_stream_selection_research.py';PURE_SHA=None
OUTPUT=ROOT/'data/cache/research/double_stream_selection_20261008_v1'
BOUND={k:(None,None)for k in ('preparation','request','publication','audit','reader','worker','registration','decoder')}
FLAGS=dict.fromkeys(('evaluation_reperformed','account_executed','orders_executed','fit_executed','future_returns_used','cross_family_winner_selected','point_in_time_verified','promotion_allowed','full_ndx_certified','execution_authorized'),False)

def module(path,sha):
    if type(sha)is not str or len(sha)!=64 or set(sha)-set('0123456789abcdef'):raise ValueError('Pending source SHA')
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Source SHA')
    result=types.ModuleType('_bound_double_selection_'+Path(path).stem);result.__file__=str(path);exec(compile(raw,str(path),'exec'),result.__dict__);return result

def run(*,execute=False):
    if execute is not True:raise ValueError('Explicit saved selection run')
    for path,sha in BOUND.values():
        if type(path)is not str or type(sha)is not str or len(sha)!=64 or set(sha)-set('0123456789abcdef'):raise ValueError('Pending actual input anchors')
    io=module(IO,IO_SHA);pure=module(PURE,PURE_SHA);refs={k:dict(path=p,sha256=h)for k,(p,h)in BOUND.items()};state=io.prepare(refs)
    for path,sha in ((IO,IO_SHA),(PURE,PURE_SHA),(SOURCE,LOADED)):io.merge(state['sources'],str(path),sha)
    io.guard(state['sources']);io.safe(OUTPUT);io.require(not OUTPUT.exists(),'Create-only selection namespace');OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=io.save(OUTPUT/'started.json',dict(schema='DOUBLE_STREAM_SELECTION_STARTED_V1',input_references=refs,source_hashes=state['sources'],**FLAGS))
        selection=pure.select(prepared=state['prepared'],audit=state['audit'],records=io.records(state))
        for unused in io.records(state,metadata_only=True):raise ValueError('Metadata traversal yielded economics')
        result=io.save(OUTPUT/'selection.json',dict(schema='DOUBLE_STREAM_SELECTION_DOCUMENT_V1',selection=selection,input_references=refs,started_reference=started,source_hashes=state['sources'],observed_original_audit_start_reference=state['observed_audit_start_reference'],original_audit_start_externally_anchored=False,**FLAGS))
        publication=io.save(OUTPUT/'publication.json',dict(schema='DOUBLE_STREAM_SELECTION_PUBLICATION_V1',status='PUBLISHED_COMPLETE_DOMAIN_SELECTION_PENDING_INDEPENDENT_READBACK',selection_reference=result,input_references=refs,source_hashes=state['sources'],**FLAGS))
        for unused in io.records(state,metadata_only=True):raise ValueError('Metadata traversal yielded economics')
        io.exact_inventory(OUTPUT,{'started.json','selection.json','publication.json'})
        for r in (started,result,publication):io.require(io.filehash(r['path'])==r['sha256'],'Final saved selection SHA')
        return result
    except BaseException as error:
        io.save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,**FLAGS));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
