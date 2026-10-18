"""Independent one-artifact scoped capture readback; no producer imports or writes."""
import base64
import csv
from datetime import datetime, time, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'data/cache/research/forward_source_capture_scoped_20261002_v1'
CAPTURE_SHA = '25fa0d8664c51945384fb6a2e720b86d66965ddeff31ed005b0cd9a74d0dff1c'
PUBLICATION_SHA = '29e0423c6ef7241fd27fb60def7d7ef8bb67680505fd097660a499ea72678537'
FIELDS = ['Date','Open','High','Low','Close','Volume']


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
    rows = list(reader); previous = ''; included=[]; excluded=[]; diagnostics=[]; normalized={}
    for index,row in enumerate(rows):
        day=row['Date']; parsed=datetime.strptime(day,'%Y-%m-%d').date()
        require(parsed.isoformat() == day and parsed.weekday()<5 and day>previous, 'Original date order')
        previous=day; require(set(row)==set(FIELDS), 'Original fields')
        numbers={key:Decimal(row[key]) for key in FIELDS[1:]}
        require(all(number.is_finite() and (number>=0 if key=='Volume' else number>0) for key,number in numbers.items()),'Invalid number')
        violations=[]
        for left,relation,right,name in [('Low','>','Open','LOW_EXCEEDS_OPEN'),('Low','>','Close','LOW_EXCEEDS_CLOSE'),
            ('High','<','Open','HIGH_BELOW_OPEN'),('High','<','Close','HIGH_BELOW_CLOSE'),('Low','>','High','LOW_EXCEEDS_HIGH')]:
            if numbers[left]>numbers[right] if relation=='>' else numbers[left]<numbers[right]: violations.append(name)
        in_scope=day>=scope
        require(not in_scope or not violations,'Required scope invalid OHLC')
        require(evidence['original_rows'][index] == {'original_data_row_index':index,'session':day,
            'raw_csv_row':row,'included_in_scoped_csv':in_scope}, 'Original row/index evidence differs')
        (included if in_scope else excluded).append(index)
        if violations: diagnostics.append({'original_data_row_index':index,'session':day,'raw_csv_row':row,
            'violations':violations,'role':'OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE'})
        if in_scope:
            converted={'Date':day,**{key:decimal_text(number) for key,number in numbers.items()}}
            normalized[day]={'normalized_ohlcv':converted,'normalized_row_sha256':sha(canonical(converted)),'raw_csv_row':row}
    require(list(normalized)==expected_dates,'Exact 65 accounted rows required')
    require(evidence['original_row_count']==len(rows)==len(evidence['original_rows']),'Row count differs')
    require(evidence['included_original_row_indexes']==included and evidence['excluded_original_row_indexes']==excluded,'Index partition differs')
    require(evidence['excluded_before_scope_ohlc_diagnostics']==diagnostics,'Old anomaly diagnostics differ')
    buffer=io.StringIO(newline=''); writer=csv.DictWriter(buffer,fieldnames=FIELDS,lineterminator='\n')
    writer.writeheader(); writer.writerows(rows[index] for index in included)
    derived=buffer.getvalue().encode()
    require(evidence['scoped_csv_utf8'].encode()==derived,'Derived CSV content differs')
    require(evidence['original_sha256']==sha(original) and evidence['original_byte_count']==len(original),'Full bytes hash/count')
    require(evidence['scoped_sha256']==sha(derived) and evidence['scoped_byte_count']==len(derived),'Derived bytes hash/count')
    return normalized, diagnostics, len(rows), sha(derived)


