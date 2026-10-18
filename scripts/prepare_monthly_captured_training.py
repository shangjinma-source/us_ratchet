"""Advance saved conditional training to a captured session; never run research."""
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse,json
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_monthly_training import _daily,compile_saved_training
from data.current_quantity_v2_monthly_bounded_review import _json
from scripts.monthly_full_domain_capture import prepare as validate_capture_plan
from scripts.current_research_close_capture import utc_now
from data.current_research_saved_quote import read_saved_quote


def build(*,root,previous_manifest_path,previous_manifest_sha256,capture_index_path,capture_index_sha256,plan_path,plan_sha256,clock=utc_now,plan_validator=validate_capture_plan):
    root=Path(root).resolve();files={};pins={}
    def pin(path,expected=None):
        p=Path(path);require(not p.is_absolute() and '..' not in p.parts and p.as_posix()==path,'INVALID_SOURCE_PATH')
        resolved=(root/p).resolve();require(resolved.is_relative_to(root),'SOURCE_ESCAPES_ROOT')
        require(resolved.stat().st_size<=32*1024*1024,'SOURCE_TOO_LARGE');raw=resolved.read_bytes();h=sha256(raw).hexdigest()
        require(expected is None or h==expected,'SOURCE_CHANGED:'+path);require(path not in pins or pins[path]==h,'SOURCE_CONFLICT')
        files[path]=raw;pins[path]=h;require(sum(map(len,files.values()))<=128*1024*1024,'SOURCE_PACKAGE_TOO_LARGE');return raw
    old=json.loads(pin(previous_manifest_path,previous_manifest_sha256));index=json.loads(pin(capture_index_path,capture_index_sha256))
    # Only trusted Python composition can supply an experimental-domain validator;
    # the CLI request schema does not expose callbacks or import names.
    require(callable(plan_validator),'CAPTURE_PLAN_VALIDATOR_REQUIRED')
    plan,preflight=plan_validator(plan_path,plan_sha256,root=root,clock=clock);pin(plan_path,plan_sha256)
    require(preflight['ready_after_close'],'SESSION_NOT_CLOSED');now=stamp(clock())
    for source in (old['source_hashes'],plan['membership_source_hashes'],plan['calendar_source_hashes']):
        for p,h in source.items():pin(p,h)
    require(index['plan_sha256']==plan_sha256 and index['session']==plan['session'],'CAPTURE_PLAN_MISMATCH')
    entries=index['entries'];rows={r['ticker']:r for r in old['candidates']}
    require(len(entries)==len(rows)==len(old['members']) and {e['ticker'] for e in entries}==set(rows)
        and {s['ticker'] for s in plan['securities']}==set(rows),'FULL_DOMAIN_MISMATCH')
    indexed={}
    for b in index['batches']:
        child=json.loads(pin(b['path'],b['sha256']))
        require(child['session']==index['session'],'BATCH_SESSION_MISMATCH')
        for entry in child['entries']:
            require(entry['ticker'] not in indexed,'DUPLICATE_CHILD_ENTRY');indexed[entry['ticker']]=entry
    for e in entries:
        child=indexed.get(e['ticker']) if e['security_id'] is not None else json.loads(pin(e['relative_directory']+'/completion_index.json'))
        require(child=={k:v for k,v in e.items() if k!='relative_directory'},'CAPTURE_CHILD_INDEX_MISMATCH')
    calendar=json.loads(files[plan['calendar_path']]);day=plan['session']
    require(day>old['decision_date'],'NEW_DECISION_SESSION_REQUIRED')
    extension=[d for d in calendar['calendar'] if old['decision_date']<d<=day]
    require(extension and extension[-1]==day,'SESSION_EXTENSION_MISSING')
    days=(old['training_dates']+extension)[-253:];require(len(days)==253 and days==sorted(set(days)),'INVALID_253_SESSION_CALENDAR')
    closing=stamp(next(s['close_at'] for s in calendar['sessions'] if s['date']==day))
    result=deepcopy(old);result.update(decision_date=day,training_dates=days,membership_observation_asof=old.get('membership_observation_asof',old['decision_date']),
        calendar_basis='PINNED_PRIOR_253_WINDOW_PLUS_PINNED_SCHEDULED_SESSION_EXTENSION',full_pit_verified=False,complete_corporate_actions_verified=False)
    coverage=[];captured=[]
    for e in entries:
        ticker=e['ticker'];r=rows[ticker];directory=e['relative_directory'];rp=directory+'/'+ticker+'.receipt.json';rawpath=directory+'/'+ticker+'.response.bin'
        receipt=json.loads(pin(rp,e['receipt_sha256']));raw=pin(rawpath,e['raw_sha256'])
        pin(directory+'/'+ticker+'.decoded.json',e['decoded_sha256'])
        require(e['status']==('TRANSPORT_SAVED_UNRESOLVED_NOT_ADMITTED' if e['security_id'] is None else 'SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED'),'CAPTURE_ENTRY_NOT_VALIDATED')
        read_saved_quote(root=root,ticker=ticker,expected_security_type='EQUITY',entry=e,relative_directory=directory,decision_date=day,decision_session_close_at=next(s['close_at'] for s in calendar['sessions'] if s['date']==day))
        require(receipt['raw_sha256']==pins[rawpath] and receipt['ticker']==ticker and receipt['target_date']==day
            and receipt['status']=='RAW_CAPTURED' and receipt['final_url']==receipt['request_url']
            and receipt['http_status']==200 and receipt['body_truncated'] is False and receipt['security_id']==e['security_id']==r['security_id']
            and receipt['security_type']=='EQUITY' and stamp(receipt['started_at_utc'])>=closing and stamp(receipt['started_at_utc'])<=stamp(receipt['received_at_utc'])<=now, 'CAPTURE_RECEIPT_INVALID:'+ticker)
        parsed,closes=_daily(raw,ticker);_,previous=_daily(files[r['training_source']],ticker)
        overlap=set(old['training_dates'])&set(days);mismatch=[d for d in sorted(overlap) if closes.get(d)!=previous.get(d)]
        require(not mismatch,'HISTORICAL_COORDINATE_DRIFT:'+ticker+(':'+mismatch[0] if mismatch else ''))
        chart=_json(raw)['chart']['result'][0];events=[];splits=set()
        for kind,values in chart.get('events',{}).items():
            require(kind in ('splits','dividends') and type(values)is dict,'UNKNOWN_EVENT_FAMILY:'+ticker)
            for event in values.values():
                require(type(event)is dict and type(event.get('date'))is int,'INVALID_EVENT_DATE:'+ticker)
                date=datetime.fromtimestamp(event['date'],timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                events.append(dict(kind=kind,date=date,payload=json.loads(json.dumps(event,default=str))))
                if kind=='splits' and days[0]<=date<=day:splits.add((date,str(Fraction(event['numerator'])/Fraction(event['denominator']))))
                require(not(kind=='splits' and date>day),'POST_DECISION_COORDINATE_ACTION:'+ticker)
        expected={(v['date'],str(Fraction(v['factor']))) for v in r['price_coordinate_factors'] if days[0]<=v['date']<=day}
        require(splits==expected,'UNREVIEWED_COORDINATE_EVENT:'+ticker)
        target=next(v for v in result['candidates'] if v['ticker']==ticker)
        target.update(training_source=rawpath,raw_close=[closes.get(d) for d in days],returned_events=events,
            raw_first_session=parsed['dates'][0],raw_last_session=parsed['dates'][-1],missing_training_dates=[d for d in days if closes.get(d) is None],
            coordinate_source_references=list(dict.fromkeys(r['coordinate_source_references']+[previous_manifest_path,rp,rawpath])))
        target['decision_nominal_close']=closes.get(day)
        for k in ('training_close','training_gross'):target.pop(k,None)
        if target['status']=='EXCLUDED_TRAINING_RULE':
            exclusion=result['admission']['training_exclusions'][ticker];exclusion['known_asof']=day
            exclusion['source_references']=list(dict.fromkeys(exclusion['source_references']+[rp,rawpath,previous_manifest_path]))
        captured.append(stamp(receipt['received_at_utc']))
        coverage.append(dict(ticker=ticker,security_id=r['security_id'],observed_sessions=sum(closes.get(d) is not None for d in days),overlap_differences=0,status=target['status']))
    result['coordinate_asof_date']=max(captured).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    result['admission']['decision_date']=day
    result['admission']['source_references']=list(dict.fromkeys(result['admission']['source_references']+[previous_manifest_path,plan_path,capture_index_path]))
    result['source_hashes']=deepcopy(pins)
    result['limitations']=list(old['limitations'])+['Membership remains the pinned prior observation, not a newly dated complete constituent history.',
        'This decision-date package is not a next-month execution mandate.',
        'Coordinate carry-forward is conditional on exact overlap closes and reviewed split factors; this is not complete action certification.']
    manifest_raw=canonical(result);generated='derived-training-manifest/'+sha256(manifest_raw).hexdigest()+'.json'
    files[generated]=manifest_raw;pins[generated]=sha256(manifest_raw).hexdigest()
    compiled=compile_saved_training(dict(files=files,source_hashes=pins,documents={}),generated)
    # The in-memory manifest locator is not a disk source; do not export a phantom pin.
    def remove_virtual(value):
        if isinstance(value,dict):
            value.pop(generated,None)
            for item in value.values():remove_virtual(item)
        elif isinstance(value,list):
            for item in value:remove_virtual(item)
    remove_virtual(compiled)
    return result,compiled,dict(status=compiled['status'],decision_date=day,membership_observation_asof=result['membership_observation_asof'],coordinate_asof_date=result['coordinate_asof_date'],
        training_start=days[0],training_end=days[-1],sessions=len(days),coverage=coverage,source_hashes=deepcopy(result['source_hashes']),search_calls=0,book_calls=0,network_calls=0)


def main(argv=None):
    parser=argparse.ArgumentParser()
    for field in ('previous-manifest-path','previous-manifest-sha256','capture-index-path','capture-index-sha256','plan-path','plan-sha256','output'):parser.add_argument('--'+field,required=True)
    parser.add_argument('--experimental-domain',action='store_true',help='Use the explicit fixed experimental domain; not a new membership observation or production admission.')
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));a=vars(parser.parse_args(argv));output=Path(a.pop('output'))
    experimental=a.pop('experimental_domain')
    if experimental:
        from scripts.monthly_experimental_domain_capture import prepare
        a['plan_validator']=prepare
    require(not output.exists(),'CREATE_ONLY_OUTPUT_EXISTS');manifest,compiled,report=build(**a,clock=utc_now)
    if experimental:report['domain_mode']='EXPERIMENTAL_FIXED_DOMAIN_NOT_PRODUCTION_ADMISSION'
    output.mkdir(parents=True,exist_ok=False)
    for name,value in [('manifest',manifest),('preparation',compiled),('input',compiled['input']),('report',report)]:
        with (output/(name+'.json')).open('xb') as stream:stream.write(canonical(value))
    result=dict(output=str(output),status=report['status'],search_calls=0,book_calls=0)
    if experimental:result['domain_mode']=report['domain_mode']
    print(json.dumps(result))

if __name__=='__main__':main()
