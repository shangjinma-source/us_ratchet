"""Read-only full saved-window adapter; no solve or economic search dispatch."""
from copy import deepcopy
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
from math import prod
from pathlib import Path
import json
import argparse
import sys
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backtest.quantity_integer_box_certificate_prototype import prepare,objective,require


def digest(value):return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()).hexdigest()


def preflight(*,root,prepared_path,prepared_sha256,result_path,result_sha256,decision_date):
    root=Path(root).resolve();read_hashes={}
    def read(path,expected,document=True):
        target=(root/path).resolve();require(target.is_relative_to(root),'SOURCE_OUTSIDE_ROOT')
        raw=target.read_bytes();actual=sha256(raw).hexdigest();require(actual==expected,'SAVED_SOURCE_HASH_CHANGED')
        key=target.relative_to(root).as_posix();require(key not in read_hashes or read_hashes[key]==actual,'SOURCE_PIN_CONFLICT');read_hashes[key]=actual
        return json.loads(raw) if document else None
    prepared=read(prepared_path,prepared_sha256);saved=read(result_path,result_sha256)
    require(date.fromisoformat(decision_date).isoformat()==decision_date,'DECISION_DATE')
    windows=[w for w in prepared['windows'] if w['decision_date']==decision_date]
    require(len(windows)==1,'UNIQUE_FULL_WINDOW_REQUIRED');window=windows[0]
    require(saved.get('status')=='SAVED_FRONTIER_PLUS_CONTINUOUS_CANDIDATES','SAVED_COMPARISON_REQUIRED')
    old=saved['inherited_saved_result'];arguments=deepcopy(window['search_arguments'])
    arguments['entered_cash']=old['entered_cash']
    require(digest(arguments)==saved['binding']['search_arguments_sha256'] and digest(old)==saved['binding']['saved_result_sha256'],'SAVED_ARGUMENT_BINDING_MISMATCH')
    require(arguments['decision_date']==old['decision_date']==decision_date and arguments['scenario_dates']==old['scenario_dates'],'SAVED_DATE_MISMATCH')
    for key in ('entered_cash','fee_bps','minimum_cash_buffer'):require(F(arguments[key])==F(old[key]),'SAVED_CAPITAL_MISMATCH')
    dates=window['training_dates'];require(len(dates)==253 and dates==sorted(set(dates)) and dates[-1]<=decision_date,'TRAINING_WINDOW_INVALID')
    require(arguments['scenario_dates']==dates[21::21] and len(arguments['training_scenarios'])==12,'SCENARIO_DATES_MISMATCH')
    require(all(r.get('status') in ('DRAFT_CONDITIONAL_INPUT_COMPUTED','EXCLUDED_INSUFFICIENT_253_HISTORY') for r in window['candidates']),'UNKNOWN_CANDIDATE_STATUS')
    eligible=[r for r in window['candidates'] if r.get('status')=='DRAFT_CONDITIONAL_INPUT_COMPUTED']
    require(eligible,'EXPLICIT_ELIGIBLE_ROWS_REQUIRED')
    require(type(window['member_denominator'])is int and window['member_denominator']==len(window['candidates']),'MEMBER_DENOMINATOR_MISMATCH')
    require(len({r['ticker'] for r in window['candidates']})==len(window['candidates']),'CANDIDATE_TICKER_DUPLICATE')
    declared_ids=[r.get('security_id') for r in window['candidates'] if r.get('security_id')is not None]
    require(len(declared_ids)==len(set(declared_ids)),'CANDIDATE_SID_DUPLICATE')
    for row in window['candidates']:
        if row['status']=='EXCLUDED_INSUFFICIENT_253_HISTORY':
            exclusion=row['history_exclusion']
            require(exclusion['reason']=='INSUFFICIENT_VALID_PREDECISION_253_CLOSES' and exclusion['missing_count']==len(set(exclusion['missing_dates'])) and exclusion['missing_count']>0 and set(exclusion['missing_dates'])<=set(dates),'EXCLUSION_EVIDENCE_REQUIRED')
    ids=[r['security_id'] for r in eligible]
    require(len(ids)==len(set(ids)) and set(ids)==set(arguments['prices'])==set(arguments['metadata']),'ELIGIBLE_DOMAIN_OMITTED')
    pins=prepared['source_hashes'];require(type(pins)is dict and pins,'DECLARED_SOURCE_PINS_REQUIRED')
    for path,h in pins.items():read(path,h,False)
    for row in eligible:
        sid=row['security_id'];meta=arguments['metadata'][sid]
        require(meta['ticker']==row['ticker'] and meta['issuer_id']==row['issuer_id'],'HISTORICAL_IDENTITY_MISMATCH')
        identity=row['identity_binding'];require(identity['security_id']==sid and identity['ticker']==row['ticker'],'HISTORICAL_IDENTITY_MISMATCH')
        require(identity['valid_from']<=decision_date<=identity['valid_through'],'IDENTITY_WINDOW_MISMATCH')
        require(row['training_source'] in pins,'TRAINING_SOURCE_UNBOUND')
        values=list(map(F,row['training_close']));require(len(values)==253 and all(v>0 for v in values),'FULL_PRICE_HISTORY_REQUIRED')
        require(F(row['decision_cost'])==F(arguments['prices'][sid]),'DECISION_PRICE_MISMATCH')
        for j,index in enumerate(range(0,252,21)):
            require(values[index+21]/values[index]==F(arguments['training_scenarios'][j][sid]),'SCENARIO_PRICE_MISMATCH')
    fields=('prices','metadata','entered_cash','fee_bps','minimum_cash_buffer','training_scenarios')
    inputs={k:arguments[k] for k in fields};problem=prepare(**inputs)
    q=saved['selected']['quantities'];value,_,notional=objective(problem,q)
    record=saved['selected'];require(record['actual_k']==len(q) and F(record['notional'])==notional and F(record['residual_cash'])==problem['cash']-notional*(1+problem['fee']),'SAVED_INCUMBENT_MISMATCH')
    if record.get('training_gross_growth_product')is not None:require(F(record['training_gross_growth_product'])==value,'SAVED_OBJECTIVE_MISMATCH')
    highs={s:int(problem['spendable']//problem['cost'][s]) for s in problem['ids']}
    cheapest={}
    for sid in problem['ids']:
        issuer=problem['metadata'][sid]['issuer_id'];cheapest[issuer]=min(cheapest.get(issuer,problem['cost'][sid]),problem['cost'][sid])
    costs=sorted(cheapest.values());affordable=[k for k in range(1,len(costs)+1) if sum(costs[:k],F(0))<=problem['spendable']]
    # Recheck all bytes after interpretation; immutable binding only, no fresh data.
    for path,h in list(read_hashes.items()):read(path,h,False)
    return dict(schema='FULL_SAVED_INTEGER_DOMAIN_PREFLIGHT_V1',status='PREPARED_NOT_SEARCHED',decision_date=decision_date,available_decision_dates=[w['decision_date'] for w in prepared['windows']],excluded_candidates=[r for r in window['candidates'] if r['status']=='EXCLUDED_INSUFFICIENT_253_HISTORY'],inputs=inputs,initial_quantities=q,
        source_hashes=read_hashes,search_arguments_sha256=digest(arguments),member_denominator=window['member_denominator'],eligible_sid_count=len(ids),issuer_count=len(costs),
        all_k_preserved=True,affordable_k=[0]+affordable,root_box={s:[0,v] for s,v in highs.items()},root_integer_box_points=str(prod(v+1 for v in highs.values())),
        root_points_are_upper_count_before_budget_and_issuer_constraints=True,incumbent_product=str(value),incumbent_feasible=True,search_calls=0,economic_runs=0,
        point_in_time_certified=False,source_authentication_scope='SAVED_BYTES_AND_DECLARED_PINS_ONLY_NOT_OFFICIAL_HISTORICAL_IDENTITY_CERTIFICATION',
        limitations=['Conditional historical identity assumptions are retained verbatim. No current metadata replacement.', 'Prepared saved prices are reconstructed; raw source bytes are hashed but their vendor prices are not reparsed by this adapter.', 'Resource count is not runtime estimate or global-optimum evidence.'],
        historical_identity_bindings={r['security_id']:r['identity_binding'] for r in eligible})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('root','prepared_path','prepared_sha256','result_path','result_sha256','decision_date'):parser.add_argument('--'+field.replace('_','-'),required=True)
    print(json.dumps(preflight(**vars(parser.parse_args())),ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
