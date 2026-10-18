"""Independent 21-session conditional account comparison; no execution or fit calls."""
import argparse
import hashlib
import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_frozen_accounting_independent_audit_research as accounting
from backtest import ndx_frozen_target_normalization_audit_research as normalization
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_seven_dated_identity_assembly_20260919 as identity
from scripts.ndx_may_cutoff_snapshot_independent_readback_20260919 import verify_gaps
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish
BASE=ROOT/'data/cache/research'
BOUND={
 'historical_failure':('two_period_conditional_execution_20260919_v1/account.json.failure.json','39a35e86644c878ffe07bb7658da3e7ceb351f8328172da9cb542e9963ab9775'),
 'identity':('seven_dated_identity_assembly_20260919_v1/identities.json','ed810b2fc1626e05f3c1edee10212645dad37435461b8b7e8d01dcba1354e7c2'),
 'prefix':('two_period_benchmark_prefix_20260919_v1/prefix.json','f55875a7e8c0ab109b2628866da9fc09bd99f74404b4bd274da078dba5a99c7d'),
 'target':('corrected_explicit_path_20260919_v1/target_path.json','3270302ee18a8a4a3503ab9227bebc53c6a4b3a6728c79ffdc8b5c5196fee266'),
 'target_audit':('corrected_explicit_path_20260919_v1/independent_audit.json','afff057b93b7ddaa7478bf1b879e8c3960024fcd97a759203c0147461d5c0fbb'),
 'prices':('seven_ticker_price_only_20260919_v1/prices.json','56dece6ee94518d39fbeb101d1d5e06c7351a05e90dd70cf87adf713196cc7bb')}
CLOCK=[['2023-03-31','2023-04-03'],['2023-04-28','2023-05-01']]
CONTRACT=dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,max_single_weight=.45,
 min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
FALSE=('fit_performed','execution_rerun','winner_selected','formal_eight_dimension_evaluation','out_of_sample_evaluation',
 'promotion_allowed','point_in_time_verified','provider_security_identity_verified','complete_corporate_actions_verified',
 'dividend_cash_flows_modelled','nav_publication_time_verified','currency_fx_equivalence_verified',
 'subscription_redemption_fee_equivalence_verified','historical_full_source_closure_verified')
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),Path(accounting.__file__).resolve(),
 Path(identity.__file__).resolve(),Path(normalization.__file__).resolve(),archive.SOURCE,Path(verify_gaps.__code__.co_filename).resolve(),Path(publish.__code__.co_filename).resolve())}


def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('Duplicate JSON key')
        value[key]=item
    return value


def metrics(values):
    if len(values)!=21:raise ValueError('21 observations / 20 return intervals required')
    values=[accounting.number(v) for v in values]
    if any(v<=0 for v in values):raise ValueError('Positive account values required')
    with localcontext() as context:
        context.prec=50;ratio=values[-1]/values[0];peak=values[0];dd=Decimal(0)
        for value in values:peak=max(peak,value);dd=max(dd,1-value/peak)
        return dict(path_return=str(ratio-1),annualized_return_252_over_20=str(ratio**(Decimal(252)/20)-1),
            path_max_drawdown=str(dd),observation_count=21,return_interval_count=20,annualization_is_short_window_diagnostic=True)


