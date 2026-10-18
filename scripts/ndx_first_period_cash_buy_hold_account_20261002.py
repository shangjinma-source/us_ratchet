"""Frozen first-eight selected buys held constant: conditional price-only TWR."""
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
OUTPUT = ROOT / 'data/cache/research/first_period_cash_buy_hold_account_20261002_v1'
SCHEMA = 'FIRST_PERIOD_CASH_FIXED_BUY_HOLD_PRICE_ONLY_TWR_V1'
PINS = {
 'inputs': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json','f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'),
 'input_publication': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/publication.json','304303cd9e53cb92723d4fd463f58934f3506339a2f8170ffef9cd9f258e6d47'),
 'repair_results': ('data/cache/research/first_period_cash_repair_research_20261002_v1/results.json','61b9e1e66c18b74fb503e1de57a292514e9467ec07215eaa7126055ae2b395b7'),
 'old_results': ('data/cache/research/first_period_cash_neighbor_research_20261002_v1/results.json','dfd434e79c5f9f1242a1a2d11d7cbe7bf9d830f6d5e3e380225a64ff31dcdbdf'),
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


def saved_selection(row, repaired, old, refs, index):
    require(row['scenario_id'] == repaired['scenario_id'] == old['scenario_id'], 'Scenario routing mismatch')
    require(repaired['input_reference'] == pointer(refs['inputs'],f'/rows/{index}')
            and repaired['previous_result_reference'] == pointer(refs['old_results'],f'/rows/{index}'), 'Repair lineage differs')
    chosen = repaired['selected']
    require(type(chosen) is dict and chosen['source'] in ('PREVIOUS_BATCH','NEW_REPAIR_BATCH'), 'Explicit selected batch required')
    role = 'old_results' if chosen['source'] == 'PREVIOUS_BATCH' else 'repair_results'
    owner = old if role == 'old_results' else repaired
    branches = owner['evaluation']['branches']
    require(len(branches) == 1 and branches[0]['branch_id'] == row['scenario_id'], 'Selected branch mismatch')
    plan_index = chosen['plan_index']; plans = branches[0]['evaluated_plans']
    require(type(plan_index) is int and 0 <= plan_index < len(plans), 'Selected index invalid')
    plan = plans[plan_index]
    require(type(plan['supplied_plan_index']) is int and plan['supplied_plan_index'] == plan_index
            and plan['feasible'] is True, 'Selected saved plan must be feasible')
    require(set(plan['buy_shares']) == set(row['target_weights']) == set(row['securities']) == set(row['execution_prices']), 'Full selected SID domain mismatch')
    require(all(type(q) is int and q >= 0 for q in plan['buy_shares'].values()), 'Whole additional buys required')
    require(plan['proposed_holdings'] == plan['buy_shares'], 'First-period empty baseline required')
    require(from_ratio(chosen['fee_usd']) == number(plan['fees_usd']), 'Selected saved fee mismatch')
    return plan, pointer(refs[role],f'/rows/{index}/evaluation/branches/0/evaluated_plans/{plan_index}')


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


def assemble(documents, refs, account_path):
    inputs, repair, old = (documents[key] for key in ('inputs','repair_results','old_results'))
    require(inputs['schema'] == 'FIRST_PERIOD_STANDARD_CASH_INPUTS_V1'
            and repair['schema'] == 'FIRST_PERIOD_CASH_REPAIR_RESEARCH_V1'
            and old['schema'] == 'FIRST_PERIOD_CASH_NEIGHBOR_RESEARCH_V1', 'Input result schema mismatch')
    require(len(inputs['rows']) == len(repair['rows']) == len(old['rows']) == 8, 'Eight aligned scenarios required')
    require(len({row['scenario_id'] for row in inputs['rows']}) == 8, 'Unique scenario IDs required')
    for doc in (inputs,repair,old):
        for flag in ('orders_executed','point_in_time_verified','promotion_allowed'):
            require(doc[flag] is False, 'Parent authority changed')
    calendar, projections, metadata = price_contract(documents)
    coordinates = [(row['lane'],row['cash_event']['amount_usd']) for row in inputs['rows']]
    require(len(set(coordinates)) == 8 and set(coordinates) == {(lane,amount) for lane in PRICE_SCHEMAS for amount in ('1000','10000')}, 'Exact four-lane two-amount denominator')
    rows = []
    for index,(row,repaired,previous) in enumerate(zip(inputs['rows'],repair['rows'],old['rows'])):
        require(row['holdings'] == {} and number(row['starting_cash_usd']) == 25000
                and number(row['transaction_cost_bps']) == 10
                and row['cash_event']['decision_date'] == calendar[0]
                and row['cash_event']['execution_date'] == calendar[1], 'Fixed initial capital/date/fee contract')
        plan, selected_ref = saved_selection(row,repaired,previous,refs,index)
        lane = row['lane']; price, prefix = projections[lane]; price_ref = refs[lane+'_price']
        mapping = {sid: row['securities'][sid]['ticker'] for sid in sorted(plan['buy_shares'])}
        require(all(type(ticker) is str and ticker in price['tickers'] for ticker in mapping.values())
                and len(set(mapping.values())) == len(mapping), 'Unique prepared SID/ticker mapping required')
        sessions, quote_evidence = [], []
        for day_index,day in enumerate(calendar[1:]):
            marks = {}; evidence = {}
            for field in ('open','close'):
                marks[field] = {}; evidence[field] = {}
                for sid,ticker in mapping.items():
                    literal = price['matrices'][field][day][ticker]
                    require(number(literal) > 0, 'Positive saved nominal mark required')
                    if day_index == 0 and field == 'open':
                        require(literal == row['execution_prices'][sid], 'First Open literal differs from selected input')
                    marks[field][sid] = literal
                    evidence[field][sid] = {'ticker': ticker, 'decimal_literal': literal,
                        'reference': pointer(price_ref,f'{prefix}/matrices/{field}/{day}/{ticker}')}
            sessions.append({'session':day,'open_prices':marks['open'],'close_prices':marks['close'],
                'cash_injection_usd':row['cash_event']['amount_usd'] if day_index == 0 else '0',
                'buy_shares':deepcopy(plan['buy_shares']) if day_index == 0 else {}})
            quote_evidence.append({'session':day,'quotes':evidence})
        account = account_path(initial={'session':calendar[0],'cash_usd':row['starting_cash_usd'],'holdings':{},'close_prices':{}},
            sessions=sessions, transaction_cost_bps=row['transaction_cost_bps'])
        require(account['schema'] == 'BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1' and len(account['rows']) == 106, 'Account path contract')
        first = account['rows'][0]
        for key in ('cash_after_usd','fees_usd','gross_buy_usd'):
            require(number(first[key]) == number(plan[key]), 'First saved trade reconciliation differs: '+key)
        require(first['holdings_after'] == plan['proposed_holdings'] and first['buy_shares'] == plan['buy_shares'], 'First holdings reconciliation differs')
        require(number(account['total_cash_injection_usd']) == number(row['cash_event']['amount_usd'])
                and number(account['total_fees_usd']) == number(plan['fees_usd']), 'Single flow/fee reconciliation differs')
        require(all(result['session'] == day and result['holdings_after'] == plan['proposed_holdings']
                    and number(result['cash_after_usd']) == number(plan['cash_after_usd'])
                    for result,day in zip(account['rows'],calendar[1:])), 'Fixed holdings/cash path differs')
        require(all(result['buy_shares'] == {} and number(result['cash_injection_usd']) == 0
                    and number(result['fees_usd']) == 0 for result in account['rows'][1:]), 'Unexpected later flow/trade')
        for flag in ('dividends_modelled','corporate_actions_modelled','orders_executed','point_in_time_verified','promotion_allowed'):
            require(account[flag] is False, 'Kernel authority changed')
        rows.append({'scenario_id':row['scenario_id'],'lane':lane,'input_row':deepcopy(row),
            'input_reference':pointer(refs['inputs'],f'/rows/{index}'),
            'selection_reference':pointer(refs['repair_results'],f'/rows/{index}/selected'),
            'saved_selection':deepcopy(repaired['selected']), 'selected_plan_reference':selected_ref,'selected_plan':deepcopy(plan),
            'security_to_ticker':mapping,'security_mapping_scope':'FROZEN_PREPARED_CONDITIONAL_MAPPING_NOT_REAUDITED_IDENTITY',
            'security_mapping_reference':pointer(refs['inputs'],f'/rows/{index}/securities'),
            'quote_evidence':quote_evidence,'accounting_inputs':{'initial':{'session':calendar[0],
                'cash_usd':row['starting_cash_usd'],'holdings':{},'close_prices':{}},'sessions':sessions,
                'transaction_cost_bps':row['transaction_cost_bps']},
            'account':account,'drawdown':maximum_drawdown(account),'first_trade_reconciled_to_saved_plan':True,**FLAGS})
    return {'schema':SCHEMA,'rows':rows,'scenario_count':8,'initial_date':calendar[0],
        'observed_calendar':calendar,'account_session_count':106,'price_evidence_metadata':metadata,
        'input_references':deepcopy(refs),'parent_source_hashes_preserved_not_reaudited':{
            role:deepcopy(documents[role].get('source_hashes',documents[role].get('historical_expected_source_hashes',{})))
            for role in documents if role != 'input_publication'},
        'scope':'INITIAL_SELECTED_BUYS_HELD_CONSTANT_PRICE_ONLY_CONDITIONAL_ACCOUNT_PATH',
        'this_account_wrapper_selects_using_future_returns':False,
        'parent_selection_point_in_time_verified':False,'new_cashflow_account_paths_calculated':8,
        'original_nominal_marks_reconstructed':False,'price_only_dividend_omission_explicit':True,
        'saved_action_event_metadata_preserved':True,'time_series_return_evaluated':True,**FLAGS}


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
    require(all(type(digest) is str and len(digest)==64 for _,digest in PINS.values()),'Pending source pins')
    sources={str(SOURCE):LOADED_SHA}; documents={}; refs={}
    for role,(relative,digest) in PINS.items():
        path=ROOT/relative; raw=path.read_bytes(); require(sha(raw)==digest,'Source mismatch: '+role)
        sources[str(path)]=digest; refs[role]={'path':str(path),'sha256':digest}
        if role!='kernel': documents[role]=json.loads(raw)
    for role,names in [('inputs',{'inputs.json','publication.json'}),('old_results',{'started.json','results.json'}),('repair_results',{'started.json','results.json'})]:
        require({p.name for p in Path(refs[role]['path']).parent.iterdir()}==names,'Incomplete parent namespace')
    receipt=documents['input_publication']
    require(receipt['schema']=='FIRST_PERIOD_STANDARD_CASH_INPUTS_PUBLICATION_V1'
            and receipt['input_reference']==refs['inputs'] and receipt['source_hashes']==documents['inputs']['source_hashes']
            and receipt['status']=='INPUTS_ONLY_NOT_EXECUTED','Input publication differs')
    for flag in ('cash_fork_called','orders_executed','point_in_time_verified','promotion_allowed','fork_executable'):
        require(receipt[flag] is False,'Input receipt authority changed')
    account_path=load_account_path(refs)
    def guard():
        for path,digest in sources.items(): require(sha(Path(path).read_bytes())==digest,'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'schema':'FIRST_PERIOD_CASH_BUY_HOLD_STARTED_V1',
            'started_at_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':sources,
            'planned_path_count':8,'retry_allowed':False})
        result=assemble(documents,refs,account_path); result['source_hashes']=sources; guard()
        digest=write_new(OUTPUT/'accounts.json',result); guard()
        receipt={'schema':'FIRST_PERIOD_CASH_BUY_HOLD_PUBLICATION_V1','status':'PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS',
            'account_reference':{'path':str(OUTPUT/'accounts.json'),'sha256':digest},'source_hashes':sources,**FLAGS}
        receipt_sha=write_new(OUTPUT/'publication.json',receipt); guard()
        require(sha((OUTPUT/'accounts.json').read_bytes())==digest and sha((OUTPUT/'publication.json').read_bytes())==receipt_sha
                and {p.name for p in OUTPUT.iterdir()}=={'started.json','accounts.json','publication.json'},'Final publication differs')
        return {'path':str(OUTPUT/'accounts.json'),'sha256':digest,'publication_sha256':receipt_sha,'scenario_count':8}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
