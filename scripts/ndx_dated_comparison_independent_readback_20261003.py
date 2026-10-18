"""Independently read saved six paths and all distance cells; no producer calls."""
from decimal import Context,Decimal,localcontext
from fractions import Fraction
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research/dated_first_economic_comparison_20261003_v1'
REF=dict(path=str(BASE/'comparison.json'),sha256='a7ce43fec0c554c2b9376e233fa0bbdc7e0aa0d218e99f37727148c48183c323')
PUB=dict(path=str(BASE/'publication.json'),sha256='585c07d3700c3c1132768cd1a768c566cf4d537cb5b80c732df8e3ab55ae5aa1')
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def read(ref,sources):
    b=Path(ref['path']).read_bytes();require(sha(b)==ref['sha256'],'External bytes')
    require(ref['path'] not in sources or sources[ref['path']]==ref['sha256'],'Source conflict');sources[ref['path']]=ref['sha256'];return json.loads(b)
def ratio(r):return Fraction(int(r['numerator']),int(r['denominator']))
def check_metric(observed,value):
    with localcontext(Context(prec=80)):display=str(Decimal(value.numerator)/Decimal(value.denominator))
    exact(observed,dict(exact=str(value),decimal=display,unit='DIMENSIONLESS_RATIO_NOT_PERCENT'),'Exact metric plus display')
def verify_metrics(observed,values,dates):
    require(len(values)==127 and all(v>0 for v in values),'Full positive path')
    normalized=[v/values[0] for v in values]
    exact(observed['normalized_values_exact'],[str(v) for v in normalized],'Every normalized point')
    # Exhaustive ordered point pairs provide a separate drawdown oracle.
    dd=max(1-normalized[j]/normalized[i] for i in range(127) for j in range(i,127))
    peak=normalized[0];peak_index=0;worst=Fraction();pair=(0,0)
    for i,value in enumerate(normalized):
        if value>peak:peak=value;peak_index=i
        if 1-value/peak>worst:worst=1-value/peak;pair=(peak_index,i)
    require(worst==dd,'Independent all-pairs drawdown')
    result=dict(cumulative_return=normalized[-1]-1,annualized_return=normalized[-1]**2-1,maximum_drawdown=dd)
    for key,value in result.items():check_metric(observed[key],value)
    exact(observed['annualization'],dict(trading_days_per_year=252,return_interval_count=126,exponent_exact='2',formula='(LAST / FIRST) ** 2 - 1',historical_diagnostic_only=True),'Annualization definition')
    draw=observed['drawdown'];require(draw['first_observation_included_as_peak'] is True and type(draw['peak_index']) is int and type(draw['trough_index']) is int,'Exact drawdown metadata')
    require((draw['peak_index'],draw['trough_index'])==pair and draw['peak_session']==dates[pair[0]] and draw['trough_session']==dates[pair[1]],'Peak/trough locations')
    return result
def run():
    output=ROOT/'DYNAMIC_DATED_COMPARISON_INDEPENDENT_READBACK_20261003.json';require(not output.exists(),'Independent readback already saved')
    sources={str(SOURCE):LOADED};d=read(REF,sources);p=read(PUB,sources);c=d['comparison']
    exact(p['comparison_reference'],REF,'Publication payload');exact(p['source_hashes'],d['source_hashes'],'Publication sources')
    parents={}
    for role,r in d['input_references'].items():
        if role.endswith('_reader'):
            require(sha(Path(r['path']).read_bytes())==r['sha256'],'Saved audit reader source');sources[r['path']]=r['sha256']
        else:parents[role]=read(r,sources)
    for path,h in d['source_hashes'].items():require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift')
    dates=parents['nav_metrics']['metrics']['reference_calendar']['dates'];exact(c['calendar'],dates,'Same127 calendar')
    require(len(dates)==127 and dates[0]=='2026-03-20' and dates[-1]=='2026-09-21','Fixed interval')
    calculated={}
    for role in ('candidate','incumbent'):
        raw=parents[role+'_account'];daily=raw['account']['daily'];saved=c['tracks'][role+'_integer']
        exact([r['session'] for r in daily],dates,'Full integer date sequence')
        values=[Fraction(str(r['total_value_usd'])) for r in daily];require(values[0]==25000,'Initial capital')
        exact(saved['stored_values_exact'],[str(v) for v in values],'Original saved integer numbers')
        exact(c['saved_paths_preserved'][role],dict(integer_account=raw['account'],continuous_track=parents['continuous']['tracks'][role]),'Entire integer account and continuous track preserved')
        require(saved['rejections_or_all_cash_retained'] is True,'No rejected account omitted')
        calculated[role+'_integer']=verify_metrics(saved['metrics'],values,dates)
        path=parents['continuous']['tracks'][role]['path'];saved=c['tracks'][role+'_continuous']
        exact([r['session'] for r in path],dates,'Full continuous date sequence');values=[ratio(r['normalized_value']) for r in path]
        require(values[0]==1,'Continuous initial1');exact(saved['stored_values_exact'],[str(v) for v in values],'Original fractional values')
        calculated[role+'_continuous']=verify_metrics(saved['metrics'],values,dates)
    modes=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];exact(c['mode_order'],modes,'Both FX modes in original order')
    require(c['modes_retained_separately'] is True and set(c['nav_modes'])==set(modes),'No FX selection')
    differences={}
    for mode in modes:
        original=parents['nav_metrics']['metrics']['modes'][mode];exact(c['nav_modes'][mode]['original_mode'],original,'Complete NAV mode retained')
        rows=original['observations'];exact([r['session'] for r in rows],dates,'All NAV observation dates')
        values=[Fraction(r['saved_value_exact']) for r in rows]
        nav=verify_metrics(c['nav_modes'][mode]['metrics'],values,dates);differences[mode]={}
        for track in ('integer','continuous'):
            differences[mode][track]={}
            for metric in ('annualized_return','maximum_drawdown'):
                a=abs(calculated['candidate_'+track][metric]-nav[metric]);b=abs(calculated['incumbent_'+track][metric]-nav[metric]);cell=c['absolute_distance_comparisons'][mode][track][metric]
                check_metric(cell['candidate_absolute_distance'],a);check_metric(cell['incumbent_absolute_distance'],b);check_metric(cell['candidate_minus_incumbent_distance'],a-b)
                require(cell['formula']=='ABS(CANDIDATE-NAV)-ABS(INCUMBENT-NAV);NO_PASS_THRESHOLD_APPLIED','Distance formula')
                differences[mode][track][metric]=str(a-b)
    for key in ('formal_comparison_passed','formal_noninferiority_verified','winner_selected','cohort_statistics_computed','cohort_p50_computed','cohort_p10_computed','cohort_p90_computed','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','subscription_redemption_execution_required_for_reference_metrics'):require(c[key] is False,'No formal authority')
    require(c['status']=='SINGLE_PATH_DIAGNOSTIC_ONLY','Single path scope')
    value=dict(schema='DATED_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',comparison_reference=REF,publication_reference=PUB,reader_sha256=LOADED,source_hashes=sources,path_count=6,observation_count=762,distance_cell_count=8,exact_distance_differences=differences,producer_called=False,account_executed=False,fit_performed=False,old_raw_audit_repeated=False,formal_comparison_passed=False,winner_selected=False,point_in_time_verified=False,promotion_allowed=False,future_independent_oos=False)
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Final source drift')
    blob=encoded(value)
    with output.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(output.read_bytes()==blob,'Durable result');return dict(path=str(output),sha256=sha(blob))
if __name__=='__main__':print(json.dumps(run()))
