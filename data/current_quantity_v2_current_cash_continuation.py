"""Fixed accepted current-unit targets; pure declarations, no raw authentication.

Continuity must explicitly cover the first accepted quote to the new capture.
No historical quantity conversion, implicit corporate-action handling or search.
"""
from copy import deepcopy
import base64
import json
from hashlib import sha256
from datetime import timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo
from data.current_quantity_v2_difference_plan import require,stamp,number,allocate_differences
from data.current_quantity_v2_paper_ledger import digest
from data.current_quantity_v2_current_cash_plan import SCOPE,BASIS


def frozen_pullback_policy(original):
    frozen=original['causal_inputs']['frozen_execution_package'];docs=frozen['documents']
    if 'pullback_policy' not in docs:
        require('pullback_proofs' not in docs,'COMPLETE_PULLBACK_POLICY_REQUIRED')
        return None
    require('pullback_proofs' in docs,'COMPLETE_PULLBACK_POLICY_REQUIRED')
    path=docs['pullback_policy']
    require(path in frozen['files_base64'] and path in frozen['source_hashes'],'FROZEN_PULLBACK_POLICY_REQUIRED')
    raw=base64.b64decode(frozen['files_base64'][path],validate=True)
    require(sha256(raw).hexdigest()==frozen['source_hashes'][path],'FROZEN_PULLBACK_POLICY_HASH_MISMATCH')
    return json.loads(raw)


