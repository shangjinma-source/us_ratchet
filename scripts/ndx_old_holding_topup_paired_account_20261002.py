"""Frozen old-holding top-ups versus same-flow zero-trade conditional price-only paths."""
import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/old_holding_topup_paired_account_20261002_v1'
SCHEMA = 'OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1'
PINS = {
 'inputs': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json','1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
 'input_publication': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json','54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
 'topups': ('data/cache/research/old_holding_topup_research_20261002_v1/results.json','1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb'),
 'topup_publication': ('data/cache/research/old_holding_topup_research_20261002_v1/publication.json','ed4f230d5e74ac0fb2000149caab80825e48d36cf3d7cd98a5f0858abc0fbc16'),
 'control': ('data/cache/research/incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json','53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'),
 'RETURN_price': ('data/cache/research/return_eight_price_only_20260923_v1/raw_assembly.json','e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336'),
 'BAD_TAIL_price': ('data/cache/research/bad_tail_five_input_projection_20260923_v1/projection.json','77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'),
 'DRAWDOWN_price': ('data/cache/research/drawdown_four_input_assembly_20260923_v1/assembly.json','cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'),
 'LEGACY_TARGET_DISTANCE_price': ('data/cache/research/legacy_twelve_price_only_20260923_v1/prices.json','a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342'),
 'kernel': ('backtest/ndx_cash_flow_return_accounting_research.py','ba4924f8f34ded1163d1b746faed236e968306004f2f15b559642cd4275f9417')}
PRICE_SCHEMAS = {
 'RETURN': 'RETURN_EIGHT_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1',
 'BAD_TAIL': 'BAD_TAIL_FIVE_SECURITY_107_SESSION_INPUT_PROJECTION_V1',
 'DRAWDOWN': 'DRAWDOWN_FOUR_SECURITY_107_SESSION_CONDITIONAL_INPUT_V1',
 'LEGACY_TARGET_DISTANCE': 'LEGACY_TWELVE_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1'}
