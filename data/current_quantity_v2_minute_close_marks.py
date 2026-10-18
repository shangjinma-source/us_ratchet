"""Conditional close marks from saved minutes, never official auction closes.

Only subsequent close marks are supported. Late captured data must not be used
to backfill the simulation's contemporaneous initial valuation registration.
"""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
import json
from data.current_quantity_v2_late_unit_review import STATUS as LATE_STATUS, replay as replay_late_review

from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_paper_ledger import digest
from data.current_quantity_v2_completed_session_minutes import decode, stamp, require, LIMIT
from backtest.current_quantity_v2_simulated_settlement import _references


def build_marks(*, root, chain, session, session_close, captures, source_hashes,
                unit_reviews, observed_at):
    """Unit reviews are explicit pinned caller declarations, not certification.

    captures maps SID to raw/receipt/minutes paths; unit_reviews maps SID to a
    JSON declaration path. All references must belong to source_hashes.
    """
    chain = review_chain(chain); references = _references(chain)
    held = {s for s,q in chain['ledger']['shares'].items() if q}
    require(set(captures) == held == set(unit_reviews), 'COMPLETE_HELD_MARK_DOMAIN_REQUIRED')
    close, observed = stamp(session_close), stamp(observed_at)
    require(observed >= close, 'CLOSE_NOT_OBSERVED')
    require(close.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session
            and stamp(chain['ledger']['last_effective_at'])<=close, 'MARK_SESSION_OR_STATE_MISMATCH')
    root = Path(root).resolve(); cache={}; total=0
    def read(name):
        nonlocal total
        require(type(name) is str and name in source_hashes and '\\' not in name
                and ':' not in name and not PurePosixPath(name).is_absolute()
                and '..' not in PurePosixPath(name).parts, 'INVALID_MARK_SOURCE_PATH')
        if name in cache:return cache[name]
        path=root/name
        require(not path.is_symlink() and path.resolve().is_relative_to(root), 'INVALID_MARK_SOURCE_PATH')
        with path.open('rb') as stream: raw=stream.read(LIMIT+1)
        total+=len(raw)
        require(len(raw)<=LIMIT and total<=128*1024*1024 and
                sha256(raw).hexdigest()==source_hashes[name], 'MARK_SOURCE_CHANGED_OR_TOO_LARGE')
        cache[name]=raw;return raw
    marks={}
    for sid in sorted(held):
        paths=captures[sid]; require(set(paths)=={'raw','receipt','minutes'}, 'INVALID_CAPTURE_PATHS')
        raw=read(paths['raw']); receipt=json.loads(read(paths['receipt'])); saved=json.loads(read(paths['minutes']))
        reference=references[sid]; ticker=reference['ticker']; captured=stamp(receipt['captured_at'])
        require(receipt['status']=='COMPLETE_SESSION_MINUTES' and receipt['security_id']==sid
                and receipt['ticker']==ticker and receipt['session']==session
                and receipt['raw_sha256']==sha256(raw).hexdigest()
                and stamp(receipt['session_close'])==close and close<=captured<=observed,
                'CAPTURE_MARK_BINDING_MISMATCH')
        decoded=decode(raw,security_id=sid,ticker=ticker,session=session,
            session_open=receipt['session_open'],session_close=session_close,captured_at=receipt['captured_at'])
        decoded['source_reference']='sha256:'+receipt['raw_sha256']
        require(saved==decoded and decoded['status']=='COMPLETE_SESSION_MINUTES', 'SAVED_MINUTE_REPLAY_MISMATCH')
        last=decoded['minutes'][-1] if decoded['minutes'] else None
        require(last is not None and stamp(last['start'])==close-timedelta(minutes=1)
                and stamp(last['end'])==close, 'FINAL_MINUTE_REQUIRED')
        review=json.loads(read(unit_reviews[sid]))
        require(review.get('security_id')==sid and review.get('ticker')==ticker
                and review.get('price_basis')==reference['price_basis']
                and review.get('status') in ('NO_UNPROCESSED_ACTIONS', LATE_STATUS)
                and review.get('reference_sha256')==digest(reference)
                and review.get('reference_source_hashes')==reference['source_hashes']
                and review.get('capture_raw_sha256')==receipt['raw_sha256']
                and stamp(review['covered_from'])<=stamp(reference['captured_at'])
                and captured<=stamp(review['covered_through'])<=stamp(review['reviewed_at'])<=observed
                and type(review.get('source_references')) is list and review['source_references']
                and all(type(p) is str and p.strip() for p in review['source_references']),
                'MARK_UNIT_REVIEW_REQUIRED')
        for path in review['source_references']:read(path)
        if review['status'] == LATE_STATUS:
            replay_late_review(review, reference=reference, capture_raw_sha256=receipt['raw_sha256'],
                captured_at=captured, observed_at=observed, read=read)
        marks[sid]=dict(security_id=sid,ticker=ticker,session=session,currency='USD',
            price_basis=reference['price_basis'],price=last['close'],as_of=close.isoformat(),
            observed_at=captured.isoformat(),source_references=[*paths.values(),unit_reviews[sid]],
            mark_method='LAST_COMPLETE_MINUTE_CLOSE_PROXY',official_close=False,
            unit_review_scope=('BOUNDED_PUBLIC_SCREENING_MAY_MISS_ACTIONS' if review['status'] == LATE_STATUS
                               else 'PINNED_CALLER_DECLARATION_NOT_EXTERNAL_CERTIFICATION'))
    return dict(status='COMPLETE_CONDITIONAL_PROXY_MARKS',marks=marks,session=session,
        observed_at=observed.isoformat(),source_hashes={p:source_hashes[p] for p in cache},
        official_close=False,initial_valuation_supported=False,source_authenticated=False,
        limitations=['Final minute close is a proxy, not the official closing auction price.',
                    'Unit continuity is a pinned explicit caller review; provider event coverage alone is insufficient.',
                    'Late evidence retains its actual capture time; no initial valuation backfill.'])
