"""New saved scoped-capture oracle; never reads live quote caches or calls producers."""
import argparse,base64,csv,hashlib,io,json,os
from copy import deepcopy
from datetime import datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
DIRECTORY=ROOT/'data/cache/research/forward_source_capture_scoped_20261003_v1'
OUTPUT=ROOT/'data/cache/research/forward_source_capture_scoped_independent_readback_20261003_v1'
CAPTURE_SHA='dd90524b2da28280b2b3742a3898e99ab3492b476cefc629ac6acba392fc0792'
PUBLICATION_SHA='158151e2905b3bcb45894afc8300bcd4447378908cc4e9ec3482668a97c9c27a'
PRODUCER=ROOT/'scripts/ndx_forward_source_capture_scoped_20261003.py'
PRODUCER_SHA='ce5a0aef308a6864162025a259cdf90ee1d5891b83e3472e4962834c4103928f'
FIELDS=['Date','Open','High','Low','Close','Volume']
FALSE=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','decision_eligible','canonical_calendar_append_allowed','source_price_execution_verified','exchange_holidays_verified','early_closes_verified','authentic_clock_verified','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','historical_first_observation_claimed','fresh_observation'),False)

def exact(a,b,message):require(canonical(a)==canonical(b),message)
def require(ok, message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decimal_text(value):
    if value == 0: return '0'
    text = format(value,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def read_ref(ref):
    raw = Path(ref['path']).read_bytes()
    require(sha(raw) == ref['sha256'], 'Reference bytes changed: '+ref['path'])
    return raw


def check_csv(original, evidence, scope, expected_dates):
    require(base64.b64decode(evidence['original_csv_bytes_base64'], validate=True) == original, 'Original base64 differs')
    reader = csv.DictReader(io.StringIO(original.decode('utf-8-sig'),newline=''))
    require(reader.fieldnames == FIELDS, 'CSV header differs')
    require(type(original) is bytes and 0<len(original)<=8000000,'Bounded original bytes')
    rows = list(reader);require(0<len(rows)<=20000,'Bounded rows'); previous = ''; included=[]; excluded=[]; diagnostics=[]; normalized={}
    for index,row in enumerate(rows):
        day=row['Date']; parsed=datetime.strptime(day,'%Y-%m-%d').date()
        require(parsed.isoformat() == day and parsed.weekday()<5 and day>previous, 'Original date order')
        previous=day; require(set(row)==set(FIELDS), 'Original fields')
        require(all(type(v) is str and v and v.strip()==v for v in row.values()),'Exact nonempty fields')
        require(all(len(row[k])<=100 for k in FIELDS[1:]),'Numeric text bound')
        numbers={key:Decimal(row[key]) for key in FIELDS[1:]}
        require(all(n.is_finite() and len(n.as_tuple().digits)<=50 and -50<=n.as_tuple().exponent<=50 for n in numbers.values()),'Finite bounded decimals')
        require(all(number.is_finite() and (number>=0 if key=='Volume' else number>0) for key,number in numbers.items()),'Invalid number')
        violations=[]
        for left,relation,right,name in [('Low','>','Open','LOW_EXCEEDS_OPEN'),('Low','>','Close','LOW_EXCEEDS_CLOSE'),
            ('High','<','Open','HIGH_BELOW_OPEN'),('High','<','Close','HIGH_BELOW_CLOSE'),('Low','>','High','LOW_EXCEEDS_HIGH')]:
            if numbers[left]>numbers[right] if relation=='>' else numbers[left]<numbers[right]: violations.append(name)
        in_scope=day>=scope
        require(not in_scope or not violations,'Required scope invalid OHLC')
        exact(evidence['original_rows'][index], {'original_data_row_index':index,'session':day,
            'raw_csv_row':row,'included_in_scoped_csv':in_scope}, 'Original row/index evidence differs')
        (included if in_scope else excluded).append(index)
        if violations: diagnostics.append({'original_data_row_index':index,'session':day,'raw_csv_row':row,
            'violations':violations,'role':'OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE'})
        if in_scope:
            converted={'Date':day,**{key:decimal_text(number) for key,number in numbers.items()}}
            normalized[day]={'normalized_ohlcv':converted,'normalized_row_sha256':sha(canonical(converted)),'raw_csv_row':row}
    require(list(normalized)[:len(expected_dates)]==expected_dates,'Every ticker exact accounted prefix')
    require(evidence['original_row_count']==len(rows)==len(evidence['original_rows']),'Row count differs')
    exact(evidence['included_original_row_indexes'],included,'Included indexes');exact(evidence['excluded_original_row_indexes'],excluded,'Excluded indexes')
    exact(evidence['excluded_before_scope_ohlc_diagnostics'],diagnostics,'Old anomaly diagnostics differ')
    buffer=io.StringIO(newline=''); writer=csv.DictWriter(buffer,fieldnames=FIELDS,lineterminator='\n')
    writer.writeheader(); writer.writerows(rows[index] for index in included)
    derived=buffer.getvalue().encode()
    require(evidence['scoped_csv_utf8'].encode()==derived,'Derived CSV content differs')
    require(evidence['original_sha256']==sha(original) and evidence['original_byte_count']==len(original),'Full bytes hash/count')
    require(evidence['scoped_sha256']==sha(derived) and evidence['scoped_byte_count']==len(derived),'Derived bytes hash/count')
    for key,value in [('original_row_count',len(rows)),('original_byte_count',len(original)),('scoped_byte_count',len(derived))]:require(type(evidence[key]) is int and evidence[key]==value,'Exact integer count')
    return normalized, diagnostics, len(rows), sha(derived)



RECEIPT_FALSE=('old_calendar_mutated','old_calendar_full_validation_reexecuted','gap_ledger_validation_reexecuted','classifier_reexecuted','candidate_generator_called','candidate_seal_allowed','cohort_registration_allowed','canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','network_quote_refresh_performed','oos_recovery_completed','full_transitive_source_closure_reverified')

def validate_saved_frontier(frontier,receipt,refs):
    require(frontier['schema']=='OBSERVATION_GAP_FRONTIER_RESEARCH_V1' and receipt['schema']=='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1','Parent schemas')
    require(receipt['status']=='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY','Parent publication status')
    exact(receipt['frontier_reference'],refs['frontier'],'Parent receipt reference');exact(receipt['source_hashes'],frontier['source_hashes'],'Parent source claims')
    require(frontier['last_observed_session']=='2026-09-24' and frontier['last_accounted_session']==frontier['last_accounted_gap_session']=='2026-10-01','Distinct parent cursors')
    exact(frontier['unaccounted_source_dates'],[],'No pending parent dates')
    for key in ('candidate_seal_allowed','cohort_registration_allowed','canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed','oos_recovery_completed'):
        require(frontier[key] is False and receipt[key] is False,'Parent authority')
    for ticker in ('QQQ','SPY'):exact(frontier['input_references'][ticker],refs['baseline_'+ticker],'Baseline bound to parent')
    rows=frontier['known_accounted_rows'];require(type(rows) is list and len(rows)==65,'Full parent rows')
    dates=[r['session'] for r in rows];require(dates==sorted(set(dates)) and dates[0]=='2026-07-01' and dates[59]=='2026-09-24' and dates[-1]=='2026-10-01','Full parent date sequence')
    for i,row in enumerate(rows):
        day=datetime.strptime(row['session'],'%Y-%m-%d').date();require(day.isoformat()==row['session'] and day.weekday()<5,'Canonical parent dates')
        if i<60:exact(row,dict(session=row['session'],kind='SEALED_PARENT_OBSERVED_SESSION',parent_session_index=i,eligibility_reverified=False),'Observed original row')
        else:
            h=row['gap_event_sha256'];require(type(h) is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'Gap hash')
            exact(row,dict(session=row['session'],kind='MISSED_OBSERVATION',gap_event_index=i-60,gap_event_sha256=h,counts_as_observed_session=False,decision_eligible=False),'Gap original row')
    for key,n in [('parent_observed_session_count',60),('accounted_gap_count',5)]:require(type(frontier[key]) is int and frontier[key]==n,'Parent counts')


def inspect_plan(plan,frontier,current,baseline,tzif,started,observed):
    require(plan['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1','Scoped plan schema')
    dates=[r['session'] for r in frontier['known_accounted_rows']];require(dates and dates==sorted(set(dates)),'Complete ordered prefix');require(plan['scope_start']==dates[0],'Scope is sealed frontier start')
    require(plan['frozen_capture_source_sha256']=='30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642','Frozen planning source')
    inner=plan['capture_plan'];require(inner['schema']=='FORWARD_SOURCE_CAPTURE_PLANNING_V1','Inner planning schema')
    begin=datetime.fromisoformat(started);end=datetime.fromisoformat(observed)
    require(begin.tzinfo is not None and end.tzinfo is not None and begin.utcoffset()==end.utcoffset()==timedelta(0) and begin<=end,'Full ordered UTC reading interval')
    require(inner['capture_started_at_utc']==started and inner['observed_at_utc']==observed,'Clock evidence linkage')
    zone=ZoneInfo.from_file(io.BytesIO(tzif))
    def timing(day):
        d=datetime.strptime(day,'%Y-%m-%d').date();following=d+timedelta(days=1)
        while following.weekday()>=5:following+=timedelta(days=1)
        return datetime.combine(d,time(16),zone).astimezone(timezone.utc),datetime.combine(following,time(9,30),zone).astimezone(timezone.utc)
    require(begin>=timing(dates[-1])[0],'Capture cannot precede accounted close')
    require(inner['tzif_sha256']==sha(tzif),'Actual TZif bytes')
    maps={};details={}
    for role,mapping in [('source',current),('baseline',baseline)]:
        require(set(mapping)=={'QQQ','SPY'},'Two tickers in each group');maps[role]={};details[role]={}
        for ticker,raw in mapping.items():
            ev=plan['csv_scope_evidence'][role][ticker];values,diag,count,digest=check_csv(raw,ev,dates[0],dates)
            require(ev['scope_start']==dates[0] and ev['scope_selection']=='SESSION_GREATER_OR_EQUAL_SEALED_FRONTIER_FIRST_SESSION_NOT_PRICE_SELECTED','Scope provenance')
            require(plan['original_'+role+'_sha256'][ticker]==sha(raw),'Full raw hash');require(plan['scoped_'+role+'_sha256'][ticker]==digest==inner[role+'_sha256'][ticker],'Derived versus original hashes')
            maps[role][ticker]=values;details[role][ticker]=dict(original_row_count=count,scoped_row_count=len(values),out_of_scope_ohlc_diagnostics=diag,original_sha256=sha(raw),derived_sha256=digest)
    exact(inner['source_rows'],maps['source'],'Every original/normalized source row')
    revisions=[]
    for ticker in ('QQQ','SPY'):
        for day in dates:
            before=maps['baseline'][ticker][day];after=maps['source'][ticker][day]
            if before['normalized_row_sha256']!=after['normalized_row_sha256']:revisions.append(dict(ticker=ticker,session=day,baseline_evidence=before,current_evidence=after,role='DIAGNOSTIC_ONLY_NEVER_REWRITE_ACCOUNTED_EVIDENCE'))
    exact(inner['revisions'],revisions,'Complete revision diagnostics')
    unmatched={t:sorted(d for d in maps['source'][t] if d>dates[-1] and d not in maps['source'][other]) for t,other in [('QQQ','SPY'),('SPY','QQQ')]};asymmetric=any(unmatched.values())
    common=sorted(set(maps['source']['QQQ'])&set(maps['source']['SPY']));require(common[:len(dates)]==dates,'Common prefix preserved')
    new=common[len(dates):];complete=[d for d in new if timing(d)[0]<=begin];excluded=[d for d in new if d not in complete];classifications=[];candidate=None
    for i,day in enumerate(complete):
        close,deadline=timing(day)
        status='MISSED_EARLIER_COMPLETED_SOURCE_SESSION' if i<len(complete)-1 else 'SOURCE_SUFFIX_ASYMMETRY_REQUIRES_REVIEW' if asymmetric else 'TIMELINESS_REVIEW_CANDIDATE_ONLY' if end<deadline else 'MISSED_SEAL_DEADLINE'
        row=dict(session=day,classification=status,conservative_close_utc=close.isoformat(),conservative_next_weekday_open_utc=deadline.isoformat(),capture_started_at_utc=started,observed_at_utc=observed,**FALSE);classifications.append(row)
        if status=='TIMELINESS_REVIEW_CANDIDATE_ONLY':candidate=deepcopy(row)
    expected_status='SOURCE_SUFFIX_ASYMMETRY_REQUIRES_REVIEW' if asymmetric else 'NO_NEW_SOURCE_SESSION' if not new else 'NEW_SOURCE_DATES_REQUIRE_REVIEW'
    require(inner['status']==expected_status,'Current capture status');exact(inner['new_source_dates'],new,'All new common dates');exact(inner['excluded_unfinished_source_dates'],excluded,'Start-time unfinished rows');exact(inner['classifications'],classifications,'Whole-interval timeliness classification');exact(inner['timeliness_candidate'],candidate,'Candidate is not observed/sealed')
    exact(inner['unmatched_new_source_dates_by_ticker'],unmatched,'Unmatched suffix retained');require(inner['source_suffix_asymmetry_blocks_timeliness_candidate'] is asymmetric,'Suffix authority')
    exact(inner['accounted_prefix_dates'],dates,'Full prefix');require(inner['last_observed_session_unchanged']==frontier['last_observed_session'] and inner['last_accounted_session_unchanged']==frontier['last_accounted_session'],'Distinct cursors')
    require(inner['month_first_semantics']==frontier['month_first_semantics']=='UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE','Capture does not grant monthly eligibility')
    for key in FALSE:require(inner[key] is False,'Inner authority')
    for key in ('candidate_seal_allowed','cohort_registration_allowed','decision_eligible','point_in_time_verified','promotion_allowed','fresh_observation','oos_recovery_completed','frozen_capture_consumed_full_original_csv','out_of_scope_ohlc_anomalies_repaired','old_failed_namespace_modified','scope_chosen_from_prices','source_bytes_authenticated_by_this_module','original_calendar_reverified','source_price_execution_verified','historical_first_observation_claimed','canonical_calendar_append_allowed','live_mutation_allowed'):require(plan[key] is False,'Scoped authority')
    require(plan['full_original_bytes_preserved'] is True,'Original full bytes preserved')
    return dict(details=details,status_observed=expected_status,candidate=deepcopy(candidate),new_source_dates=new,revision_count=len(revisions),tzif_sha256=sha(tzif),capture_started_at_utc=started,observed_at_utc=observed,accounted_prefix_count=len(dates),**FALSE)

def readback(*,execute=False):
    require(type(execute) is bool and execute,'Explicit execution required');require(type(CAPTURE_SHA) is str and type(PUBLICATION_SHA) is str,'Future capture anchors pending');require(not OUTPUT.exists(),'Immutable independent namespace')
    sources={str(SOURCE):LOADED_SHA,str(PRODUCER):PRODUCER_SHA}
    def read(r):
        raw=read_ref(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Conflicting bytes');sources[r['path']]=r['sha256'];return raw
    capture_ref=dict(path=str(DIRECTORY/'capture.json'),sha256=CAPTURE_SHA);pub_ref=dict(path=str(DIRECTORY/'publication.json'),sha256=PUBLICATION_SHA)
    c=json.loads(read(capture_ref));p=json.loads(read(pub_ref));require(c['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1' and p['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PUBLICATION_V1','Capture receipt schema');exact(p['capture_reference'],capture_ref,'Receipt capture');require(p['status']=='PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND','Successful capture')
    require({x.name for x in DIRECTORY.iterdir()}=={'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'},'Successful unique capture')
    exact(c['source_hashes'],p['source_hashes'],'Original capture direct source map');require(len(c['source_hashes'])==10,'Ten original direct source claims')
    refs=c['input_references'];require(set(refs)=={'frontier','frontier_publication','baseline_QQQ','baseline_SPY','tzif','base_core','core','current_QQQ','current_SPY'},'Fixed source roles')
    # Never open current_QQQ/current_SPY: their captured copies carry the original bytes.
    parents={}
    for role,r in refs.items():
        if role.startswith('current_'):continue
        raw=read(r)
        if role in ('frontier','frontier_publication'):parents[role]=json.loads(raw)
        else:parents[role]=raw
    expected_sources={str(PRODUCER):PRODUCER_SHA,**{r['path']:r['sha256'] for r in refs.values()}};exact(c['source_hashes'],expected_sources,'Every direct claim bound')
    frontier=parents['frontier'];receipt=parents['frontier_publication'];exact(receipt['frontier_reference'],refs['frontier'],'Prior frontier receipt');exact(receipt['source_hashes'],frontier['source_hashes'],'Prior frontier source map')
    validate_saved_frontier(frontier,receipt,refs)
    dates=[r['session'] for r in frontier['known_accounted_rows']];require(len(dates)==65 and dates[0]=='2026-07-01' and dates[-1]=='2026-10-01' and frontier['last_observed_session']=='2026-09-24','Fixed old observed/gap prefix')
    require(type(frontier['parent_observed_session_count']) is int and frontier['parent_observed_session_count']==60 and type(frontier['accounted_gap_count']) is int and frontier['accounted_gap_count']==5,'Observed and gap counts distinct')
    for ticker in ('QQQ','SPY'):require(Path(refs['current_'+ticker]['path'])==ROOT/'data/cache'/(ticker+'.csv'),'Original live path claim')
    current={}
    for ticker in ('QQQ','SPY'):
        r=c['captured_artifacts'][ticker];require(Path(r['path'])==DIRECTORY/(ticker+'.csv'),'Fixed copied CSV');current[ticker]=read(r);require(sha(current[ticker])==refs['current_'+ticker]['sha256'],'Original live hash claim matches immutable copy')
    tr=c['captured_artifacts']['tzif'];require(Path(tr['path'])==DIRECTORY/'New_York.tzif','Fixed TZif copy');tz=read(tr);require(tz==parents['tzif'] and c['timezone_resource_metadata']['bytes_sha256']==sha(tz),'Actual saved timezone')
    sr=dict(path=str(DIRECTORY/'started.json'),sha256=sha((DIRECTORY/'started.json').read_bytes()));started=json.loads(read(sr));exact(started['source_hashes'],c['source_hashes'],'Started source claims');require(started['retry_allowed'] is False,'No retry')
    for k in ('capture_started_at_utc','observed_at_utc'):require(started[k]==c[k],'Original reader clock interval')
    for obj in (c,p):
        for k in RECEIPT_FALSE:require(obj[k] is False,'No receipt authority')
    require(c['external_clock_attestation_verified'] is False and c['timezone_resource_metadata']['current_exchange_rules_certified'] is False,'No clock/exchange certification')
    require(c['clock_captured_by_runner'] is True and c['quote_source_type']=='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH','Original capture scope')
    result=inspect_plan(c['plan'],frontier,current,{t:parents['baseline_'+t] for t in ('QQQ','SPY')},tz,c['capture_started_at_utc'],c['observed_at_utc'])
    def guard():
        for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Immutable evidence changed')
    guard();report=dict(schema='SCOPED_FORWARD_CAPTURE_INDEPENDENT_READBACK_V1',status='PASS',capture_reference=capture_ref,publication_reference=pub_ref,reader_sha256=LOADED_SHA,source_hashes=sources,capture_original_source_hashes_preserved=c['source_hashes'],current_live_cache_reopened=False,original_capture_interval_is_receipt_not_external_clock_attestation=True,producer_called=False,old_audit_called=False,observed_session_registered=False,full_transitive_source_closure_reverified=False,**result)
    OUTPUT.mkdir(parents=True,exist_ok=False);path=OUTPUT/'independent_readback.json';blob=canonical(report)
    try:
        with path.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
        guard();require(path.read_bytes()==blob and {x.name for x in OUTPUT.iterdir()}=={'independent_readback.json'},'Independent output bytes')
    except Exception as e:
        with (OUTPUT/'failure.json').open('xb') as f:f.write(canonical(dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False)));f.flush();os.fsync(f.fileno())
        raise
    return dict(path=str(path),sha256=sha(blob))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