def audit_account(candidate,target,price,identities):
    if candidate['schema']!='TWO_PERIOD_CONDITIONAL_FROZEN_ACCOUNT_V2' or target['schema']!='CORRECTED_EXPLICIT_STRATEGIC_TARGET_PATH_V1' or price['schema']!='SEVEN_TICKER_21_SESSION_PRICE_ONLY_V1':raise ValueError('Expected bounded v2 account/target/price schemas required')
    for key in ('fit_performed','legacy_identity_bridge_called','frozen_engine_source_modified','additional_cash_flows_supported',
                'dividend_cash_flows_modelled','continuous_identity_interval_verified','provider_binding_verified',
                'corporate_action_completeness_verified','point_in_time_verified','promotion_allowed'):
        if candidate[key] is not False:raise ValueError('Conditional candidate scope upgraded')
    if candidate['execution_performed'] is not True:raise ValueError('Saved account required')
    identity.validate_report(identities)
    labels={r['security_id']:r for r in identities['rows']}
    calendar=price['calendar'];schedule=target['schedule']
    if len(calendar)!=21 or calendar!=sorted(set(calendar)) or calendar[0]!='2023-03-31' or calendar[-1]!='2023-05-01' or candidate['calendar']!=calendar or calendar!=[d for d in target['calendar'] if calendar[0]<=d<=calendar[-1]]:raise ValueError('Common bounded calendar differs')
    if [[r['decision_date'],r['execution_date']] for r in schedule]!=CLOCK or not exact(candidate['schedule'],schedule):raise ValueError('Exact two-period target schedule required')
    normalized,evidence=normalization.normalized_schedule(schedule)
    if not exact(candidate['normalized_schedule'],normalized) or not exact(candidate['normalization_evidence'],evidence):raise ValueError('Exact independently calculated single-normalization evidence required')
    if set().union(*(r['targets'] for r in schedule))!=set(labels) or set(price['tickers'])!={r['ticker'] for r in labels.values()} or len(price['tickers'])!=7:raise ValueError('Seven target/identity/price union differs')
    if set(candidate['execution_contract'])!=set(CONTRACT) or any(accounting.number(candidate['execution_contract'][k])!=accounting.number(v) for k,v in CONTRACT.items()):raise ValueError('25000/100/10bps/five-risk execution contract differs')
    expected_target=dict(initial_cash_usd=target['downstream_execution_capital_usd'],minimum_cash_buffer_usd=target['downstream_execution_cash_buffer_usd'],transaction_cost_bps=target['downstream_execution_transaction_cost_bps'],**target['fixed_risk_parameters'])
    if any(accounting.number(expected_target[k])!=accounting.number(v) for k,v in CONTRACT.items()):raise ValueError('Target objective contract differs')
    for row in schedule:
        for sid,t in row['targets'].items():
            if (t['ticker'],t['issuer_id'])!=(labels[sid]['ticker'],labels[sid]['issuer_id']):raise ValueError('Conditional identity target coordinate differs')
    expected_columns={sid:'SID_'+sid.split(':')[1]+'_'+sid.split(':')[2] for sid in labels}
    if candidate['internal_columns']!=expected_columns:raise ValueError('Stable internal column map differs')
    marks={d:{} for d in calendar}
    for kind in ('open','close'):
        if set(price['matrices'][kind])!=set(calendar):raise ValueError('Price calendar missing')
        for day in calendar:
            if set(price['matrices'][kind][day])!=set(price['tickers']):raise ValueError('Price security denominator differs')
            for sid,label in labels.items():marks[day].setdefault(sid,{'ticker':label['ticker']})[kind]=price['matrices'][kind][day][label['ticker']]
    result=accounting.audit(execution=candidate['execution'],calendar=calendar,schedule=normalized,prices=marks,
        risk_chains_by_decision=target['risk_chains_by_decision'],contract=CONTRACT)
    if not exact(result,candidate['independent_decimal_accounting']):raise ValueError('Embedded audit differs from new independent calculation')
    return result,metrics([r['total_value_usd'] for r in candidate['execution']['daily']])


