"""Prepare dated-SID continuous input; unresolved action families stay null."""
import hashlib,json,sys
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.continuous_guided_account_decision import REQUIRED_PINS
from backtest.return_priority_monthly_execution_inputs import BASIS

def main():
    pins={};snapshots={}
    def read(path,expected=None):
        p=Path(path);p=p if p.is_absolute() else ROOT/p;key=p.relative_to(ROOT).as_posix()
        if key not in snapshots:snapshots[key]=p.read_bytes()
        b=snapshots[key];h=hashlib.sha256(b).hexdigest()
        if expected and h!=expected:raise ValueError('SOURCE_CHANGED:'+key)
        if key in pins and pins[key]!=h:raise ValueError('PIN_CONFLICT:'+key)
        pins[key]=h;return b
    def doc(path):
        d=json.loads(read(path))
        for name,h in d.get('source_hashes',{}).items():read(name,h)
        return d
    training_path='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json'
    execution_path='tmp/old_window_execution_prices_20261026/execution_prices_v1.json'
    training=doc(training_path);execution=doc(execution_path)
    if training['execution_prices_sha256']!=pins[execution_path]:raise ValueError('TRAINING_QUOTE_BINDING_MISMATCH')
    if training['pure_compiled_windows']!=31:raise ValueError('EXPECTED_31_WINDOWS')
    prior_path='tmp/next12_execution_prepare_20261014_v3/prepared.json'
    prior=doc(prior_path)
    binding_path='tmp/next12_distribution_execution_binding_20261015_v1/binding.json'
    binding=doc(binding_path)
    bridge_path='tmp/midwindow_identity_bridge_20261026/review.json';doc(bridge_path)
    lifecycle_path='tmp/old_holdings_lifecycle_gate_20261026/review.json';doc(lifecycle_path)
    wba_path='tmp/wba_terminal_official_20261026/review.json';doc(wba_path)
    official_split_path='tmp/qqq_20201231_anchor_20261025/official_split_semantics_batch1.json';official_splits=doc(official_split_path)
    sessions=execution['session_dates'];metadata={};ids={}
    for w in training['windows']:
        for sid,meta in w['compiled_search_arguments']['metadata'].items():
            if sid in metadata and metadata[sid]!=meta:raise ValueError('METADATA_COLLISION:'+sid)
            metadata[sid]=deepcopy(meta);ids.setdefault(meta['ticker'],set()).add(sid)
    transitions=[]
    for ticker,day,old,new,ratio,reference in (
        ('SMCI','2024-10-01','security:0001375365:86800U104','security:0001375365:86800U302','10',bridge_path),
        ('LRCX','2024-10-03','security:0000707549:512807108','security:0000707549:512807306','10','tmp/fixed12_training_prepare_20261014_v6/prepared.json'),
        ('HON','2026-06-29','security:0000773840:438516106','security:0000773840:438516205','1/2',binding_path)):
        if ids[ticker]!={old,new}:raise ValueError('UNEXPECTED_DATED_IDENTITY_DOMAIN:'+ticker)
        transitions.append(dict(ticker=ticker,date=day,old_sid=old,new_sid=new,share_ratio=ratio,
            source_references=[reference],identity_quote_binding_only=True,economic_conversion_execution_authorized=False,
            coupled_distribution=(ticker=='HON')))
    azn=next(e for e in prior['supported_conversions'] if e['event_id']=='AZN_ADS_ORDINARY_20260202')
    azn_new=azn['new_security_id'];metadata[azn_new]=deepcopy(prior['metadata'][azn_new]);ids['AZN'].add(azn_new)
    transitions.append(dict(ticker='AZN',date=azn['date'],old_sid=azn['security_id'],new_sid=azn_new,
        share_ratio='1/2',source_references=[prior_path]+azn['source_references'],identity_quote_binding_only=True,
        economic_conversion_execution_authorized=False,conditional_account_model=prior['account_model']))
    bounds={sid:dict(first=sessions[0],last=sessions[-1]) for sid in metadata}
    for e in transitions:
        if e['date'] not in sessions:raise ValueError('NONSESSION_IDENTITY_TRANSITION')
        bounds[e['old_sid']]['last']=sessions[sessions.index(e['date'])-1]
        bounds[e['new_sid']]['first']=e['date']
    # Old SIRI equity cannot silently inherit successor-company quotes.
    siri_old=next(iter(ids['SIRI']));bounds[siri_old]['last']='2024-09-09'
    identity_blockers=[dict(ticker='SIRI',date='2024-09-10',old_sid=siri_old,
        status='SUCCESSOR_IDENTITY_AND_ENTITLEMENT_MAPPING_REQUIRED_ON_EXPOSURE',source_references=[lifecycle_path])]
    if any(len(sids)>1 and ticker not in ('SMCI','LRCX','HON','AZN') for ticker,sids in ids.items()):raise ValueError('UNREVIEWED_IDENTITY_ALIAS')
    ohlc={};provenance={}
    for sid,meta in metadata.items():
        ticker=meta['ticker']
        if ticker not in execution['ohlc_candidates_by_ticker']:
            # AZN successor keeps the same ticker, but remains a separate SID.
            if sid==azn_new:ticker='AZN'
            else:raise ValueError('MISSING_TICKER_QUOTE_DOMAIN:'+sid)
        allowed=bounds[sid]
        ohlc[sid]={d:deepcopy(bar) for d,bar in execution['ohlc_candidates_by_ticker'][ticker].items() if allowed['first']<=d<=allowed['last']}
        dated=execution['source_routes'][ticker]['source_by_date'];segments=[]
        for day in sorted(ohlc[sid]):
            source=dated[day]
            if source not in pins:raise ValueError('UNPINNED_QUOTE_SEGMENT:'+source)
            if segments and segments[-1]['source_path']==source:segments[-1]['end']=day
            else:segments.append(dict(start=day,end=day,source_path=source))
        if not segments:raise ValueError('EMPTY_DATED_SECURITY_QUOTE_DOMAIN:'+sid)
        provenance[sid]=dict(price_basis=BASIS,segments=segments,whole_source_claim=False,
            identity_quote_interval=allowed,source_route_reference=execution_path,execution_authorized=False)
    windows=[];monthly=[];decision_count=0
    for w in training['windows']:
        day=w['decision_date'];args=deepcopy(w['compiled_search_arguments']);active=sessions[sessions.index(day)+1]
        for sid,price in args['prices'].items():
            if args['metadata'][sid]!=metadata[sid]:raise ValueError('WINDOW_IDENTITY_MISMATCH:'+sid)
            if Fraction(ohlc[sid][day]['close'])!=Fraction(price):raise ValueError('WINDOW_PRICE_MISMATCH:'+sid)
            decision_count+=1
        windows.append(dict(decision_date=day,active_date=active,search_arguments=args))
        quotes=[]
        for sid,bars in ohlc.items():
            if day not in bars:continue
            refs=[s['source_path'] for s in provenance[sid]['segments'] if s['start']<=day<=s['end']]
            if len(refs)!=1:raise ValueError('INVALID_DATED_SOURCE_SEGMENT')
            quotes.append(dict(security_id=sid,ticker=metadata[sid]['ticker'],price=bars[day]['close'],as_of=day,price_basis=BASIS,source_references=refs))
        monthly_args=deepcopy(args);monthly_args.update(quote_as_of=day,price_basis=BASIS)
        monthly.append(dict(decision_date=day,active_date=active,search_arguments=monthly_args,valuation_quotes=quotes,
            source_hashes=pins,missing_historical_marks=[],
            actual_held_price_policy='MISSING_HELD_MARK_MUST_BLOCK_NO_ZERO_NO_REMOVAL'))
    for filename in ('scripts/prepare_old_continuous_execution_schema.py','backtest/return_priority_fresh_cash_quantity_search.py',
        'backtest/return_priority_monthly_execution_inputs.py','backtest/return_priority_monthly_execution_inputs_v4.py',
        'backtest/historical_dividend_frontier_research.py','backtest/historical_dividend_next_open_book_research.py',
        'backtest/capped_frontier_rerank_research.py','scripts/audit_capped_training_frontier.py',*REQUIRED_PINS):read(filename)
    event_inventory=[];missing_action_sources=[]
    for ticker,route in execution['source_routes'].items():
        for source,events in route['provider_actions_by_source'].items():
            for event in events:
                if sessions[0]<event['date']<=sessions[-1]:event_inventory.append(dict(ticker=ticker,source=source,**event,
                    source_selected_for_date=route['source_by_date'].get(event['date'])==source,mapping_status='REQUIRES_EXPOSURE_SCOPED_ECONOMIC_MAPPING'))
        for source in route['source_action_stream_absent']:missing_action_sources.append(dict(ticker=ticker,source=source))
    mapped_split_candidates=deepcopy(prior['split_events_reference_only'])
    for record in official_splits['records']:
        if not sessions[0]<record['ex_date']<=sessions[-1]:continue
        for sid in ids.get(record['ticker'],[]):
            if bounds[sid]['first']<=record['ex_date']<=bounds[sid]['last']:
                mapped_split_candidates.append(dict(date=record['ex_date'],security_id=sid,new_shares=record['new_shares'],old_shares=record['old_shares'],source_references=[official_split_path]))
    prepared=dict(session_dates=sessions,source_hashes=pins,metadata=metadata,source_provenance=provenance,ohlc=ohlc,windows=windows,
        split_events_reference_only=mapped_split_candidates,identity_migrations=None,
        cash_stock_merger_events=None,fractional_settlements=None,distribution_events=None,
        distribution_fractional_cash_values=None,supported_conversions=None,unsupported_conversions=None)
    blockers=[dict(kind='ACTION_FAMILIES_NOT_ASSEMBLED',fields=[k for k,v in prepared.items() if v is None],
        resolution='Populate only from reviewed, actually exposed events before invoking the existing v4 assembler; null never means no actions.'),
        dict(kind='DIVIDEND_PAYMENT_AND_WITHHOLDING_MODEL_NOT_BOUND',event_count=sum(e['kind']=='dividends' for e in event_inventory)),
        dict(kind='COMPLEX_TERMINATION_ENTITLEMENTS_REQUIRE_EXPOSURE_GATE',tickers=['SPLK','ANSS','WBA']),
        dict(kind='MISSING_ACTION_STREAM_REQUIRES_SCOPED_REVIEW',source_count=len(missing_action_sources))]+identity_blockers
    for name,content in snapshots.items():
        if (ROOT/name).read_bytes()!=content:raise ValueError('INPUT_CHANGED_DURING_PREPARATION:'+name)
    result=dict(status='QUOTE_AND_MONTHLY_SCHEMA_PRECHECK_PASSED_ECONOMIC_ACTION_ASSEMBLY_BLOCKED',
        prepared_input_candidate=prepared,monthly_input_candidates=monthly,ohlc=ohlc,dated_identity_transitions=transitions,
        provider_event_inventory=event_inventory,action_stream_missing=missing_action_sources,
        reusable_reviewed_action_candidates=dict(ordinary_splits=mapped_split_candidates,azn_conversion=azn,
            prior_distribution_events=prior['distribution_events'],prior_distribution_binding=binding),
        source_hashes=pins,training_sha256=pins[training_path],execution_prices_sha256=pins[execution_path],
        schema_checks=dict(months=len(windows),sessions=len(sessions),security_ids=len(metadata),exact_candidate_prices=decision_count,
            dated_identity_slices=True,exact_segment_pins=True,unmapped_actions_are_null_not_empty=True),
        execution_blockers=blockers,runner_execution_authorized=False,dividend_events=None,
        assembly_call_attempted=False,assembly_entrypoint='backtest.return_priority_monthly_execution_inputs_v4.assemble_monthly_execution_inputs_v4',
        assembly_skip_reason='Required action families remain explicitly unknown; running the assembler would misrepresent incomplete inputs.',
        search_calls=0,economic_run_completed=False,
        limitations=['This is an actual reusable input precheck, not a completed economic execution assembly.',
            'SMCI/LRCX/HON/AZN quote identity intervals do not themselves execute share conversions or distributed rights.',
            'Old holdings after index exit remain in the quote domain; successor-identity uncertainty blocks rather than zeroing holdings.'])
    target=ROOT/'tmp/old_window_execution_prices_20261026/continuous_schema_precheck_v1.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],**result['schema_checks'],sha256=hashlib.sha256(target.read_bytes()).hexdigest())))

if __name__=='__main__':main()
