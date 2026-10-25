"""Paper context around current transport capture; creates evidence, never orders.

Capture is not unit/source admission. The original daily/action/unit validators
must still run before a formal decision is admitted to the paper ledger.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import time
import os
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require,stamp
from backtest.current_strategy_prospective_paper_book_v2 import replay,project,_context
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_verified_context_market_capture_v1 import VerifiedContextDailyMarketCapture
from data.strategy_halt_market_capture_v1 import HaltMarketCaptureV1
from data.strategy_account_action_capture_v6 import StrategyAccountActionCaptureV6
from data.strategy_prospective_paper_unit_review_v2 import _exposure_context
from data.strategy_paper_execution_preview_v1 import _local_import_closure

CODE_PATHS=_local_import_closure({'data/strategy_prospective_paper_source_capture_v2.py'})


def _save(path,value):
    raw=canonical(value)
    with Path(path).open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def _archive_packages(directory,market,actions):
    """Create-only raw closure with logical indexes; no interpretation/approval."""
    blobs=directory/'blobs';blobs.mkdir()
    seen={};indexes={}
    for name,package in (('market',market),('actions',actions)):
        require(set(package['files'])==set(package['source_hashes']),'PAPER_CAPTURE_ARCHIVE_DOMAIN')
        for logical,raw in package['files'].items():
            digest=sha256(raw).hexdigest()
            require(digest==package['source_hashes'][logical],'PAPER_CAPTURE_ARCHIVE_HASH')
            if digest not in seen:
                require(sum(seen.values())+len(raw)<=256*1024*1024,'PAPER_CAPTURE_ARCHIVE_BUDGET')
                with (blobs/(digest+'.bin')).open('xb') as stream:
                    stream.write(raw);stream.flush();os.fsync(stream.fileno())
                seen[digest]=len(raw)
            require((blobs/(digest+'.bin')).read_bytes()==raw,'PAPER_CAPTURE_ARCHIVE_READBACK')
        indexes[name]={k:v for k,v in package.items() if k!='files'}
    index=dict(schema='PAPER_CAPTURE_SOURCE_ARCHIVE_V1',packages=indexes,blobs=seen)
    _save(directory/'archive.json',index)
    return sha256(canonical(index)).hexdigest()


def capture_prospective_sources(*,book,authority,admitted_decisions,identity_resolver,
        securities,target_quantities,window_start,output_directory,admitted_settlements=None,
        clock=None,market_fetch=None,halt_fetch=None,action_fetch=None,rss_fetch=None):
    """Bound immutable paper revision to V20 mark/halt/action raw evidence.

    Injected fetches are transport test seams, not trusted approval. Descriptor
    code closure and normal source reviewers remain required. All pending and
    held symbols must be present even when absent from this month's selection.
    """
    clock=clock or (lambda:datetime.now(timezone.utc))
    original=deepcopy((book,authority,admitted_decisions,admitted_settlements,securities,target_quantities))
    began=stamp(clock());app=_context(authority,began)
    require(CODE_PATHS<=set(app['code_sha256']),'PAPER_CAPTURE_CODE_SCOPE')
    require(type(identity_resolver) is PinnedStrategyIdentity,'PAPER_CAPTURE_PINNED_IDENTITY_REQUIRED')
    verified=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    require(began>=stamp(verified['last_available_at']),'PAPER_CAPTURE_CLOCK')
    state=project(verified,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    state['orders']={o['order_id']:dict(o,status='OPEN') for o in state['pending_orders']}
    exposure_times,unused_exposed,exposure_domain=_exposure_context(verified)
    needed=exposure_domain|set(target_quantities)
    require(type(securities) is dict and needed<=set(securities) and len(securities)<=200,'PAPER_CAPTURE_SECURITY_DOMAIN')
    require(all(stamp(window_start)<=stamp(at) for at in exposure_times),'PAPER_CAPTURE_EXPOSURE_WINDOW')
    require(all(type(q) is int and q>=0 for q in target_quantities.values()),'PAPER_CAPTURE_TARGET_QUANTITY')
    directory=Path(output_directory).absolute()
    require(not any(p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&0x400) for p in [directory,*directory.parents]),'PAPER_CAPTURE_PATH_ALIAS')
    directory.mkdir(parents=True,exist_ok=False)
    _save(directory/'started.json',dict(scope='PAPER_SOURCE_CAPTURE_ONLY',account_id=book['account_id'],
        account_revision=book['revision'],descriptor_sha256=book['descriptor_sha256'],started_at=began.isoformat()))
    timer=time.monotonic()
    try:
        options=dict(identity_resolver=identity_resolver,clock=clock)
        if market_fetch is not None:options['fetch']=market_fetch
        halt_options=dict(clock=clock)
        if halt_fetch is not None:halt_options['fetch']=halt_fetch
        market=HaltMarketCaptureV1(VerifiedContextDailyMarketCapture(**options),**halt_options).capture(
            state=state,candidate_metadata=deepcopy(securities),output_directory=directory/'market')
        market_seconds=time.monotonic()-timer
        action_options=dict(clock=clock)
        if action_fetch is not None:action_options['fetch']=action_fetch
        if rss_fetch is not None:action_options['rss_fetch']=rss_fetch
        request=dict(account_id=book['account_id'],state_revision=book['revision'],window_start=stamp(window_start).isoformat(),
            observed_floor=began.isoformat(),securities=deepcopy(securities),current_target_quantities=deepcopy(target_quantities))
        actions=StrategyAccountActionCaptureV6(**action_options).capture(request,directory/'actions')
        archive_hash=_archive_packages(directory,market,actions)
        _context(authority,stamp(clock()))
        require((book,authority,admitted_decisions,admitted_settlements,securities,target_quantities)==original,'PAPER_CAPTURE_INPUT_CHANGED')
        final=stamp(clock());require(final>=began,'PAPER_CAPTURE_CLOCK')
        receipt=dict(scope='PAPER_SOURCE_CAPTURE_ONLY',status='CAPTURED_NOT_ADMITTED',account_id=book['account_id'],
            account_revision=book['revision'],descriptor_sha256=book['descriptor_sha256'],started_at=began.isoformat(),finished_at=final.isoformat(),
            market_source_sha256=market['source_hashes'],action_source_sha256=actions['source_hashes'],
            archive_sha256=archive_hash,
            market_seconds=market_seconds,total_seconds=time.monotonic()-timer,securities_count=len(securities),
            source_authenticated=False,unit_review_completed=False,account_mutated=False,orders_created=False)
        _save(directory/'complete.json',receipt)
        return dict(receipt=receipt,market_capture=market,action_capture=actions)
    except BaseException:
        _save(directory/'failed.json',dict(status='FAILED_PRESERVED',account_mutated=False,orders_created=False))
        raise
