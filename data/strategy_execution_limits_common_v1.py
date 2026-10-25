"""Server-only execution limits from captured bytes and reviewed units.

No fetching or account writes. cap_store is an independently scoped server store;
its writes retain same-day conservative buy ceilings. The unit_review argument
must come from the server's raw-evidence reviewer, never an HTTP assertion.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical,replay,require
from data.strategy_account_target_inputs import stamp
from data.strategy_account_mark_reference import decode_current_mark as decode_intraday_reference
from data.strategy_halt_aware_pullback_sources_v1 import candidate_from_yahoo_bytes
from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY


def _build_execution_limits_core(*,state,target_quantities,market_capture,unit_review,cap_store,now,policy=None,quote_domain=None):
    policy=deepcopy(EXPERIMENTAL_POLICY if policy is None else policy)
    require(policy==EXPERIMENTAL_POLICY,'EXPLICIT_APPROVED_ENTRY_POLICY_REQUIRED')
    current=stamp(now);package=market_capture
    require(package['status']=='MARKS_CAPTURED_UNIT_REVIEW_REQUIRED' and package['account_id']==state['account_id'] and package['account_revision']==state['revision'],'MARK_ACCOUNT_MISMATCH')
    require(stamp(package['finished_at'])<=current,'MARK_CAPTURE_FUTURE')
    files,pins=package['files'],package['source_hashes']
    require(type(files)is dict and type(pins)is dict and set(files)==set(pins) and len(files)<=2000,'MARK_SOURCE_CLOSURE')
    require(all(type(raw)is bytes for raw in files.values()) and sum(map(len,files.values()))<=128*1024*1024,'MARK_PACKAGE_BUDGET')
    require(all(sha256(raw).hexdigest()==pins[path] for path,raw in files.items()),'MARK_SOURCE_CHANGED')
    marks=package['marks'];review=unit_review
    require(review['schema']=='STRATEGY_TARGET_UNIT_REVIEW_V1' and review['status']=='CONDITIONAL_CURRENT_UNITS_REVIEWED'
        and review['account_revision']==state['revision'] and review['marks_sha256']==sha256(canonical(marks)).hexdigest()
        and not review['unresolved'] and not review['pending_rights'] and review['coverage_complete'] is False
        and review['source_authenticated'] is False and 0<=(current-stamp(review['reviewed_at'])).total_seconds()<120,'UNIT_REVIEW_BINDING_INVALID')
    require(set(review['securities'])==set(marks),'UNIT_REVIEW_DOMAIN_MISMATCH')
    held_pending={sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
    if quote_domain is not None:
        require(target_quantities is None,'QUOTE_DOMAIN_IS_NOT_A_TARGET')
        needed=set(quote_domain);require(held_pending<=needed,'QUOTE_DOMAIN_OMITS_EXPOSURE')
    else:
        require(type(target_quantities)is dict and all(type(q)is int and q>=0 for q in target_quantities.values()),'TARGET_QUANTITIES_REQUIRED')
        needed={sid for sid,q in target_quantities.items() if q}|held_pending
    require(needed<=set(marks),'EXECUTION_MARK_DOMAIN_MISSING')
    validated={}
    for sid in sorted(needed):
        mark=marks[sid];unit=review['securities'][sid];identity=package['identities'][sid];ticker=identity['ticker']
        require(mark['security_id']==sid and mark['ticker']==ticker and identity['security_id']==sid,'EXECUTION_IDENTITY_MISMATCH')
        identity_refs=identity['source_references']
        require(bool(identity_refs) and len(identity_refs)==len(set(identity_refs))
            and set(identity_refs)==set(identity['source_hashes'])
            and all(identity['source_hashes'][path]==pins[path] for path in identity_refs),'IDENTITY_SOURCE_CLOSURE')
        require(unit['security_id']==sid and unit['current_mark_sha256']==sha256(canonical(mark)).hexdigest()
            and unit['current_price_basis']==mark['price_basis'] and unit['held_quantities_in_current_units'] is True
            and max(stamp(mark['captured_at']),stamp(mark['observed_at']))<=stamp(unit['covered_through'])<=current,'UNIT_REVIEW_MARK_MISMATCH')
        refs=mark['source_references'];require(len(refs)==2 and set(mark['source_hashes'])==set(refs) and all(mark['source_hashes'][p]==pins[p] for p in refs),'MARK_RECEIPT_CLOSURE')
        receipts=[p for p in refs if p.endswith('.receipt.json')];require(len(receipts)==1,'MARK_RECEIPT_REQUIRED')
        receipt=json.loads(files[receipts[0]]);raw=files[receipt['raw_path']]
        require(receipt['raw_path'] in refs and receipt['security_id']==sid and receipt['ticker']==ticker
            and receipt['raw_sha256']==pins[receipt['raw_path']] and receipt['captured_at']==mark['captured_at']
            and receipt.get('checked_at',receipt['captured_at'])==mark.get('checked_at',mark['captured_at'])
            and stamp(receipt['started_at'])<=stamp(receipt['captured_at'])<=stamp(receipt.get('checked_at',receipt['captured_at']))<=current
            and stamp(mark['observed_at'])<=stamp(receipt.get('checked_at',receipt['captured_at'])),'MARK_RECEIPT_MISMATCH')
        reference=decode_intraday_reference(raw,ticker=ticker,captured_at=stamp(receipt['captured_at']),now=current)
        require(reference['session']==package['session'] and reference['last_at']==mark['observed_at'] and Fraction(reference['last_price'])==Fraction(mark['price']),'MARK_RAW_MISMATCH')
        parameters=dict(raw=raw,expected_sha256=receipt['raw_sha256'],security_id=sid,ticker=ticker,session=reference['session'],
            session_open=reference['session_open'],session_close=reference['session_close'],captured_at=receipt['captured_at'],
            checked_at=receipt.get('checked_at',receipt['captured_at']),now=now,rebound_fraction=policy['rebound_fraction'],minimum_discount=policy['minimum_discount'],maximum_age_seconds=policy['maximum_age_seconds'])
        require(mark['price_basis']=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS','MARK_RAW_UNIT_MISMATCH')
        gap=1 if target_quantities is None else target_quantities.get(sid,0)-state['shares'].get(sid,0)
        for order in state['orders'].values():
            if target_quantities is not None and order['status']=='OPEN' and order['security_id']==sid:gap+=order['remaining_quantity']*(-1 if order['side']=='BUY' else 1)
        # Only a prospective buy requires the full session's pullback bars.
        # Near-quote sells remain available with a valid recent minute.
        if gap > 0:
            halt = package.get('halt_evidence')
            require(type(halt) is dict and set(halt) == {'raw_path', 'receipt_path'},
                    'HALT_EXECUTION_EVIDENCE_REQUIRED')
            require(halt['raw_path'] in files and halt['receipt_path'] in files,
                    'HALT_EXECUTION_SOURCE_CLOSURE')
            halt_receipt = json.loads(files[halt['receipt_path']])
            require(halt_receipt.get('raw_sha256') == pins[halt['raw_path']],
                    'HALT_EXECUTION_SOURCE_MISMATCH')
            parameters.update(halt_raw=files[halt['raw_path']], halt_receipt=halt_receipt)
            candidate_from_yahoo_bytes(previous_cap=None, **parameters)
        validated[sid]=(mark,ticker,parameters,reference,gap)
    result_marks={};limits={}
    for sid,(mark,ticker,parameters,reference,gap) in validated.items():
        parsed=cap_store.candidate(**parameters) if gap>0 else None
        last=Fraction(mark['price']);sell=Fraction(-(-last.numerator*100//last.denominator),100)
        candidate=parsed['candidate'] if parsed else None;result_marks[sid]=deepcopy(mark)
        limits[sid]=dict(security_id=sid,price_basis=mark['price_basis'],observed_at=mark['observed_at'],ticker=ticker,
            # The core requires both positive prices, but only consumes the side
            # of this bound net gap. This placeholder is NOT a buy suggestion.
            buy=candidate['limit_price'] if candidate else str(sell),sell=str(sell),
            buy_evaluated=bool(candidate),evaluated_account_revision=state['revision'],evaluated_net_gap=gap,
            reference_valid_until=candidate['reference_valid_until'] if candidate else reference['refresh_by'],
            buy_reason='日内回落价；同日已记录上限不随上涨抬高，允许不成交。' if candidate else '当前无净买入缺口，未评估买价；占位数值不可用于买入。',
            sell_reason='仅用于已决定减仓或退出的近现价限价；不是已验证卖点。',
            performance_validated=False,unit_review_coverage_complete=False,public_actions_may_be_missing=True,
            source_hashes=dict(mark['source_hashes'], **({
                package['halt_evidence']['raw_path']: pins[package['halt_evidence']['raw_path']],
                package['halt_evidence']['receipt_path']: pins[package['halt_evidence']['receipt_path']]
            } if gap > 0 else {})),cap_record_hash=parsed.get('cap_store_receipt',{}).get('record_hash') if parsed else None)
    return dict(marks=result_marks,limits=limits)


def build_real_execution_limits(**arguments):
    state=arguments["state"]
    require(replay(state["account_id"],[e["payload"] for e in state["events"]])==state,"ACCOUNT_REPLAY_MISMATCH")
    return _build_execution_limits_core(**arguments)
