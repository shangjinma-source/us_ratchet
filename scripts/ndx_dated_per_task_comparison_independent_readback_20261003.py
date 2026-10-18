"""Read saved per-task comparison with independent six-path arithmetic."""
from decimal import Context,Decimal,localcontext
from fractions import Fraction
import argparse,hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research/dated_per_task_economic_comparison_20261003_v1'
PRODUCER=ROOT/'scripts/ndx_dated_per_task_economic_comparison_20261003.py'
PRODUCER_SHA='3b808e10071b7e5f67f337a79ae95ab974d4245c4201436ffde85fc54c66531f'
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
SHARED={
 'incumbent_account':('data/cache/research/dated_account_execution_20261003_v1/incumbent/raw.json','ed060c2cc58f0465c7e47f30e0d5315b4179c85da543e305b2fbd12f53ca7d05'),
 'account_audit':('DYNAMIC_DATED_FIRST_ACCOUNTS_INDEPENDENT_READBACK_20261003.json','64c68233d31913422ef7d3f823602f3f1ecd85c2309184f7cf4cb2d623d4af7a'),
 'continuous':('data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/diagnostic.json','bb81bc97c9bb5564afeab9eed4a1421e40fe5274ae29807ce9994bd7b70b8c7f'),
 'continuous_audit':('DYNAMIC_DATED_CONTINUOUS_INDEPENDENT_READBACK_20261003.json','3dca84ea418360f1c039c437614c0887966c665cdfbf4c5c0c99484659d42057'),
 'nav_metrics':('data/cache/research/same_window_nav_reference_metrics_20261003_v1/metrics.json','2f2d072190115b38de2776b8ba33b50372a8546b2c858766751b79915c78dcfa'),
 'nav_audit':('DYNAMIC_SAME_WINDOW_NAV_REFERENCE_INDEPENDENT_READBACK_20261003.json','92b73cc2c812f044e182c5ee7d966bdb245dfd531b01bd28ea1b0e11313a7337')}
FALSE=('account_executed','fit_performed','raw_prices_redecoded','formal_comparison_passed','formal_noninferiority_verified','benchmark_qualified','winner_selected','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','cohort_p90_computed','mode_selected_using_results','point_in_time_verified','promotion_allowed','execution_authorized','future_independent_oos','untouched_holdout','source_bytes_authenticated','original_economic_values_exact','subscription_redemption_execution_required_for_reference_metrics','complete_economic_comparison_verified','integer_missing_replaced_with_cash','shared_control_reexecuted')

def require(ok,message):
    if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,message):require(enc(a)==enc(b),message)
def rational(v):
    if type(v) is dict:
        require(set(v)=={'numerator','denominator'},'Exact rational keys');return Fraction(int(v['numerator']),int(v['denominator']))
    require(type(v) is str,'Saved exact string');return Fraction(v)
def point_ref(ref,pointer):return dict(ref,json_pointer=pointer)

def inspect_metrics(saved,values,dates):
    require(len(values)==127 and all(v>0 for v in values),'Complete positive127')
    values=[v/values[0] for v in values];peak=values[0];pi=0;worst=Fraction(0);pair=(0,0)
    for i,v in enumerate(values):
        if v>peak:peak=v;pi=i
        if 1-v/peak>worst:worst=1-v/peak;pair=(pi,i)
    require(worst==max(1-values[j]/values[i] for i in range(127) for j in range(i,127)),'All pairs independent drawdown')
    result=dict(cumulative_return=values[-1]-1,annualized_return=values[-1]**2-1,maximum_drawdown=worst)
    for k,v in result.items():inspect_metric(saved[k],v)
    exact(saved['normalized_values_exact'],[str(v) for v in values],'Every path point')
    exact(saved['annualization'],dict(trading_days_per_year=252,return_interval_count=126,exponent_exact='2',formula='(LAST / FIRST) ** 2 - 1',historical_diagnostic_only=True),'Annualization')
    exact(saved['drawdown'],dict(first_observation_included_as_peak=True,peak_index=pair[0],trough_index=pair[1],peak_session=dates[pair[0]],trough_session=dates[pair[1]],equal_peak_policy='EARLIEST_UNTIL_STRICTLY_HIGHER_PEAK',equal_maximum_policy='FIRST_STRICT_MAXIMUM'),'Drawdown metadata')
    return result

def inspect_metric(saved,v):
    with localcontext(Context(prec=80)):display=str(Decimal(v.numerator)/Decimal(v.denominator))
    exact(saved,dict(exact=str(v),decimal=display,unit='DIMENSIONLESS_RATIO_NOT_PERCENT'),'Metric arithmetic and display')

