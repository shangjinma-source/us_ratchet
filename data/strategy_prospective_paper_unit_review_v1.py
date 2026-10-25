"""Formal paper replay/exposure to unchanged bounded unit and notice rules."""
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical
from backtest.current_strategy_prospective_paper_book_v1 import replay,project,_context
from data.strategy_account_mark_reference import decode_current_mark
from data.strategy_paper_application_descriptor_v1 import require,stamp
from data.strategy_verified_context_unit_review_v1 import review_verified_context_interval
from data.strategy_paper_execution_preview_v1 import _local_import_closure

CODE_PATHS=_local_import_closure({'data/strategy_prospective_paper_unit_review_v1.py'})


def _exposure_context(checked):
    """Only use after formal replay; include closed positions' cash rights."""
    times=[];exposed=set()
    for operation in checked['operations']:
        if operation['request']['kind']!='SETTLE':continue
        for oid,result in operation['outcome'].items():
            event=result.get('event_proposal')
            if event and event['type']=='FILL':
                times.append(event['executed_at']);exposed.add(checked['orders'][oid]['security_id'])
    needed=exposed|{sid for sid,q in checked['shares'].items() if q}|{
        order['security_id'] for order in checked['orders'].values() if order['closed'] is None}
    return times,exposed,needed


def review_prospective_units(*,book,authority,admitted_decisions,securities,market_capture,action_package,
        training_manifest_sha256,historical_search_arguments_sha256,historical_price_basis,training_closed_at,
        admitted_settlements=None,clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    original=deepcopy((book,authority,admitted_decisions,admitted_settlements,securities,market_capture,action_package))
    started=stamp(clock());app=_context(authority,started)
    require(CODE_PATHS<=set(app['code_sha256']),'PAPER_UNIT_CODE_SCOPE')
    checked=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    require(started>=stamp(checked['last_available_at']),'PAPER_UNIT_STATE_FUTURE')
    state=project(checked,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    times,exposed,needed=_exposure_context(checked)
    require(type(securities) is dict and needed<=set(securities),'PAPER_UNIT_EXPOSURE_DOMAIN')
    package=deepcopy(market_capture);marks=package['marks']
    require(package['account_id']==book['account_id'] and package['account_revision']==book['revision'],
        'PAPER_UNIT_MARK_ACCOUNT')
    require(set(package['files'])==set(package['source_hashes']) and
        all(sha256(raw).hexdigest()==package['source_hashes'][path] for path,raw in package['files'].items()),'PAPER_UNIT_MARK_SOURCE')
    decoded=[]
    for sid,mark in marks.items():
        require(set(mark['source_references'])==set(mark['source_hashes']),'PAPER_UNIT_MARK_REFERENCES')
        receipts=[]
        for path,digest in mark['source_hashes'].items():
            require(package['source_hashes'].get(path)==digest,'PAPER_UNIT_MARK_SOURCE')
            if path.endswith('.receipt.json'):receipts.append(json.loads(package['files'][path]))
        require(len(receipts)==1,'PAPER_UNIT_MARK_RECEIPT')
        receipt=receipts[0];raw=package['files'][receipt['raw_path']]
        require(receipt['security_id']==sid and receipt['ticker']==mark['ticker']==securities[sid]['ticker'] and
            receipt['raw_sha256']==sha256(raw).hexdigest() and receipt['captured_at']==mark['captured_at'],
            'PAPER_UNIT_MARK_RECEIPT')
        reference=decode_current_mark(raw,ticker=mark['ticker'],captured_at=stamp(mark['captured_at']),now=started,maximum_age_seconds=120)
        require(Fraction(reference['last_price'])==Fraction(mark['price']) and reference['last_at']==mark['observed_at'],
            'PAPER_UNIT_MARK_VALUE')
        decoded.append((raw,mark))
    review=review_verified_context_interval(state=state,exposure_times=times,exposed_security_ids=exposed,
        securities=deepcopy(securities),marks=marks,action_package=deepcopy(action_package),
        training_manifest_sha256=training_manifest_sha256,historical_search_arguments_sha256=historical_search_arguments_sha256,
        historical_price_basis=historical_price_basis,training_closed_at=training_closed_at,
        marks_sha256=sha256(canonical(marks)).hexdigest(),now=started.isoformat())
    _context(authority,started)
    require((book,authority,admitted_decisions,admitted_settlements,securities,market_capture,action_package)==original,'PAPER_UNIT_INPUT_CHANGED')
    final=stamp(clock());require(final>=started,'PAPER_UNIT_CLOCK_REVERSED')
    for raw,mark in decoded:
        decode_current_mark(raw,ticker=mark['ticker'],captured_at=stamp(mark['captured_at']),now=final,maximum_age_seconds=120)
    require((final-started).total_seconds()<120,'PAPER_UNIT_REVIEW_EXPIRED')
    rss_receipt=json.loads(action_package['files'][action_package['documents']['rss_receipt']])
    require((final-stamp(rss_receipt['received_at'])).total_seconds()<120,'PAPER_UNIT_REVIEW_EXPIRED')
    require((book,authority,admitted_decisions,admitted_settlements,securities,market_capture,action_package)==original,'PAPER_UNIT_INPUT_CHANGED')
    review['reviewed_at']=final.isoformat()
    return review


def review_prospective_execution_sources(**arguments):
    """Keep action raw closure in the exact package subsequently limit-admitted."""
    original=deepcopy(arguments)
    package=deepcopy(arguments['market_capture'])
    for path,raw in arguments['action_package']['files'].items():
        digest=sha256(raw).hexdigest()
        require(path not in package['source_hashes'] or
            (package['source_hashes'][path]==digest and package['files'][path]==raw),'PAPER_UNIT_SOURCE_COLLISION')
        package['files'][path]=raw;package['source_hashes'][path]=digest
    require(sum(map(len,package['files'].values()))<=128*1024*1024,'PAPER_UNIT_PACKAGE_BUDGET')
    review=review_prospective_units(**dict(original,market_capture=package))
    require(arguments==original,'PAPER_UNIT_INPUT_CHANGED')
    return dict(status='CONDITIONAL_PAPER_UNITS_REVIEWED',market_capture=package,unit_review=review,
        account_mutated=False,orders_created=False)
