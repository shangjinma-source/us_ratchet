"""New-cash current-quote dollar allocation; pure, not an accepted ledger plan.

Historical quantities set dollar envelopes only. Current class/unit declarations
are conditional reviewed inputs, not a historical no-action continuity proof.
"""
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
from hashlib import sha256
import json
import re
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_research_intraday_execution import decode_intraday_reference

SCOPE='NEW_CASH_CURRENT_QUOTE_ALLOCATION'
BASIS='PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE'
NY=ZoneInfo('America/New_York')


def require(ok,reason):
    if not ok:raise ValueError(reason)


def exact(v):
    require(type(v) in (str,int),'EXACT_NUMBER_REQUIRED')
    return Fraction(v)


def timestamp(v):
    require(type(v)is str,'ISO_TIME_REQUIRED')
    t=datetime.fromisoformat(v);require(t.tzinfo is not None,'AWARE_TIME_REQUIRED');return t


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def parse(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            require(k not in result,'DUPLICATE_DOCUMENT_KEY');result[k]=v
        return result
    def invalid(_):raise ValueError('NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid)


def closure(package, historical_pins=None):
    require(type(package)is dict and set(package)=={'files','source_hashes','documents'},'PACKAGE_FIELDS')
    files,pins=package['files'],package['source_hashes']
    require(type(files)is dict and type(pins)is dict and set(files)<=set(pins) and all(re.fullmatch('[a-f0-9]{64}',h) for h in pins.values())
            and 0<len(files)<=2000 and len(pins)<=2000,'COMPLETE_SOURCE_CLOSURE_REQUIRED')
    for path in pins:
        require(type(path)is str and path and '\\' not in path and ':' not in path
                and not PurePosixPath(path).is_absolute() and all(p not in ('','.','..') for p in path.split('/'))
                and str(PurePosixPath(path))==path,'SAFE_RELATIVE_PATH_REQUIRED')
    missing=set(pins)-set(files)
    require(not missing or (historical_pins is not None and all(historical_pins.get(p)==pins[p] for p in missing)),
            'COMPLETE_SOURCE_CLOSURE_REQUIRED')
    total=0
    for path,raw in files.items():
        require(type(path)is str and path and '\\' not in path and ':' not in path
                and not PurePosixPath(path).is_absolute() and all(p not in ('','.','..') for p in path.split('/'))
                and str(PurePosixPath(path))==path,'SAFE_RELATIVE_PATH_REQUIRED')
        require(type(raw)is bytes and len(raw)<=32*1024*1024,'SOURCE_BYTES_LIMIT')
        total+=len(raw);require(total<=128*1024*1024,'SOURCE_BYTES_LIMIT')
        require(sha256(raw).hexdigest()==pins[path],'SOURCE_HASH_MISMATCH')
    docs=package['documents']
    base_documents = {'identities','current_unit_reviews','quote_receipts'}
    require(type(docs)is dict and base_documents <= set(docs)
            and set(docs) <= base_documents | {'execution_month_mandate','pullback_policy','pullback_proofs'}
            and (('pullback_policy' in docs) == ('pullback_proofs' in docs)), 'DOCUMENT_FIELDS')
    return files,pins,docs


def _build_current_cash_plan(*,capital_decision,account_state,genesis_declaration,execution_package,now,recorded_historical_manifest=False):
    flags=dict(schema='V2_NEW_CASH_CURRENT_QUOTE_ALLOCATION_V1',target_scope=SCOPE,
        research_only=True,execution_blocked=True,orders_created=False,account_mutated=False,
        real_account=False,source_authenticated=False,corporate_actions_complete=False,
        ledger_acceptance_supported=False)
    try:
        # Validate the entire capital result, not a client display or rewritten decision.
        canonical(capital_decision);canonical(account_state);canonical(genesis_declaration)
        view=project_capital_decision_v2(capital_decision)
        require(view['status'] in ('AVAILABLE','ALL_CASH'),'COMPLETE_DECISION_REQUIRED')
        b=capital_decision['binding'];a=account_state;g=genesis_declaration
        current=timestamp(now);session=current.astimezone(NY).date().isoformat()
        require(date.fromisoformat(b['decision_date']).isoformat()==b['decision_date']<=session,'FUTURE_DECISION')
        require(set(a)=={'account_id','revision','cash','shares','observed_at','open_orders','reserved_cash','reserved_shares','pending_rights'},'EXPLICIT_ACCOUNT_FIELDS')
        require(type(a['account_id'])is str and a['account_id'].strip(),'ACCOUNT_ID_REQUIRED')
        require(b['shares']=={} and a['shares']=={} and capital_decision['holding_market_values']=={},'NEW_CASH_EMPTY_HOLDINGS_REQUIRED')
        require(a['open_orders']==[] and a['reserved_shares']=={} and exact(a['reserved_cash'])==0
                and a['pending_rights']==[],'NEW_CASH_UNENCUMBERED_REQUIRED')
        cash=exact(b['available_cash'])
        require(cash>0 and exact(a['cash'])==cash==exact(b['investable_equity'])
                and a['revision']==b['state_revision'],'INITIAL_CASH_BINDING_MISMATCH')
        require(set(g)=={'purpose','account_id','research_id','decision_id','capital_origin_revision',
                'initial_cash_exact','target_month','active_date','declared_at','source_references'},'GENESIS_FIELDS')
        require(g['purpose']=='PAPER_INITIALIZATION_NOT_BROKER_BALANCE'
                and g['account_id']==a['account_id'] and g['decision_id']==capital_decision['decision_id']
                and g['research_id']==capital_decision['research_id'] and g['capital_origin_revision']==a['revision']
                and exact(g['initial_cash_exact'])==cash and g['target_month']==session[:7]
                and g['active_date']==session,'GENESIS_BINDING_MISMATCH')
        observed=timestamp(a['observed_at']);genesis=timestamp(g['declared_at'])
        require(observed<=genesis<=current,'GENESIS_TIME_INVALID')
        files,pins,docs=closure(execution_package,b['source_hashes'] if recorded_historical_manifest else None)
        require(all(pins.get(p)==h for p,h in b['source_hashes'].items()),'ORIGINAL_SOURCE_MISMATCH')
        month_path=docs.get('execution_month_mandate')
        require(month_path is not None or recorded_historical_manifest,'MONTH_MANDATE_REQUIRED')
        if month_path is not None:
            from data.current_quantity_v2_execution_month import validate_execution_month
            require(month_path in files,'MONTH_MANDATE_BYTES_REQUIRED')
            validate_execution_month(parse(files[month_path]),decision_date=b['decision_date'],
                original_pins=b['source_hashes'],session=session,files=files,pins=pins)
        require(type(g['source_references'])is list and g['source_references']
                and all(p in files for p in g['source_references']),'GENESIS_SOURCE_REQUIRED')
        identities=parse(files[docs['identities']]);reviews=parse(files[docs['current_unit_reviews']])
        targets=capital_decision['target_quantities'];needed={sid for sid,q in targets.items() if q>0}
        pullback_policy = None
        if 'pullback_policy' in docs or 'pullback_proofs' in docs:
            require('pullback_policy' in docs and 'pullback_proofs' in docs,
                    'COMPLETE_PULLBACK_POLICY_REQUIRED')
            pullback_policy = parse(files[docs['pullback_policy']])
            require(set(pullback_policy) == {'schema','status','rebound_fraction',
                    'minimum_discount','maximum_age_seconds'}
                    and pullback_policy['schema'] == 'V2_PULLBACK_EXECUTION_POLICY_V1'
                    and pullback_policy['status'] == 'EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED'
                    and type(docs['pullback_proofs']) is dict
                    and set(docs['pullback_proofs']) == needed, 'INVALID_PULLBACK_POLICY')
        require(type(docs['quote_receipts'])is dict and set(docs['quote_receipts'])==set(identities)==set(reviews)==needed,'COMPLETE_SELECTED_DOMAIN_REQUIRED')
        args=b['search_arguments'];allocations={sid:targets[sid]*exact(args['prices'][sid]) for sid in needed}
        allocated=sum(allocations.values(),Fraction());original_residual=cash-allocated
        require(original_residual>=0 and exact(args['fee_bps'])==0,'ZERO_COMMISSION_CASH_BUDGET_REQUIRED')
        orders=[];rows=[];deadlines=[];used=Fraction()
        for sid in sorted(needed):
            identity=identities[sid];review=reviews[sid];meta=args['metadata'][sid]
            require(identity['security_id']==sid and identity['ticker']==meta['ticker']
                    and identity['issuer_id']==meta['issuer_id'] and identity['currency']=='USD'
                    and type(identity['security_class'])is str and identity['security_class'].strip()
                    and identity['source_references'] and all(p in files for p in identity['source_references']),
                    'CURRENT_IDENTITY_REQUIRED')
            path=docs['quote_receipts'][sid];receipt=parse(files[path]);rawpath=receipt['raw_path'];raw=files[rawpath]
            require(receipt['security_id']==sid and receipt['ticker']==identity['ticker']
                    and receipt['raw_sha256']==pins[rawpath],'RAW_RECEIPT_BINDING_MISMATCH')
            captured=timestamp(receipt['captured_at']);require(genesis<=captured<=current,'CAPTURE_TIME_INVALID')
            chart=parse(raw)['chart']['result'][0]
            require(chart['meta'].get('instrumentType')=='EQUITY','EQUITY_QUOTE_REQUIRED')
            require(not any(chart.get('events',{}).values()),'KNOWN_QUOTE_ACTION_UNSUPPORTED')
            ref=decode_intraday_reference(raw,ticker=identity['ticker'],now=current,captured_at=captured)
            require(timestamp(ref['last_at'])<=captured,'QUOTE_AFTER_CAPTURE')
            require(current<timestamp(ref['refresh_by']),'REFERENCE_EXPIRED')
            refpins={path:pins[path],rawpath:pins[rawpath]}
            require(review['status']=='CONDITIONAL_CURRENT_QUOTE_IDENTITY'
                    and review['security_id']==sid and review['ticker']==identity['ticker']
                    and review['issuer_id']==identity['issuer_id'] and review['security_class']==identity['security_class']
                    and review['currency']=='USD' and review['price_basis']==BASIS
                    and review['session']==session and review['reference_source_hashes']==refpins
                    and review['known_actions']==[] and review['source_references']
                    and all(p in files for p in review['source_references']),'CURRENT_UNIT_REVIEW_REQUIRED')
            require(timestamp(review['quote_captured_at'])==captured
                    and captured<=timestamp(review['reviewed_at'])<=current,
                    'CURRENT_UNIT_REVIEW_TIME_INVALID')
            limit=Fraction(min(exact(ref['last_price']),exact(ref['minute_low']))*100//1,100)
            if pullback_policy is not None:
                from data.current_quantity_v2_pullback_proof import replay_frozen_pullback
                proof = parse(files[docs['pullback_proofs'][sid]])
                replay = replay_frozen_pullback(raw, proof, now)
                candidate = replay['candidate']; parameters = proof['parameters']
                require(parameters['security_id'] == sid and parameters['ticker'] == identity['ticker']
                        and parameters['session'] == session
                        and timestamp(parameters['captured_at']) == captured
                        and parameters['expected_sha256'] == pins[rawpath]
                        and timestamp(parameters['session_open']) == timestamp(ref['session_open'])
                        and timestamp(parameters['session_close']) == timestamp(ref['session_close']),
                        'PULLBACK_REFERENCE_BINDING_MISMATCH')
                require(all(parameters[key] == pullback_policy[key] for key in
                        ('rebound_fraction','minimum_discount','maximum_age_seconds')),
                        'PULLBACK_POLICY_BINDING_MISMATCH')
                limit = exact(candidate['limit_price'])
                ref['pullback'] = dict(deepcopy(candidate), prior_cap=deepcopy(proof['prior_cap']),
                    status=pullback_policy['status'], cap_record_hash=proof['record_hash'])
                ref['refresh_by'] = min(timestamp(ref['refresh_by']),
                    timestamp(candidate['reference_valid_until'])).isoformat()
            require(limit>0,'NONPOSITIVE_LIMIT')
            q=int(allocations[sid]//limit);notional=q*limit;used+=notional
            if q:orders.append(dict(security_id=sid,ticker=identity['ticker'],side='BUY',quantity=q,limit_price=str(limit)))
            rows.append(dict(security_id=sid,ticker=identity['ticker'],historical_reference_quantity=targets[sid],
                frozen_dollar_allocation=str(allocations[sid]),current_quantity=q,limit_price=str(limit),
                notional=str(notional),allocation_residual=str(allocations[sid]-notional),reference=ref,
                captured_at=receipt['captured_at'],source_hashes=refpins))
            deadlines.append(ref['refresh_by'])
        require(used<=allocated<=cash,'BUDGET_CONSERVATION_FAILED')
        binding=dict(scope=SCOPE,capital_decision=deepcopy(capital_decision),account_state=deepcopy(a),
            genesis_declaration=deepcopy(g),source_hashes=deepcopy(pins),documents=deepcopy(docs),
            current_identities=identities,current_unit_reviews=reviews,rows=rows,created_at=now)
        identifier=sha256(canonical(binding)).hexdigest()
        return dict(flags,status='READY',execution_target_id=identifier,pinned_inputs=binding,
            capital_decision_id=capital_decision['decision_id'],research_id=capital_decision['research_id'],
            account_id=a['account_id'],origin_revision=a['revision'],session=session,orders=orders,rows=rows,
            execution_target_quantities={r['security_id']:r['current_quantity'] for r in rows},
            initial_cash=str(cash),original_residual_cash=str(original_residual),
            frozen_allocation_total=str(allocated),indicative_notional=str(used),remaining_cash=str(cash-used),
            reference_valid_until=min(deadlines) if deadlines else None,action='ORDERS' if orders else 'KEEP_CASH',
            source_bytes_verified=not recorded_historical_manifest,
            current_execution_bytes_verified=True,historical_source_bytes_reverified=not recorded_historical_manifest,fee_scope='COMMISSION_ZERO_OTHER_FEES_UNKNOWN_NOT_RESERVED',
            policy=('PER_SECURITY_DOLLAR_ENVELOPE_EXPERIMENTAL_PULLBACK_V1' if pullback_policy
                    else 'PER_SECURITY_DOLLAR_ENVELOPE_CURRENT_BUY_LOW_FLOOR_CENT_NO_REDISTRIBUTION'),
            limitations=['Current identity/unit evidence is conditional, not a certified absence of actions; no full-session action coverage is required or asserted.',
                'Historical training quantities are dollar weights only; no historical-unit continuity is asserted.',
                'Independent proposal only; existing ledger acceptance schemas do not accept this target.'])
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,ArithmeticError,OverflowError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),orders=[],execution_target_id=None,source_bytes_verified=False)


def build_current_cash_plan(*,capital_decision,account_state,genesis_declaration,execution_package,now):
    return _build_current_cash_plan(capital_decision=capital_decision,account_state=account_state,
        genesis_declaration=genesis_declaration,execution_package=execution_package,now=now)


def rebuild_current_cash_plan(plan, execution_package):
    """Replay needs the original externally saved byte package, never current prices."""
    b=plan['pinned_inputs']
    rebuilt=build_current_cash_plan(capital_decision=b['capital_decision'],account_state=b['account_state'],
        genesis_declaration=b['genesis_declaration'],execution_package=execution_package,now=b['created_at'])
    require(rebuilt==plan,'CURRENT_CASH_PLAN_RECONSTRUCTION_MISMATCH')
    return rebuilt