def run():
    capture_raw=(DIRECTORY/'capture.json').read_bytes(); publication_raw=(DIRECTORY/'publication.json').read_bytes()
    require(sha(capture_raw)==CAPTURE_SHA and sha(publication_raw)==PUBLICATION_SHA,'Hard artifact hash mismatch')
    capture=json.loads(capture_raw); publication=json.loads(publication_raw)
    require(capture['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1' and publication['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PUBLICATION_V1','Schema mismatch')
    require(publication['status']=='PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND' and
        publication['capture_reference']=={'path':str(DIRECTORY/'capture.json'),'sha256':CAPTURE_SHA},'Publication reference')
    sources=capture['source_hashes']; require(len(sources)==10 and publication['source_hashes']==sources,'Ten direct sources required')
    def guard():
        for path,digest in sources.items(): require(sha(Path(path).read_bytes())==digest,'Direct source drift: '+path)
    guard()
    require({path.name for path in DIRECTORY.iterdir()}=={'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'},'Capture namespace')
    started=json.loads((DIRECTORY/'started.json').read_bytes())
    require(started['source_hashes']==sources and started['retry_allowed'] is False,'Started linkage')
    for key in ('capture_started_at_utc','observed_at_utc'): require(started[key]==capture[key],'Clock receipt differs')
    begin=datetime.fromisoformat(capture['capture_started_at_utc']); end=datetime.fromisoformat(capture['observed_at_utc'])
    require(begin<=end and begin.utcoffset().total_seconds()==end.utcoffset().total_seconds()==0,'UTC interval')
    require(capture['capture_started_at_utc']=='2026-10-02T15:21:18.150706+00:00' and
            capture['observed_at_utc']=='2026-10-02T15:21:18.150888+00:00','Exact capture interval')
    refs=capture['input_references']; frontier=json.loads(read_ref(refs['frontier']))
    dates=[row['session'] for row in frontier['known_accounted_rows']]
    require(len(dates)==65 and dates[0]=='2026-07-01' and dates[-1]=='2026-10-01','Frontier dates')
    plan=capture['plan']; inner=plan['capture_plan']
    require(plan['schema']=='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1' and plan['scope_start']==dates[0],'Scope schema')
    normalized={}; details={}
    for role in ('source','baseline'):
        normalized[role]={}; details[role]={}
        for ticker in ('QQQ','SPY'):
            original=read_ref(capture['captured_artifacts'][ticker]) if role=='source' else read_ref(refs['baseline_'+ticker])
            evidence=plan['csv_scope_evidence'][role][ticker]
            values, diagnostics, count, digest=check_csv(original,evidence,dates[0],dates)
            normalized[role][ticker]=values
            require(plan['original_'+role+'_sha256'][ticker]==sha(original),'Outer original hash')
            require(plan['scoped_'+role+'_sha256'][ticker]==digest==inner[role+'_sha256'][ticker],'Derived/consumed hash')
            if role=='source': require(inner['source_rows'][ticker]==values,'Independent normalized row hashes differ')
            details[role][ticker]={'original_row_count':count,'scoped_row_count':len(values),
                'old_anomaly_dates':[item['session'] for item in diagnostics], 'original_sha256':sha(original),'scoped_sha256':digest}
    require(normalized['source']==normalized['baseline'] and inner['revisions']==[],'Revision diagnostic differs')
    require(all(details[role]['SPY']['old_anomaly_dates']==['2015-03-30'] and details[role]['QQQ']['old_anomaly_dates']==[] for role in details),'Expected isolated old anomaly')
    tz=read_ref(capture['captured_artifacts']['tzif'])
    require(tz==read_ref(refs['tzif']) and inner['tzif_sha256']==sha(tz)==capture['timezone_resource_metadata']['bytes_sha256'],'TZif copied bytes')
    zone=ZoneInfo.from_file(io.BytesIO(tz))
    last_close=datetime.combine(datetime.strptime(dates[-1],'%Y-%m-%d').date(),time(16),zone).astimezone(timezone.utc)
    require(begin>=last_close,'Read began before accounted close')
    require(inner['status']=='NO_NEW_SOURCE_SESSION' and inner['new_source_dates']==[] and inner['classifications']==[]
        and inner['excluded_unfinished_source_dates']==[] and inner['timeliness_candidate'] is None,'No-new-source classification differs')
    require(inner['accounted_prefix_dates']==dates and inner['unmatched_new_source_dates_by_ticker']=={'QQQ':[],'SPY':[]},'Source coverage differs')
    require(inner['last_observed_session_unchanged']=='2026-09-24' and inner['last_accounted_session_unchanged']=='2026-10-01','Two cursors differ')
    for value in (capture,publication,plan,inner):
        for key in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed'):
            require(value[key] is False,'Authority changed')
    failed=ROOT/'data/cache/research/forward_source_capture_20261002_v1'
    retained={p.name:sha(p.read_bytes()) for p in failed.iterdir()}
    require(set(retained)=={'started.json','failure.json','QQQ.csv','SPY.csv','New_York.tzif'},'Original failed namespace altered')
    require(json.loads((failed/'failure.json').read_bytes())=={'error':'OHLC bounds violated','retry_allowed':False,'status':'FAILED_DO_NOT_CONSUME'},'Original failure evidence differs')
    guard()
    require(retained=={p.name:sha(p.read_bytes()) for p in failed.iterdir()},'Failed namespace changed during readback')
    return {'status':'PASSED_INDEPENDENT_SCOPED_CAPTURE_READBACK','capture_sha256':CAPTURE_SHA,
        'publication_sha256':PUBLICATION_SHA,'direct_source_count':len(sources),'details':details,
        'capture_started_at_utc':capture['capture_started_at_utc'],'observed_at_utc':capture['observed_at_utc'],
        'tzif_sha256':sha(tz),'status_observed':inner['status'],'candidate':None,'revision_count':0,
        'retained_failed_namespace_hashes':retained,'producer_or_old_audit_called':False,
        'full_transitive_source_closure_reverified':False,'oos_recovery_completed':False}


if __name__=='__main__': print(json.dumps(run(),indent=2))