def proposal_for_current_cash(ledger,inputs,now):
    original=ledger['acceptance']['proposal'];causal=original['causal_inputs'];now=stamp(now)
    pullback_policy=frozen_pullback_policy(original)
    require(original['target_scope']==SCOPE,'CURRENT_CASH_SCOPE_REQUIRED')
    require(all(o['closed'] in ('FILLED','CANCELLED','EXPIRED') for o in ledger['orders'].values())
        and number(ledger['reserved_cash'])==0 and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
    require(set(inputs)=={'securities','execution_references','unit_continuity','source_hashes'},'EXECUTION_INPUT_FIELDS')
    require(now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')==original['target_month'],'RESELECT_REQUIRED')
    observed=max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))
    require(observed<=now,'LEDGER_FROM_FUTURE')
    oldpins=causal['frozen_execution_package']['source_hashes'];pins=inputs['source_hashes']
    require(all(pins.get(p)==h for p,h in oldpins.items()),'ORIGINAL_SOURCE_CHANGED')
    targets=ledger['target_quantities'];held=ledger['shares']
    require(targets==original['target_quantities'],'FIXED_TARGET_CHANGED')
    needed={s for m in (targets,held) for s,q in m.items() if q}
    require(all(set(inputs[k])==needed for k in ('securities','execution_references','unit_continuity')),'COMPLETE_HELD_TARGET_DOMAIN_REQUIRED')
    first={r['security_id']:r for r in original['rows']};limits={};deadlines=[];bounded_reviews=[]
    for sid in sorted(needed):
        security=inputs['securities'][sid];ref=inputs['execution_references'][sid];unit=inputs['unit_continuity'][sid]
        bounded=unit.get('status')=='NO_KNOWN_UNIT_CHANGE_UNDER_BOUNDED_PUBLIC_REVIEW'
        require(type(unit)is dict and set(unit)==({'security_id','ticker','security_class','price_basis',
            'initial_price_basis','status','initial_execution_target_id','initial_reference_source_hashes',
            'reference_source_hashes','covered_from','covered_through','reviewed_at','source_references'} | ({'bounded_evidence'} if bounded else set())),
            'UNIT_CONTINUITY_FIELDS')
        require(security==original['securities'][sid],'CURRENT_SECURITY_CHANGED')
        require(ref['security_id']==sid and ref['ticker']==security['ticker'] and ref['currency']=='USD'
            and ref['price_basis'] in (BASIS,'CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'),'QUOTE_IDENTITY_MISMATCH')
        captured,checked,tick,start,end,deadline,opening,closing=map(stamp,[ref[k] for k in
            ('captured_at','checked_at','last_at','minute_start','minute_end','valid_until','session_open','session_close')])
        require(opening<=tick<=captured<=checked<=now<deadline<=closing and tick>=observed
            and opening<=start and start.second==0 and start.microsecond==0
            and end-start==timedelta(minutes=1) and end<=captured
            and deadline<=min(tick+timedelta(seconds=120),end+timedelta(seconds=120)), 'STALE_OR_INVALID_QUOTE')
        require(all(t.astimezone(ZoneInfo('America/New_York')).date().isoformat()==ref['session']
            for t in (now,opening,closing,start,end,tick)), 'QUOTE_SESSION_MISMATCH')
        rp=ref['source_hashes'];require(rp and all(pins.get(p)==h for p,h in rp.items()),'QUOTE_SOURCE_MISMATCH')
        require(unit['security_id']==sid and unit['ticker']==security['ticker']
            and unit['security_class']==security['security_class'] and unit['price_basis']==ref['price_basis'] and unit['initial_price_basis']==BASIS
            and (bounded or unit['status']=='NO_UNPROCESSED_ACTIONS')
            and unit['initial_execution_target_id']==original['execution_target_id']
            and unit['initial_reference_source_hashes']==first[sid]['source_hashes']
            and unit['reference_source_hashes']==rp
            and stamp(unit['covered_from'])<=stamp(first[sid]['captured_at'])
            and captured<=stamp(unit['covered_through'])<=stamp(unit['reviewed_at'])<=now
            and unit['source_references'] and all(p in pins for p in unit['source_references']), 'UNIT_CONTINUITY_REQUIRED')
        if bounded:
            from data.current_quantity_v2_bounded_unit_review import replay_bounded_review
            evidence=unit['bounded_evidence']
            require(all(pins.get(p)==h for p,h in evidence['source_hashes'].items()) and all(evidence[k] in unit['source_references'] for k in ('rss_raw_path','rss_receipt_path')), 'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE')
            bounded_reviews.append(replay_bounded_review(unit,security=security,origin=first[sid],current=ref,now=now))
        last,low=number(ref['last_price']),number(ref['minute_low']);require(min(last,low)>0,'INVALID_PRICE')
        buy=Fraction(min(last,low)*100//1,100);sell=Fraction(-(-last*100//1),100)
        if pullback_policy is not None:
            from data.current_quantity_v2_pullback_entry import VERSION as pullback_version, digest as policy_digest
            candidate=ref.get('pullback')
            require(type(candidate)is dict and candidate.get('execution_policy')==pullback_policy,
                    'CONTINUATION_PULLBACK_POLICY_REQUIRED')
            require(candidate['binding']['security_id']==sid and candidate['binding']['ticker']==security['ticker']
                    and candidate['binding']['session']==ref['session'],'CONTINUATION_PULLBACK_IDENTITY_MISMATCH')
            buy=number(candidate['limit_price'])
            ratio=number(pullback_policy['rebound_fraction']);discount=number(pullback_policy['minimum_discount'])
            expected_policy=dict(version=pullback_version,rebound_fraction=str(ratio),
                minimum_discount=str(discount),maximum_age_seconds=pullback_policy['maximum_age_seconds'])
            require(candidate.get('schema')==pullback_version and candidate.get('policy')==expected_policy
                    and candidate['binding']['policy_id']==policy_digest(expected_policy),
                    'CONTINUATION_PULLBACK_POLICY_MISMATCH')
            require(0<ratio<1 and 0<discount<1 and number(candidate['last_price'])==last
                    and now<stamp(candidate['reference_valid_until'])
                    and deadline<=stamp(candidate['reference_valid_until']),'INVALID_PULLBACK_REFERENCE')
            anchor=min(number(candidate['observed_session_low']),last)
            require(anchor>0,'INVALID_PULLBACK_REFERENCE')
            ceiling=min(anchor+ratio*(last-anchor),last*(1-discount))
            prior=candidate['prior_cap']
            if prior is not None:
                require(prior['binding']==candidate['binding']
                        and opening<=stamp(prior['observed_at'])<=captured,'INVALID_PULLBACK_PRIOR_CAP')
                cap=number(prior['limit_price']);require(cap>0,'INVALID_PULLBACK_PRIOR_CAP')
                ceiling=min(ceiling,cap)
            require(buy==Fraction(ceiling*100//1,100) and 0<buy<last,'INVALID_PULLBACK_LIMIT')
        else:
            require('pullback' not in ref,'UNAUTHORIZED_CONTINUATION_POLICY_CHANGE')
        require(buy>0,'NONPOSITIVE_LIMIT');limits[sid]=(buy,sell);deadlines.append(deadline)
    orders,waiting,reserved,factor=allocate_differences(targets=targets,held=held,cash=number(ledger['cash']),limits=limits)
    binding=dict(account_id=ledger['account_id'],prior_revision=ledger['revision'],
        capital_decision_id=original['capital_decision_id'],initial_execution_target_id=original['execution_target_id'],
        target_month=original['target_month'],target_quantities=deepcopy(targets),cash=ledger['cash'],shares=deepcopy(held),
        recorded_fees=ledger['recorded_fees'],created_at=now.isoformat(),execution_inputs=deepcopy(inputs))
    result=dict(schema='V2_CURRENT_CASH_FIXED_MONTH_CONTINUATION_V1',proposal_id=digest(binding),binding=binding,
        orders=orders,wait_cash=waiting,reserved_buy_cash=str(reserved),buy_allocation_factor=str(factor),
        action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',
        reference_valid_until=min(deadlines).isoformat() if deadlines else None,
        research_only=True,execution_blocked=True,real_account=False,source_authenticated=False,
        source_bytes_verified=False,unit_continuity_verified='DECLARATION_CONSISTENCY_ONLY')

    if bounded_reviews:
        result['unit_review']=dict(bounded_reviews[0],limited_name_coverage=any(r['limited_name_coverage'] for r in bounded_reviews))
    return result
