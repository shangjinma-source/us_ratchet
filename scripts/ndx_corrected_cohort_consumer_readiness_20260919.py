"""Read-only frozen-cohort/consumer contract inventory; no numerical imports."""
import ast,hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
INVENTORY=BASE/'three_cell_corrected_paired_overlay_20260919_v2/all15_consumption_inventory_20260919.json'
INVENTORY_SHA='b1308d0a50cb3c3ab2a6b4b5720c170f0c05ce4419a47d4be2e3a13be260c3de'
PLAN=BASE/'delta_selected_input_20260912_v1/plan.json'
PLAN_SHA='f0ff0242f08dcb62ceb19d5650db811fe8d0d83741f7ecc995b6a3945cf15266'
IDENTITY=BASE/'current_nine_identity_capture_20260919_v1/current_identity_facts.json'
IDENTITY_SHA='33eb7055e9072431def42f0a9fa88a0f03c245efd8664844c620955ca576fa32'
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CONTRACTS=(
 ('scripts/ndx_combined_fractional_frontier.py','run_date',('combined_summary_inventory_20260912','ndx_combined_fractional_frontier_report_v1')),
 ('backtest/ndx_combined_fractional_frontier_research.py','analyze_combined_date',('ndx_combined_fractional_date_v1','UNRESOLVED_CURRENT_PURE_TECH_DEFINITION')),
 ('scripts/ndx_frontier_cutoff_refit_research.py','_candidates',('ndx_combined_fractional_frontier_report_v1','UNRESOLVED_CURRENT_PURE_TECH_DEFINITION')),
 ('backtest/ndx_dynamic_refit_schedule_research.py','build_refit_schedule_research',('Eight original fit/risk parameters required','Exact selected identity/risk schema required')),
 ('scripts/ndx_preference_retrospective_accounting_research.py','prepare_inputs',('Exactly four dated primary-source security links required','Fixed reference composition differs')),
 ('scripts/ndx_incumbent_nominal_control_research.py','prepare_inputs',('ndx_incumbent_nominal_control_research_v1',)),
 ('scripts/ndx_retrospective_same_calendar_comparison_research.py','build_report',('Complete 295-session 15-decision path required','CONDITIONAL_FIXED_REFERENCE_PATH_OBSERVATION_NOT_PORTFOLIO_SELECTION')))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,digest,sources):
    raw=Path(path).read_bytes()
    if sha(raw)!=digest:raise ValueError('Hard input changed')
    sources[str(path)]=digest;return json.loads(raw)
def validate_inventory(inventory,plan):
    if inventory['schema']!='ndx_corrected_cohort_all15_consumption_inventory_20260919_v1':raise ValueError('Final consumption inventory required')
    expected=dict(original_count=351255,available_count=340001,pending_count=11254,equal_available=319473,base_available=19548,delta_available=980,date_count=15,paired_tasks_completed_and_consumed=614)
    if any(type(inventory.get(k)) is not int or inventory[k]!=v for k,v in expected.items()):raise ValueError('Bound 351255/11254 denominator differs')
    if any(inventory.get(k) is not False for k in ('historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','selection_performed','training_performed')) or inventory['winner'] is not None:raise ValueError('Unsupported inventory upgrade')
    dates=inventory['dates'];pending=Counter();seen=set()
    for day in plan['dates']:
        for row in day['tasks']:
            task=row['task'];key=(task['selection_date'],task['job_id'])
            if key in seen:raise ValueError('Duplicate selected task')
            seen.add(key);pending[key[0].replace('-','')]+=1
    if len(seen)!=11254 or len(dates)!=15 or [r['date'] for r in dates]!=sorted({r['date'] for r in dates}):raise ValueError('Exact fifteen dates required')
    for row in dates:
        if any(type(row.get(k)) is not int for k in ('pending','available','original_count')) or row['pending']!=pending[row['date']] or row['available']+row['pending']!=row['original_count']:raise ValueError('Per-date complete denominator differs')
        for prefix in ('overlay','audit'):
            if inventory['verified_direct_artifact_hashes'].get(row[prefix+'_path'])!=row[prefix+'_sha256']:raise ValueError('Inventory source descriptor differs')
    if sum(r['available'] for r in dates)!=340001 or sum(r['pending'] for r in dates)!=11254:raise ValueError('All-date sums differ')
    return [dict(date=r['date'],original_count=r['original_count'],available_in_bound_overlay=r['available'],pending_in_bound_overlay=r['pending'],
        original_overlay=dict(path=r['overlay_path'],sha256=r['overlay_sha256']),original_diff_audit=dict(path=r['audit_path'],sha256=r['audit_sha256']),
        complete_corrected_date_consumable=False,blocked_by='PENDING_SELECTED_RESULT_MERGE_AND_INDEPENDENT_FULL_RECORD_DIFF',
        external_selected_completion_not_observed_by_this_frozen_inventory=True) for r in dates]
def inspect_contract(relative,function,markers,sources):
    path=ROOT/relative;raw=path.read_bytes();tree=ast.parse(raw)
    functions=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==function]
    strings={n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and type(n.value) is str}
    if len(functions)!=1 or not set(markers)<=strings:raise ValueError('Observed consumer contract changed: '+relative)
    sources[str(path)]=sha(raw);node=functions[0]
    return dict(path=str(path),sha256=sha(raw),entrypoint=function,line=node.lineno,required_source_contract_literals=list(markers),
        positional_parameters=[a.arg for a in node.args.args],keyword_parameters=[a.arg for a in node.args.kwonlyargs],directly_accepts_corrected_overlay_inventory=False)