def audit_raw_receipt(candidate,receipt,identities):
    if receipt['schema']!='TWO_PERIOD_RAW_EXECUTION_RECEIPT_V2' or any(receipt[k] is not False for k in ('independent_accounting_completed','point_in_time_verified','promotion_allowed')):raise ValueError('Unadjudicated raw receipt schema differs')
    for old,new in (('original_schedule','schedule'),('calendar','calendar'),('execution_contract','execution_contract'),('internal_columns','internal_columns'),('started_attempt','started_attempt'),('historical_expected_source_hashes','historical_expected_source_hashes')):
        if not exact(receipt[old],candidate[new]):raise ValueError('Raw receipt inputs/attempt/source differ')
    # Independent label-only restoration: all remaining raw engine fields must be exact.
    restored=json.loads(json.dumps(receipt['execution'],allow_nan=False));columns=candidate['internal_columns'];labels={r['security_id']:r['ticker'] for r in identities['rows']}
    for row in restored['decisions']:
        for sid,value in row['targets'].items():
            if value['ticker']!=columns[sid]:raise ValueError('Raw decision internal ticker differs')
            value['ticker']=labels[sid]
    for row in restored['trades']:
        sid=row['security_id']
        if row['ticker']!=columns[sid]:raise ValueError('Raw trade internal ticker differs')
        row['ticker']=labels[sid]
    for row in restored['daily']:
        if row['tickers']!={sid:columns[sid] for sid in row['shares']}:raise ValueError('Raw daily internal ticker differs')
        row['tickers']={sid:labels[sid] for sid in row['shares']}
    if not exact(restored,candidate['execution']):raise ValueError('Candidate changed raw engine ledger beyond ticker restoration')