def inspect(c,accounts,continuous,nav,refs,availability):
    dates=nav['reference_calendar']['dates'];require(len(dates)==127 and dates==sorted(set(dates)) and (dates[0],dates[1],dates[-1])==('2026-03-20','2026-03-23','2026-09-21'),'Full fixed calendar')
    exact(c['calendar'],dates,'Same calendar');exact(c['source_references_preserved'],refs,'Actual source pointers');exact(c['candidate_integer_status_preserved'],availability,'Original availability')
    claims={}
    for r in [v for v in refs.values() if v is not None]+[availability['evidence_reference']]:
        require(r['path'] not in claims or claims[r['path']]==r['sha256'],'Conflicting per-track claims');claims[r['path']]=r['sha256']
    exact(c['source_hash_claims'],claims,'Every source claim')
    exact(c['numeric_helper_reference'],dict(path=str(ROOT/'backtest/ndx_dated_economic_comparison_research.py'),sha256='6216723e1d906ba689be58aa9eaee4f6b43dd2711ad2ed681566a1c7c3c5ef1b',functions=['number','metric','metrics','calendar_check']),'Pinned helper declaration')
    require(c['schema']=='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1','Comparison schema')
    missing=accounts['candidate'] is None
    require(missing==(availability['status']!='AVAILABLE'),'No invented account')
    require(c['status']==('PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE' if missing else 'ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY'),'Partial status')
    exact(c['valuation_point_count'],127,'Point count');exact(c['return_interval_count'],126,'Interval count')
    require(set(c['tracks'])=={'candidate_integer','incumbent_integer','candidate_continuous','incumbent_continuous'},'All four tracks')
    calculated={};observations=0
    for role in ('candidate','incumbent'):
        for kind in ('integer','continuous'):
            name=role+'_'+kind;saved=c['tracks'][name];original=accounts[role] if kind=='integer' else continuous[role]
            if original is None:
                exact(saved,dict(status=availability['status'],metrics=None,source_reference=None,stored_values_exact=None,original_account_preserved=None,missing_evidence=availability),'Missing is not all cash');calculated[name]=None;continue
            rows=original['daily'] if kind=='integer' else original['path'];exact([r['session'] for r in rows],dates,'Every original date')
            values=[Fraction(str(r['total_value_usd'])) if kind=='integer' else rational(r['normalized_value']) for r in rows]
            require(values[0]==(25000 if kind=='integer' else 1),'Initial value')
            require(saved['status']=='AVAILABLE','Available path');exact(saved['source_reference'],refs[name],'Per-track source')
            require(set(saved)=={'status','metrics','source_reference','stored_values_exact','value_encoding',('original_account_preserved' if kind=='integer' else 'original_track_preserved')},'Complete available track keys')
            require(saved['value_encoding']==('FRACTION_OF_STR_SAVED_FLOAT_NOT_ORIGINAL_ECONOMIC_EXACTNESS' if kind=='integer' else 'SAVED_EXACT_FRACTIONAL_REFERENCE_NOT_CASH_ACCOUNT'),'Saved value encoding boundary')
            exact(saved['original_account_preserved' if kind=='integer' else 'original_track_preserved'],original,'Entire original track retained')
            exact(saved['stored_values_exact'],[str(v) for v in values],'Original saved values')
            calculated[name]=inspect_metrics(saved['metrics'],values,dates);observations+=127
    modes=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];exact(c['mode_order'],modes,'Both original modes');require(c['modes_retained_separately'] is True and set(c['nav_modes'])==set(modes),'Both modes retained')
    differences={};cells=0
    require(set(c['absolute_distance_comparisons'])==set(modes),'Exact distance modes')
    for mode in modes:
        saved=c['nav_modes'][mode];original=nav['modes'][mode];exact(saved['original_mode_preserved'],original,'Full NAV mode');exact(saved['source_reference'],refs['nav_metrics'],'NAV pointer')
        exact([r['session'] for r in original['observations']],dates,'NAV complete dates')
        metrics=inspect_metrics(saved['metrics'],[Fraction(r['saved_value_exact']) for r in original['observations']],dates);observations+=127;differences[mode]={}
        for kind in ('integer','continuous'):
            require(set(c['absolute_distance_comparisons'][mode])=={'integer','continuous'} and set(c['absolute_distance_comparisons'][mode][kind])=={'annualized_return','maximum_drawdown'},'Exact distance grid')
            differences[mode][kind]={}
            for key in ('annualized_return','maximum_drawdown'):
                cell=c['absolute_distance_comparisons'][mode][kind][key];new=calculated['candidate_'+kind];old=calculated['incumbent_'+kind];od=abs(old[key]-metrics[key]);inspect_metric(cell['incumbent_absolute_distance'],od)
                require(set(cell)=={'candidate_absolute_distance','incumbent_absolute_distance','candidate_minus_incumbent_distance','status','formula'},'Exact distance cell')
                require(cell['formula']=='ABS(CANDIDATE-NAV)-ABS(INCUMBENT-NAV);NO_PASS_THRESHOLD_APPLIED','Absolute distance formula')
                if new is None:
                    require(cell['candidate_absolute_distance'] is None and cell['candidate_minus_incumbent_distance'] is None and cell['status']=='CANDIDATE_INTEGER_UNAVAILABLE','Missing distance stays null');delta=None
                else:
                    nd=abs(new[key]-metrics[key]);inspect_metric(cell['candidate_absolute_distance'],nd);inspect_metric(cell['candidate_minus_incumbent_distance'],nd-od);require(cell['status']=='BOTH_TRACKS_AVAILABLE_DIAGNOSTIC_ONLY','Diagnostic cell');delta=str(nd-od);cells+=1
                differences[mode][kind][key]=delta
    for flag in FALSE:require(c[flag] is False,'No formal promotion '+flag)
    require(c['evaluation_interval_previously_used_for_fitting'] is True,'Historical reuse flag')
    return dict(path_count=5 if missing else 6,observation_count=observations,available_distance_cell_count=cells,exact_distance_differences=differences)