def build():
    sources={str(SOURCE):LOADED};inventory=read(INVENTORY,INVENTORY_SHA,sources);plan=read(PLAN,PLAN_SHA,sources)
    dates=validate_inventory(inventory,plan);contracts=[inspect_contract(*c,sources) for c in CONTRACTS]
    identity=read(IDENTITY,IDENTITY_SHA,sources)
    if identity['matched_count']!=9 or identity['candidate_count']!=11 or identity['provider_price_identity_bound'] is not False or identity['point_in_time_verified'] is not False:raise ValueError('Current-only identity fact contract differs')
    stages=[
      dict(stage='CORRECTED_CROSS_K_ECONOMIC_FRONTIER',current_status='BLOCKED_FOR_COMPLETE_DATE_COMPETITION',after_selected_date_complete='NEW_CORRECTED_DATE_ADAPTER_REQUIRED',
           requirements=['Exact full original per-date origin/task denominator and independent merged-record audit','Three-cell corrected training semantics with preserved original context provenance','Replace obsolete pure-technology UNKNOWN scope contract only in a new version reflecting all-NDX user scope','Recompute frontier over all complete records; never select among available-only rows or clip prior frontier']),
      dict(stage='CUTOFF_REFIT',current_status='NOT_RUN_BY_THIS_INVENTORY',after_selected_date_complete='ECONOMIC_COMPLETION_ALONE_INSUFFICIENT',
           requirements=['Bound complete new frontier/reference schema','Explicit as-of cutoff and legitimate returns calendar','Eight original fit/risk parameters and selected SID/issuer/ticker/risk identities','Latest completed cutoff requires new input evidence, not relabeling 2024-05-31 as current']),
      dict(stage='VARIABLE_CARDINALITY_CONTINUOUS_SCHEDULE',current_status='GENERIC_RESEARCH_BUILDER_EXISTS_INPUTS_NOT_READY',after_selected_date_complete='NOT_DIRECTLY_EXECUTABLE',
           requirements=['Explicit selected path across decisions with prior-target anchor','Next observed trading session execution dates and all five risk parameters fixed','No historical weights reused as current targets without cutoff refit','k and issuer pool denominator independently established; old restricted candidate pool is not full NDX']),
      dict(stage='CONTINUOUS_WHOLE_SHARE_DUAL_BENCHMARK',current_status='FIXED_REFERENCE_PATH_ONLY_NO_GENERAL_CANDIDATE_ADMISSION',after_selected_date_complete='PRICE_IDENTITY_AND_EXECUTION_ADAPTER_REQUIRED',
           requirements=['Per-session stable security ID, issuer and actual ticker without alias stitching','Nominal USD Open/Close and explicit split/dividend/corporate action policy over same calendar','Candidate, original incumbent and 012922 share exact window; NAV native currency/publication/FX limitations disclosed','Existing reference implementation hard-locks 295 sessions/15 decisions, 25000 capital/100 cash buffer/10bps and four preference names; do not generalize by changing flags'])]
    gaps=[dict(kind='HISTORICAL_MEMBERSHIP',status='FULL_POINT_IN_TIME_SECURITY_CLASS_BASELINE_NOT_ESTABLISHED'),
          dict(kind='CURRENT_SEC_IDENTITY',status='NINE_CIK_TICKER_EXCHANGE_OBSERVATIONS_AVAILABLE_NOT_HISTORICAL_PRICE_BINDING',reference=dict(path=str(IDENTITY),sha256=IDENTITY_SHA)),
          dict(kind='HISTORICAL_PROVIDER_IDENTITY',status='COMPLETE_INTERVAL_AND_PROVIDER_SECURITY_BINDING_NOT_CERTIFIED'),
          dict(kind='CORPORATE_ACTIONS',status='SPECIFIC_EVENT_FACTS_DO_NOT_PROVE_ALL_ACTIONS_COMPLETE'),
          dict(kind='PRICE_HISTORY',status='CURRENT_CHANNEL_BIRTH_AND_REGULAR_WAY_SEGMENTS_REQUIRE_EXPLICIT_HANDLING'),
          dict(kind='SOURCE_PROVENANCE',status='26_ORIGINAL_ROOT_PRICE_HASH_GAPS_NOT_RECOVERED_BY_NEW_RAW_OR_ARCHIVE'),
          dict(kind='FORWARD_OOS',status='INDEPENDENT_PROMOTION_EVIDENCE_NOT_PROVIDED_BY_HISTORICAL_READBACK')]
    report=dict(schema='CORRECTED_COHORT_CONSUMER_CONTRACT_READINESS_V1',bound_inventory=dict(path=str(INVENTORY),sha256=INVENTORY_SHA),dates=dates,original_count=351255,available_in_bound_overlay=340001,pending_in_bound_overlay=11254,
        source_hashes=sources,consumer_contracts=contracts,next_stages=stages,evidence_gaps=gaps,
        verification_scope='HARD_CONSUMPTION_INVENTORY_AND_SELECTED_PLAN_COUNTS_PLUS_STATIC_CONSUMER_CONTRACTS',
        underlying_overlay_records_rehashed_or_recomputed_here=False,transitive_numerical_source_closure_verified=False,latest_selected_completed_count_observed=False,
        full_ndx_pool_coverage_verified=False,execution_ready=False,selection_performed=False,training_performed=False,execution_performed=False,point_in_time_verified=False,promotion_allowed=False)
    verify(report);return report
def verify(report):
    for path,digest in report['source_hashes'].items():
        if sha(Path(path).read_bytes())!=digest:raise ValueError('Readiness source changed')
if __name__=='__main__':
    report=build();folder=BASE/'corrected_cohort_consumer_readiness_20260919_v1';folder.mkdir(exist_ok=False);path=folder/'inventory.json'
    with path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    verify(report);print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()))))