FLAGS = dict.fromkeys(('old_experiments_reexecuted','selected_plans_reselected','dividends_modelled','fx_modelled',
 'corporate_actions_modelled','cash_interest_modelled','total_return_claimed','old_six_period_strategy_replayed',
 'formal_dual_benchmark_comparison','point_in_time_verified','promotion_allowed','orders_executed',
 'economic_winner_selected','identity_gaps_resolved','full_transitive_source_closure_reverified',
 'exchange_calendar_completeness_verified','real_user_cash_claimed'), False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def number(value):
    require(type(value) is str and 0 < len(value) <= 80 and value.strip() == value, 'Saved Decimal string required')
    parsed = Decimal(value)
    require(parsed.is_finite() and len(parsed.as_tuple().digits) <= 40 and abs(parsed.as_tuple().exponent) <= 40, 'Bounded finite decimal required')
    return Fraction(parsed)


def rational(value):
    return {'numerator': str(value.numerator), 'denominator': str(value.denominator)}


def from_ratio(value):
    require(type(value) is dict and set(value) == {'numerator','denominator'}
            and all(type(value[key]) is str for key in value), 'Exact saved ratio required')
    numerator, denominator = int(value['numerator']), int(value['denominator'])
    require(denominator > 0, 'Positive ratio denominator required')
    return Fraction(numerator, denominator)


def pointer(reference, value):
    return dict(reference, json_pointer=value)


def price_contract(documents):
    calendar = None; projected = {}; metadata = {}
    for lane,schema in PRICE_SCHEMAS.items():
        doc = documents[lane+'_price']; require(doc['schema'] == schema, 'Price schema differs')
        days = doc['calendar']
        require(type(days) is list and len(days) == 107 and days == sorted(set(days))
                and all(type(day) is str and date.fromisoformat(day).isoformat() == day for day in days)
                and days[0] == '2023-03-31' and days[1] == '2023-04-03' and days[-1] == '2023-09-01', '107 observed calendar required')
        require(calendar is None or calendar == days, 'Lane calendars differ')
        calendar = days
        for flag in ('corporate_action_completeness_verified','dividend_cash_flows_modelled','point_in_time_verified','promotion_allowed'):
            require(doc[flag] is False, 'Price source authority changed')
        projection = doc.get('price_projection',doc)
        require(set(projection['matrices']) == {'open','close'} and all(set(rows) == set(days) for rows in projection['matrices'].values()), 'Exact saved Open/Close calendar required')
        prefix = '/price_projection' if 'price_projection' in doc else ''
        projected[lane] = (projection,prefix)
        retained = deepcopy(doc)
        (retained['price_projection'] if 'price_projection' in retained else retained).pop('matrices')
        metadata[lane] = retained  # Entire original channels/events and flags; never split-adjust again.
    return calendar, projected, metadata


def maximum_drawdown(account):
    peak, worst = Fraction(1), Fraction(0)
    for row in account['rows']:
        value = 1 + from_ratio(row['cumulative_twr'])
        require(value > 0, 'Positive TWR wealth required')
        peak = max(peak,value); worst = max(worst,1-value/peak)
    return {'maximum_drawdown': rational(worst), 'wealth_definition': 'ONE_PLUS_CHAINED_TWR',
            'initial_wealth': rational(Fraction(1)), 'initial_observation_included': True,
            'observation_clock': 'INITIAL_CLOSE_THEN_EACH_SESSION_CLOSE_ONLY'}


CLOCKS = (('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),
          ('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))


def control_quotes(document):
    require(document['schema']=='ndx_incumbent_nominal_control_research_v1','Nominal control schema')
    for flag in ('point_in_time_verified','promotion_allowed','price_identity_binding_verified','dividends_modelled'):
        require(document[flag] is False,'Control source authority')
    indexed={}
    for ticker,channel in document['nominal_quotes']['by_ticker'].items():
        indexed[ticker]={}
        for index,row in enumerate(channel['rows']):
            require(row['ticker']==ticker and row['session'] not in indexed[ticker],'Unique control quote ticker/session required')
            indexed[ticker][row['session']]=(index,row)
    metadata=deepcopy(document)
    metadata.pop('execution')  # Saved old account is not consumed or replayed.
    for channel in metadata['nominal_quotes']['by_ticker'].values(): channel.pop('rows')
    return indexed,metadata


def quote(*, sid, ticker, day, field, projection, prefix, control_index, refs, lane):
    observations=[]
    if ticker in projection['tickers']:
        literal=projection['matrices'][field][day][ticker]
        require(number(literal)>0,'Positive lane quote required')
        observations.append({'decimal_literal':literal,'encoding':'SAVED_DECIMAL_STRING_NO_RECONSTRUCTION',
            'reference':pointer(refs[lane+'_price'],f'{prefix}/matrices/{field}/{day}/{ticker}')})
    if ticker in control_index:
        require(day in control_index[ticker],'Required control session missing')
        index,row=control_index[ticker][day]; value=row['nominal_'+field]
        require(type(value) is float and row['currency']=='USD','Saved USD float control quote required')
        literal=str(value); require(number(literal)>0,'Positive control quote required')
        observations.append({'decimal_literal':literal,'encoding':'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',
            'currency':'USD','reference':pointer(refs['control'],f'/nominal_quotes/by_ticker/{ticker}/rows/{index}/nominal_{field}')})
    require(observations,'No bound price for prepared SID/ticker')
    require(len({number(item['decimal_literal']) for item in observations})==1,'Lane/control intersecting quote conflict')
    return observations[0]['decimal_literal'],{'security_id':sid,'ticker':ticker,'chosen_observation_index':0,
        'priority':'LANE_SAVED_DECIMAL_THEN_INCUMBENT_SAVED_FLOAT_STR','observations':observations,
        'identity_scope':'FROZEN_PREPARED_SID_TICKER_ATTRIBUTION_NOT_NEW_IDENTITY_CERTIFICATION'}


def selected_plan(result,row):
    require(result['input_row']==row and result['scenario_id']==row['scenario_id'],'Frozen input row differs')
    index=result['selected_candidate_index']; branches=result['evaluation']['branches']
    require(len(branches)==1 and branches[0]['branch_id']==row['scenario_id'],'Selected branch differs')
    plans=branches[0]['evaluated_plans']
    require(type(index) is int and 0<=index<len(plans),'Selected candidate index invalid')
    plan=plans[index]
    require(type(plan['supplied_plan_index']) is int and plan['supplied_plan_index']==index and plan['feasible'] is True,'Selected saved candidate must be feasible')
    require(set(plan['buy_shares'])==set(row['securities'])==set(row['execution_prices']),'Complete buy domain including zeros required')
    require(all(type(q) is int and q>=0 for q in plan['buy_shares'].values()),'Whole nonnegative buys required')
    expected={sid:row['holdings'].get(sid,0)+count for sid,count in plan['buy_shares'].items()}
    require(set(row['holdings'])<=set(expected) and plan['proposed_holdings']==expected,'Full old and zero-key holdings differ')
    return index,plan


def calculate_pair(row,plan,calendar,projection,prefix,control_index,refs,account_path):
    decision,execution=row['cash_event']['decision_date'],row['cash_event']['execution_date']
    require((decision,execution) in [(d,e) for d,e,_ in CLOCKS]
            and calendar.index(execution)==calendar.index(decision)+1,'Adjacent saved decision/execution clock required')
    days=calendar[calendar.index(execution):]
    require(len(days)==next(n for d,e,n in CLOCKS if d==decision),'Saved remaining session count differs')
    require(number(row['transaction_cost_bps'])==10,'Frozen 10bps contract required')
    mapping={sid:item['ticker'] for sid,item in row['securities'].items()}
    require(len(set(mapping.values()))==len(mapping),'Cannot collapse distinct SID to one ticker')
    def marks(day,field,sids):
        prices,evidence={},{}
        for sid in sorted(sids):
            prices[sid],evidence[sid]=quote(sid=sid,ticker=mapping[sid],day=day,field=field,projection=projection,
                prefix=prefix,control_index=control_index,refs=refs,lane=row['lane'])
        return prices,evidence
    initial_prices,initial_evidence=marks(decision,'close',row['holdings'])
    initial={'session':decision,'cash_usd':row['starting_cash_usd'],'holdings':deepcopy(row['holdings']),'close_prices':initial_prices}
    candidate_sessions,control_sessions,quote_evidence=[],[],[]
    for index,day in enumerate(days):
        opens,open_evidence=marks(day,'open',plan['proposed_holdings'])
        closes,close_evidence=marks(day,'close',plan['proposed_holdings'])
        if index==0:
            require(all(number(opens[sid])==number(row['execution_prices'][sid]) for sid in opens),'First Open differs from saved plan input')
        flow=row['cash_event']['amount_usd'] if index==0 else '0'
        candidate_sessions.append({'session':day,'open_prices':opens,'close_prices':closes,'cash_injection_usd':flow,
            'buy_shares':deepcopy(plan['buy_shares']) if index==0 else {}})
        control_sessions.append({'session':day,'open_prices':{sid:opens[sid] for sid in row['holdings']},
            'close_prices':{sid:closes[sid] for sid in row['holdings']},'cash_injection_usd':flow,'buy_shares':{}})
        quote_evidence.append({'session':day,'open':open_evidence,'close':close_evidence})
    outputs={}
    for name,sessions in [('candidate',candidate_sessions),('same_flow_zero_trade_control',control_sessions)]:
        account=account_path(initial=deepcopy(initial),sessions=sessions,transaction_cost_bps=row['transaction_cost_bps'])
        require(account['schema']=='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1' and len(account['rows'])==len(days),'Account schema/count')
        is_candidate=name=='candidate'
        expected_holdings=plan['proposed_holdings'] if is_candidate else row['holdings']
        expected_cash=number(plan['cash_after_usd']) if is_candidate else number(row['starting_cash_usd'])+number(row['cash_event']['amount_usd'])
        for index,entry in enumerate(account['rows']):
            require(entry['session']==days[index] and entry['holdings_after']==expected_holdings
                    and number(entry['cash_after_usd'])==expected_cash,'Fixed cash/holdings differ')
            require(entry['buy_shares']==(plan['buy_shares'] if is_candidate and index==0 else {})
                    and number(entry['cash_injection_usd'])==(number(row['cash_event']['amount_usd']) if index==0 else 0),
                    'Unexpected trade/flow in path')
            require(number(entry['fees_usd'])==(number(plan['fees_usd']) if is_candidate and index==0 else 0),'Unexpected fee')
        if is_candidate:
            for field in ('gross_buy_usd','fees_usd','cash_after_usd'):
                require(number(account['rows'][0][field])==number(plan[field]),'First trade reconciliation differs')
        else:
            require(all(number(entry['gross_buy_usd'])==0 for entry in account['rows']),'Zero-trade control gross differs')
        require(number(account['total_cash_injection_usd'])==number(row['cash_event']['amount_usd'])
                and number(account['total_fees_usd'])==(number(plan['fees_usd']) if is_candidate else 0),'Aggregate flow/fee differs')
        for flag in ('dividends_modelled','corporate_actions_modelled','orders_executed','point_in_time_verified','promotion_allowed'):
            require(account[flag] is False,'Account authority changed')
        outputs[name]={'account':account,'drawdown':maximum_drawdown(account),
            'accounting_inputs':{'initial':deepcopy(initial),'sessions':sessions,'transaction_cost_bps':row['transaction_cost_bps']}}
    candidate=outputs['candidate']; control=outputs['same_flow_zero_trade_control']
    return {'paths':outputs,'security_to_ticker':mapping,'initial_close_quote_evidence':initial_evidence,
        'path_quote_evidence':quote_evidence,'observed_path_session_count':len(days),'post_execution_close_intervals':len(days)-1,
        'candidate_minus_control':{'chained_twr_difference':rational(from_ratio(candidate['account']['chained_twr'])-from_ratio(control['account']['chained_twr'])),
            'maximum_drawdown_difference':rational(from_ratio(candidate['drawdown']['maximum_drawdown'])-from_ratio(control['drawdown']['maximum_drawdown'])),
            'terminal_equity_usd_difference':rational(number(candidate['account']['terminal_equity_usd'])-number(control['account']['terminal_equity_usd']))},
        'first_candidate_trade_reconciled_to_saved_plan':True,'equal_horizons_across_decision_dates_claimed':False}


def assemble(documents,refs,account_path):
    inputs,topups=documents['inputs'],documents['topups']
    require(inputs['schema']=='REMAINING_STANDARD_CASH_INPUTS_V1' and len(inputs['rows'])==64
            and topups['schema']=='OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1' and len(topups['rows'])==40,'Parent schema/count')
    for doc in (inputs,topups):
        for flag in ('orders_executed','point_in_time_verified','promotion_allowed'):
            require(doc[flag] is False,'Parent authority changed')
    calendar,projections,metadata=price_contract(documents)
    control_index,control_metadata=control_quotes(documents['control'])
    expected={(lane,d,e,amount) for lane in PRICE_SCHEMAS for d,e,_ in CLOCKS for amount in ('1000','10000')}
    seen=set(); ids=set(); rows=[]
    for index,result in enumerate(topups['rows']):
        ref=result['input_reference']; raw_pointer=ref['json_pointer']
        require(raw_pointer.startswith('/rows/') and raw_pointer[6:].isdigit(),'Input pointer invalid')
        input_index=int(raw_pointer[6:])
        require(raw_pointer==f'/rows/{input_index}' and 0<=input_index<64
                and ref==pointer(refs['inputs'],raw_pointer),'Input reference mismatch')
        row=inputs['rows'][input_index]; event=row['cash_event']
        coord=(row['lane'],event['decision_date'],event['execution_date'],event['amount_usd'])
        require(row['branch_role']=='MAIN_LANE' and coord in expected and coord not in seen
                and row['scenario_id'] not in ids,'Exact unique 40-main coordinate required')
        seen.add(coord); ids.add(row['scenario_id'])
        plan_index,plan=selected_plan(result,row)
        projection,prefix=projections[row['lane']]
        pair=calculate_pair(row,plan,calendar,projection,prefix,control_index,refs,account_path)
        # Keep all source assumptions/gaps/domain limitations; omit only repeated numerical search results.
        context={key:deepcopy(value) for key,value in result.items() if key not in ('evaluation','closure_records','feasible_scores')}
        rows.append({'scenario_id':row['scenario_id'],'input_reference':deepcopy(ref),'input_row':deepcopy(row),
            'topup_context':context,'topup_context_reference':pointer(refs['topups'],f'/rows/{index}'),
            'selected_plan':deepcopy(plan),'selected_plan_reference':pointer(refs['topups'],
                f'/rows/{index}/evaluation/branches/0/evaluated_plans/{plan_index}'),**pair,**FLAGS})
    require(seen==expected,'Missing main scenario')
    return {'schema':SCHEMA,'rows':rows,'scenario_count':40,'new_account_path_count':80,
        'input_references':deepcopy(refs),'observed_calendar':calendar,'price_evidence_metadata':metadata,
        'incumbent_price_metadata_without_old_execution_or_quote_rows':control_metadata,
        'parent_source_hashes_preserved_not_reaudited':{role:deepcopy(doc.get('source_hashes',doc.get('historical_expected_source_hashes',{}))) for role,doc in documents.items()},
        'scope':'INDEPENDENT_SCENARIO_FIXED_HOLDINGS_PRICE_ONLY_CANDIDATE_VS_SAME_FLOW_ZERO_TRADE',
        'this_account_wrapper_selects_using_future_returns':False,'parent_selection_point_in_time_verified':False,
        'annualized_return_calculated':False,'time_series_return_evaluated':True,
        'continuous_forty_scenario_strategy_claimed':False,'nominal_prices_reconstructed':False,**FLAGS}


def write_new(path,value):
    raw=encode(value)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output bytes changed')
    return sha(raw)


def load_account_path(refs):
    name='backtest.ndx_cash_flow_return_accounting_research'
    require(name not in sys.modules,'Fresh CLI required; cached accounting module present')
    module=importlib.import_module(name)
    require(Path(module.__file__).resolve()==Path(refs['kernel']['path']).resolve(),'Accounting module path differs')
    return module.account_path


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry/overwrite')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source changed')
    require(all(type(pin) is str and len(pin)==64 for _,pin in PINS.values()),'Pending source pins')
    sources={str(SOURCE):LOADED_SHA}; documents={}; refs={}
    for role,(relative,pin) in PINS.items():
        path=ROOT/relative; raw=path.read_bytes(); require(sha(raw)==pin,'Source mismatch: '+role)
        sources[str(path)]=pin; refs[role]={'path':str(path),'sha256':pin}
        if role!='kernel': documents[role]=json.loads(raw)
    contracts=[('inputs','input_publication',{'inputs.json','publication.json'},'REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1','INPUTS_ONLY_NOT_EXECUTED','input_reference'),
        ('topups','topup_publication',{'started.json','results.json','publication.json'},'OLD_HOLDING_TOPUP_PUBLICATION_V1','PUBLISHED_CONDITIONAL_TOPUPS_ONLY','result_reference')]
    for role,publication,files,schema,status,refkey in contracts:
        require({p.name for p in Path(refs[role]['path']).parent.iterdir()}==files,'Parent namespace incomplete')
        receipt=documents[publication]
        require(receipt['schema']==schema and receipt['status']==status and receipt[refkey]==refs[role]
                and receipt['source_hashes']==documents[role]['source_hashes'],'Publication mismatch')
        for flag in ('orders_executed','point_in_time_verified','promotion_allowed','fork_executable'):
            require(receipt[flag] is False,'Publication authority')
    account_path=load_account_path(refs)
    def guard():
        for path,pin in sources.items(): require(sha(Path(path).read_bytes())==pin,'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'schema':'OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_STARTED_V1',
            'started_at_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':sources,'planned_scenario_count':40,'retry_allowed':False})
        result=assemble(documents,refs,account_path); result['source_hashes']=sources; guard()
        digest=write_new(OUTPUT/'accounts.json',result); guard()
        publication={'schema':'OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','status':'PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS',
            'account_reference':{'path':str(OUTPUT/'accounts.json'),'sha256':digest},'source_hashes':sources,**FLAGS}
        publication_sha=write_new(OUTPUT/'publication.json',publication); guard()
        require(sha((OUTPUT/'accounts.json').read_bytes())==digest and sha((OUTPUT/'publication.json').read_bytes())==publication_sha
                and {p.name for p in OUTPUT.iterdir()}=={'started.json','accounts.json','publication.json'},'Final publication differs')
        return {'path':str(OUTPUT/'accounts.json'),'sha256':digest,'publication_sha256':publication_sha,'scenario_count':40}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))