def compare(prefix,candidate_calendar,candidate_metrics):
    if prefix['schema']!='TWO_PERIOD_BENCHMARK_PREFIX_INDEPENDENT_ACCOUNTING_V1' or prefix['calendar']!=candidate_calendar or prefix['decision_clock']!=CLOCK:raise ValueError('Benchmark clock differs')
    for key in ('execution_rerun','fit_performed','risk_is_order_gate','cash_dividends_modelled','nav_publication_time_verified','currency_fx_equivalence_verified','subscription_redemption_fee_equivalence_verified','point_in_time_verified','promotion_allowed','comparison_winner_selected'):
        if prefix[key] is not False:raise ValueError('Conditional benchmark scope differs')
    control=prefix['incumbent'];nav=prefix['nav']
    if any(accounting.number(control[k])!=CONTRACT[k] for k in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps')):raise ValueError('Control capital/fee differs')
    if [[r['decision_date'],r['execution_date']] for r in control['schedule']]!=CLOCK or [r['session'] for r in control['daily']]!=candidate_calendar or [r['session'] for r in nav['rows']]!=candidate_calendar:raise ValueError('Reference observation denominator differs')
    references={'original_incumbent':metrics([r['total_value_usd'] for r in control['daily']]),'012922_native_currency_nav':metrics([r['equity_index'] for r in nav['rows']])}
    for key,value in references.items():
        saved=control['metrics'] if key=='original_incumbent' else nav['metrics']
        if not exact(value,saved):raise ValueError('Sealed benchmark metrics do not reproduce')
    with localcontext() as context:
        context.prec=50
        differences={key:{metric:str(Decimal(candidate_metrics[metric])-Decimal(value[metric])) for metric in ('path_return','annualized_return_252_over_20','path_max_drawdown')} for key,value in references.items()}
    return dict(candidate=candidate_metrics,references=references,candidate_minus_reference=differences,
        difference_semantics='RETURN_POSITIVE_IS_HIGHER_DRAWDOWN_POSITIVE_IS_WORSE_NO_WINNER_OR_ADMISSION')


def build(candidate_path,candidate_sha256):
    sources=dict(LOADED)
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact hash differs')
        archive.merge(sources,{str(path):sha});return json.loads(raw,object_pairs_hook=unique)
    docs={k:read(BASE/p,h) for k,(p,h) in BOUND.items()};candidate=read(candidate_path,candidate_sha256)
    started=read(candidate['started_attempt']['path'],candidate['started_attempt']['sha256'])
    if started['schema']!='TWO_PERIOD_CONDITIONAL_EXECUTION_ATTEMPT_V2' or started['status']!='STARTED_NOT_COMPLETED' or not exact(started['source_hashes'],candidate['historical_expected_source_hashes']):raise ValueError('Durable execution attempt source closure differs')
    ref=started['identity_reference']
    if ref!={'path':str(BASE/BOUND['identity'][0]),'sha256':BOUND['identity'][1]}:raise ValueError('Explicit approved conditional identity reference differs')
    identities=docs['identity']
    if not exact(identities,identity.build()):raise ValueError('Dated original identity evidence does not reconstruct')
    failure_ref={'path':str(BASE/BOUND['historical_failure'][0]),'sha256':BOUND['historical_failure'][1]}
    if candidate['historical_v1_failure_reference']!=failure_ref or started['historical_v1_failure_reference']!=failure_ref:raise ValueError('Historical failed attempt linkage differs')
    raw_ref=candidate['raw_execution_reference'];receipt=read(raw_ref['path'],raw_ref['sha256']);audit_raw_receipt(candidate,receipt,identities)
    target=docs['target']['result'];target_audit=docs['target_audit']
    if target_audit['result']!={'path':str(BASE/BOUND['target'][0]),'sha256':BOUND['target'][1]} or target_audit['whole_first_seed_refit_exact'] is not True or target_audit['complete_strategic_prior_verified'] is not True:raise ValueError('Target independent audit linkage differs')
    candidate_sources=candidate['historical_expected_source_hashes']
    for path,sha in [(str(BASE/BOUND[k][0]),BOUND[k][1]) for k in ('target','target_audit','prices','historical_failure')]+[(str(Path(ref['path']).resolve()),ref['sha256']),(str(Path(normalization.__file__).resolve()),LOADED[str(Path(normalization.__file__).resolve())])]:
        if candidate_sources.get(path)!=sha:raise ValueError('Candidate missing mandatory target/audit/price/identity source')
    for doc in (candidate,docs['prefix'],target,docs['prices'],target_audit,identities):
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in doc:archive.merge(sources,doc[key])
    archive.merge(sources,docs['target']['runner_source_hashes'])
    gaps=target['historical_loader_gap_observations']
    if not exact(gaps,candidate['historical_loader_gap_observations']):raise ValueError('Historical loader gap changed')
    verify_gaps(gaps);contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    audit,measures=audit_account(candidate,target,docs['prices'],identities);comparison=compare(docs['prefix'],candidate['calendar'],measures)
    result=dict(schema='TWO_PERIOD_CONDITIONAL_COMPARISON_INDEPENDENT_V1',candidate_reference={'path':str(Path(candidate_path).resolve()),'sha256':candidate_sha256},
        calendar=candidate['calendar'],decision_clock=CLOCK,independent_accounting=audit,comparison=comparison,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,contract),historical_loader_gap_observations=gaps,
        limitations=['21 observations / 20 returns: annualization is diagnostic, not a one-year forecast',
         '012922 native-currency NAV uses retrospective backward dates; publication, FX and subscription fees unverified',
         'No cash dividends; conditional dated identities and split-only quote basis; complete corporate actions unknown',
         'Explicit two-target path, not full candidate competition, formal eight-dimension evaluation or OOS'],**dict.fromkeys(FALSE,False))
    verify(result);return result


def verify(result):
    required=dict(LOADED,**{str(BASE/p):h for p,h in BOUND.values()})
    if result['schema']!='TWO_PERIOD_CONDITIONAL_COMPARISON_INDEPENDENT_V1' or any(result[k] is not False for k in FALSE):raise ValueError('Comparison scope differs')
    if any(result['historical_expected_source_hashes'].get(p)!=h for p,h in required.items()):raise ValueError('Required source omitted')
    ref=result['candidate_reference']
    if result['historical_expected_source_hashes'].get(ref['path'])!=ref['sha256']:raise ValueError('Candidate source omitted')
    verify_gaps(result['historical_loader_gap_observations'])
    if archive.verify_expected_sources(result['historical_expected_source_hashes'],archive.load_contract())!=result['archive_resolution']:raise ValueError('Source partition drift')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('candidate-path','candidate-sha256','output'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();value=build(args.candidate_path,args.candidate_sha256);verify(value);saved=publish(args.output,value);verify(value);print(json.dumps(saved))
