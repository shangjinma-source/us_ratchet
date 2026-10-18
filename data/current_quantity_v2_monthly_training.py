"""Offline raw daily bars to existing 253-session / twelve-21-session method.

No network/search/ledger mutation. Membership, coordinate and calendar documents
are server-reviewed conditional evidence, not a claim of complete historical PIT.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp,number
from data.current_quantity_v2_difference_service import document,CurrentQuantityV2DifferenceService
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_paper_chain import review_chain
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.current_research_capital_decision_v2 import VERSION
from scripts.return_priority_current_rebased_training import prepare

BASIS='CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN'


def _checked(package):
    CurrentQuantityV2DifferenceService._package_identity(package)
    for p in package['source_hashes']:CurrentQuantityV2CurrentCashSources._path(p)
    return package['files'],package['source_hashes']


def _daily(raw,ticker):
    parsed=parse_provider_ohlc(raw,ticker)
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    rows=json.loads(decoded,parse_float=Decimal)['chart']['result'][0]['indicators']['quote'][0]
    closes={day:None if rows['close'][i] is None else str(Fraction(rows['close'][i])) for i,day in enumerate(parsed['dates'])}
    return parsed,closes


def compile_saved_training(source_package,manifest_path):
    """Re-extract raw values; supplied raw_close/training_close/gross never trusted."""
    files,pins=_checked(source_package);require(manifest_path in files,'TRAINING_MANIFEST_MISSING')
    manifest=deepcopy(document(files[manifest_path]))
    require(all(pins.get(p)==h for p,h in manifest['source_hashes'].items()),'MANIFEST_SOURCE_CHANGED')
    # Full declared member list stays intact, including admitted short-history exclusions.
    manifest['source_hashes']=deepcopy(pins);days=manifest['training_dates'];decision=manifest['decision_date']
    rows=manifest['candidates'];report=[];raw_sources={};raw_marks={}
    for row in rows:
        path=row['training_source'];require(path in files,'RAW_TRAINING_SOURCE_MISSING')
        channel,closes=_daily(files[path],row['ticker'])
        values=[closes.get(day) for day in days]
        row['raw_close']=values
        for field in ('training_close','training_gross'):row.pop(field,None)
        valid=[day for day in days if closes.get(day) is not None]
        missing=[day for day in days if closes.get(day) is None]
        if row['status']=='EXCLUDED_TRAINING_RULE':
            evidence=manifest['admission'].get('training_exclusions',{}).get(row['ticker'],{})
            # Merely missing scattered bars is never an automatic short-history exclusion.
            require(evidence.get('reason')=='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY'
                and evidence.get('source_references') and all(p in pins for p in evidence['source_references'])
                and evidence.get('known_asof','')<=decision and valid and len(valid)<253
                and channel['dates'][0]>days[0] and all(day<channel['dates'][0] for day in missing), 'UNSUPPORTED_SHORT_HISTORY_EXCLUSION')
        else:
            require(row.get('identity_reviewed') is True and row.get('coordinate_reviewed') is True,'TRAINING_IDENTITY_COORDINATE_UNREVIEWED')
            require(not missing,'MISSING_PREDECISION_RAW_CLOSE')
            sid=row['security_id'];raw_sources[sid]=dict(path=path,price_basis=BASIS)
            raw_marks[sid]=closes[decision]
        report.append(dict(ticker=row['ticker'],security_id=row.get('security_id'),status=row['status'],observed_training_sessions=len(valid),missing_sessions=missing,exclusion=deepcopy(manifest['admission'].get('training_exclusions',{}).get(row['ticker']))))
    compiled=prepare(manifest)
    require(compiled['status']=='READY_CONDITIONAL','TRAINING_COMPILATION_BLOCKED')
    args=deepcopy(compiled['search_arguments'])
    require(all(number(args['prices'][s])==number(raw_marks[s]) for s in args['prices']),'DECISION_COST_NOT_RAW_COORDINATE')
    args.update(quote_as_of=decision,price_basis=BASIS)
    quotes=[dict(security_id=s,as_of=decision,price=args['prices'][s],price_basis=BASIS,source_references=[raw_sources[s]['path']]) for s in sorted(args['prices'])]
    return dict(schema='RAW_MONTHLY_TRAINING_COMPILATION_V1',status='READY_CONDITIONAL',input=dict(search_arguments=args,valuation_quotes=quotes,bar_sources=raw_sources),
        compiled=compiled,coverage=report,source_hashes=deepcopy(pins),source_bytes_verified=True,source_authenticated=False,
        full_pit_verified=False,calendar_completeness_verified=False,search_calls=0,book_calls=0,
        limitations=['Dated declared membership and coordinate reviews are inputs, not independently authenticated complete PIT.',
                    'Twelve nonoverlapping 21-session price-only gross scenarios; no optimization or forward return calculation.'])


def build_monthly_training_package(state,source_package,*,manifest_path,calendar_path,account_review_path,identities_path,held_bar_sources,now):
    """Wrap compiled scenarios for the existing monthly registry, without executing it."""
    state=review_chain(state);ledger=state['ledger'];now=stamp(now);files,pins=_checked(source_package)
    compiled=compile_saved_training(source_package,manifest_path);data=deepcopy(compiled['input'])
    calendar=document(files[calendar_path]);review=document(files[account_review_path]);identities=document(files[identities_path]);day=data['search_arguments']['decision_date']
    require(calendar['decision_date']==day and calendar['source_references'] and all(p in pins for p in calendar['source_references']),'COMPILER_CALENDAR_BINDING')
    require(calendar.get('training_dates')==document(files[manifest_path])['training_dates'],'COMPILER_CALENDAR_TRAINING_BINDING')
    derived=review.get('schema')=='QUANTITY_V2_DERIVED_PAPER_REVIEW_V1'
    if derived:
        validate_derived_training_review(state,source_package,review,calendar,identities,data,held_bar_sources,now)
    require(review['account_id']==ledger['account_id'] and review['state_revision']==ledger['revision'] and review['pending_rights']==[]
        and max(stamp(calendar['decision_close_at']),stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))<=stamp(review['reviewed_at'])<=now
        and (derived or review['source_references']) and all(p in pins for p in review['source_references']),'COMPILER_ACCOUNT_REVIEW_BINDING')
    needed={s for s,q in ledger['shares'].items() if q}-set(data['search_arguments']['prices'])
    require(set(held_bar_sources)==needed,'COMPILER_HELD_VALUATION_DOMAIN')
    for sid in sorted(needed):
        path=held_bar_sources[sid];security=identities['securities'][sid]
        channel,closes=_daily(files[path],security['ticker']);require(closes.get(day) is not None,'MISSING_HELD_DECISION_CLOSE')
        data['valuation_quotes'].append(dict(security_id=sid,as_of=day,price=closes[day],price_basis=BASIS,source_references=[path]))
        data['bar_sources'][sid]=dict(path=path,price_basis=BASIS)
    require(set(data['bar_sources'])<=set(identities['securities']),'COMPILER_IDENTITIES_INCOMPLETE')
    # Capital adapter replaces entered_cash with actual equity. Do not preserve the
    # old compiler's historical example 20,000 as an account balance declaration.
    marks={q['security_id']:number(q['price']) for q in data['valuation_quotes']}
    data['search_arguments']['entered_cash']=str(number(ledger['cash'])+sum((q*marks[s] for s,q in ledger['shares'].items() if q),Fraction(0)))
    tag=sha256(canonical(dict(manifest=pins[manifest_path],calendar=pins[calendar_path],account_review=pins[account_review_path],state=state))).hexdigest()
    output_files=deepcopy(files);output_pins=deepcopy(pins);prefix='monthly-training/'+tag+'/'
    def put(name,value):
        path=prefix+name+'.json';require(path not in output_files,'GENERATED_SOURCE_COLLISION');raw=canonical(value);output_files[path]=raw;output_pins[path]=sha256(raw).hexdigest();return path
    training_path=put('input',data);report_path=put('compilation',compiled)
    admission=dict(status='ADMITTED_MONTHLY_FULL_ACCOUNT_V2',method=VERSION,account_id=ledger['account_id'],state_revision=ledger['revision'],target_month=calendar['target_month'],input_path=training_path,input_sha256=output_pins[training_path],
        complete_candidate_domain=True,mature_training_reviewed=True,pending_rights=[],reviewed_at=review['reviewed_at'],source_references=[manifest_path,calendar_path,account_review_path,report_path],
        scope='COMPILED_DECLARED_DOMAIN_CONDITIONAL_NOT_COMPLETE_PIT',full_pit_verified=False)
    if derived:
        admission.update(account_review_policy=review['policy'],account_review_schema=review['schema'],
            holding_unit_bridge='BOUNDED_KNOWN_ACTIONS_FROM_ACCEPTED_QUOTE_TO_DECISION_CLOSE',
            coverage_complete=False,source_authenticated=False)
    admission_path=put('admission',admission)
    return dict(files=output_files,source_hashes=output_pins,documents=dict(training=training_path,admission=admission_path,calendar=calendar_path,identities=identities_path))


def validate_derived_training_review(state,package,review,calendar,identities,data,held_bar_sources,now):
    """Conditional unchanged-unit bridge, never a complete action certificate."""
    from data.current_quantity_v2_paper_review import validate_paper_review,_screen,_thaw
    from data.current_quantity_v2_paper_chain import validate_derived_review_sources
    from data.current_quantity_v2_monthly_retarget import active_proposal
    from data.current_quantity_v2_monthly_bounded_review import _json
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    validate_paper_review(review,state,now)
    validate_derived_review_sources(review,package['source_hashes'])
    ledger=state['ledger'];old=active_proposal(ledger);oldinputs=old['causal_inputs']
    oldidentities=old.get('securities',oldinputs.get('securities',{}))
    request=review['derived_evidence']['request'];start=stamp(request['window_start'])
    require(max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))<=stamp(calendar['decision_close_at']),'VALUATION_PRECEDES_LEDGER')
    for sid,q in ledger['shares'].items():
        if not q:continue
        security=identities['securities'][sid];priorsecurity=oldidentities[sid]
        require(all(security.get(k)==priorsecurity.get(k) for k in ('ticker','issuer_id','security_class')),'TRAINING_HELD_IDENTITY_CHANGED')
        if old.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION':
            prior=next(r for r in old['rows'] if r['security_id']==sid);basis='PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE'
        else:
            prior=oldinputs['execution_references'][sid];basis=prior['price_basis']
        require(basis in ('PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE','CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS')
            and stamp(prior['captured_at'])<=stamp(calendar['decision_close_at']),'TRAINING_HELD_UNIT_ORIGIN_REQUIRED')
        bridge_start=min(start,stamp(prior['captured_at']))
        bridge_request=deepcopy(request);bridge_request['window_start']=bridge_start.isoformat()
        _screen(bridge_request,_thaw(review['derived_evidence']['action_package']),now)
        path=data['bar_sources'][sid]['path'] if sid in data['bar_sources'] else held_bar_sources[sid]
        raw=package['files'][path];_daily(raw,security['ticker']);chart=_json(raw)['chart']['result'][0]
        # A later fresh feed cannot erase positive actions in the saved valuation raw.
        for family,events in chart.get('events',{}).items():
            require(family in ('splits','dividends') and type(events)is dict,'TRAINING_HELD_ACTION_UNKNOWN')
            for event in events.values():
                require(type(event.get('date'))is int,'TRAINING_HELD_ACTION_UNKNOWN')
                eventday=datetime.fromtimestamp(event['date'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
                require(eventday<bridge_start.astimezone(ZoneInfo('America/New_York')).date(),'TRAINING_HELD_ACTION_CANDIDATE')