def read(ref,sources):
    require(type(ref) is dict and set(ref)=={'path','sha256'},'Exact byte reference');p=ref['path'];b=Path(p).read_bytes();require(sha(b)==ref['sha256'],'External hash')
    require(p not in sources or sources[p]==ref['sha256'],'Source conflict');sources[p]=ref['sha256']
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)

def guard(sources):
    require(type(PRODUCER_SHA) is str and sha(PRODUCER.read_bytes())==PRODUCER_SHA,'Producer pending or changed')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')

def readback(task_id,publication_reference,*,execute=False):
    require(type(execute) is bool and execute and type(task_id) is str and len(task_id)==64 and all(x in '0123456789abcdef' for x in task_id) and task_id!=FIRST,'Explicit new task only')
    folder=BASE/task_id;require(Path(publication_reference['path'])==folder/'publication.json','Fixed publication path');require({p.name for p in folder.iterdir()}=={'started.json','comparison.json','publication.json'},'Published three files only')
    sources={str(SOURCE):LOADED};guard(sources);pub=read(publication_reference,sources);d=read(pub['comparison_reference'],sources)
    require(Path(pub['comparison_reference']['path'])==folder/'comparison.json','Fixed comparison path');require(d['schema']=='SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1' and d['numerical_task_id']==task_id,'Envelope schema and task')
    require(pub['schema']=='DATED_PER_TASK_ECONOMIC_COMPARISON_PUBLICATION_V1' and pub['status']=='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY','Successful publication')
    for obj in (d,pub):
        for flag in ('account_executed','fit_performed','old_audit_repeated','raw_prices_redecoded','point_in_time_verified','promotion_allowed','execution_authorized','winner_selected','formal_comparison_passed','formal_noninferiority_verified','cohort_statistics_computed','future_independent_oos','untouched_holdout','full_transitive_source_closure_reverified'):require(obj[flag] is False,'Envelope authority')
    exact(d['comparison_core_call_count'],1,'One comparison call');require(d['shared_account_reexecuted'] is False and d['shared_continuous_recomputed'] is False,'Shared controls only referenced')
    require(d['source_hashes'][str(PRODUCER)]==PRODUCER_SHA,'Original producer binding');exact(pub['source_hashes'],d['source_hashes'],'Publication sources')
    shared={}
    for role,(path,h) in SHARED.items():
        ref=dict(path=str(ROOT/path),sha256=h);exact(d['shared_references'][role],ref,'Fixed shared evidence');shared[role]=read(ref,sources)
    refs=d['input_references'];parents={k:read(v,sources) for k,v in refs.items()};ca=parents['account_audit'];xa=parents['continuous_audit']
    require(ca['schema']=='DATED_ACCOUNT_INDEPENDENT_READBACK_V1' and xa['schema']=='DATED_PER_TASK_CONTINUOUS_INDEPENDENT_READBACK_V1','Original audit schemas')
    for audit in (ca,xa):require(audit['status']=='PASS' and audit['numerical_task_id']==task_id,'Audited exact task')
    require(ca['reader_sha256']=='2e412e1dfe66d858656ed68c52ed5a2d976b84c8e7306612b4dc66b60ce0249a' and xa['reader_sha256']=='4a947e8c6f0d96ddae74bb87fc0a5a8dbb691865d550e543e5ecb9311b20e03a','Frozen independent audit readers')
    for audit in (ca,xa):
        for flag in ('point_in_time_verified','promotion_allowed','fit_performed'):require(audit[flag] is False,'Audit authority')
    exact(d['independent_audits_preserved'],dict(account_audit=ca,continuous_audit=xa),'Entire audit copies')
    exact(ca['shared_incumbent_audit_reference'],point_ref(d['shared_references']['account_audit'],'/rows/1'),'Original shared account audit')
    exact(ca['shared_incumbent_result_preserved'],shared['account_audit']['rows'][1],'Shared control identity')
    exact(xa['immutable_control_readback_reference'],d['shared_references']['continuous_audit'],'Original shared continuous audit')
    exact(ca['raw_reference'],refs['raw'],'Audited raw');exact(ca['postcheck_reference'],refs['postcheck'],'Audited postcheck');exact(xa['diagnostic_reference'],refs['continuous'],'Audited continuous');exact(xa['publication_reference'],refs['continuous_publication'],'Audited continuous receipt')
    for audit in (ca,xa):exact(audit['inputs_reference'],refs['inputs'],'Same input identity')
    require(parents['inputs']['inputs']['original_task']['numerical_task_id']==task_id,'Input task identity')
    inp=parents['inputs'];exact(d['original_task_preserved'],inp['inputs']['original_task'],'Original task preserved')
    for key,original in [('original_input_limitations',inp['inputs']['limitations']),('original_provenance_and_missing',inp['original_provenance_and_missing']),('preserved_evidence_sidecars',inp['preserved_evidence_sidecars'])]:exact(d[key],original,'Original evidence '+key)
    outcome=ca['attempt_outcome'];require(outcome in ('ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING','NOT_EXECUTED_NONPOSITIVE_TARGET'),'No technical failure interpreted as result')
    raw=parents['raw'];missing=outcome=='NOT_EXECUTED_NONPOSITIVE_TARGET';require((raw['account'] is None)==missing,'Account availability')
    require(parents['postcheck']['status']==outcome and parents['postcheck']['error'] is None and raw['error'] is None,'Preserved technical outcome')
    require(ca['accounting_verified'] is (not missing),'Independent accounting availability')
    for key in ('engine_call_attempt_count','returned_account_count'):exact(raw[key],0 if missing else 1,'Original call counts')
    expected_refs=dict(candidate_integer=None if missing else point_ref(refs['raw'],'/account'),incumbent_integer=point_ref(d['shared_references']['incumbent_account'],'/account'),candidate_continuous=point_ref(refs['continuous'],'/candidate'),incumbent_continuous=point_ref(d['shared_references']['continuous'],'/tracks/incumbent'),nav_metrics=point_ref(d['shared_references']['nav_metrics'],'/metrics'))
    availability=d['comparison']['candidate_integer_status_preserved']
    require(availability['status']==('NOT_EXECUTED_NONPOSITIVE_TARGET' if missing else 'AVAILABLE'),'Availability from audited outcome');exact(availability['evidence_reference'],point_ref(refs['account_audit'],'/attempt_outcome'),'Availability evidence')
    require((type(availability['reason']) is str and bool(availability['reason'].strip())) if missing else availability['reason'] is None,'Missing reason contract')
    counts=inspect(d['comparison'],dict(candidate=raw['account'],incumbent=shared['incumbent_account']['account']),dict(candidate=parents['continuous']['candidate'],incumbent=shared['continuous']['tracks']['incumbent']),shared['nav_metrics']['metrics'],expected_refs,availability)
    for p,h in d['source_hashes'].items():require(p not in sources or sources[p]==h,'Source conflict');sources[p]=h
    guard(sources);report=dict(schema='DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',numerical_task_id=task_id,comparison_reference=pub['comparison_reference'],publication_reference=publication_reference,source_hashes=sources,reader_sha256=LOADED,counts=counts,producer_called=False,fit_performed=False,account_executed=False,old_raw_audit_repeated=False,formal_comparison_passed=False,point_in_time_verified=False,promotion_allowed=False,future_independent_oos=False)
    require({p.name for p in folder.iterdir()}=={'started.json','comparison.json','publication.json'},'No concurrent readback')
    output=folder/'independent_readback.json';b=enc(report)
    with output.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    guard(sources);require(output.read_bytes()==b and {p.name for p in folder.iterdir()}=={'started.json','comparison.json','publication.json','independent_readback.json'},'Durable readback');return dict(path=str(output),sha256=sha(b))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task-id',required=True);p.add_argument('--publication-sha256',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    print(json.dumps(readback(a.task_id,dict(path=str(BASE/a.task_id/'publication.json'),sha256=a.publication_sha256),execute=a.execute)))
