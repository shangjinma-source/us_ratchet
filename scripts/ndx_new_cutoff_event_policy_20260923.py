"""Source-bound event policy bridge only. No price generation, HTTP, fit or admission."""
import argparse
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
import gzip
import hashlib
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
SOURCE=Path(__file__).resolve()
OUTPUT=BASE/'new_cutoff_event_policy_20260923_v1/bridge.json'
NY_SOURCE=Path(str(files('tzdata.zoneinfo.America').joinpath('New_York'))).resolve()
NY_BYTES=NY_SOURCE.read_bytes();NY=ZoneInfo.from_file(BytesIO(NY_BYTES),key='America/New_York')
LOADED={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),str(NY_SOURCE):hashlib.sha256(NY_BYTES).hexdigest()}
BOUND={
 'readback':('new_cutoff_raw_readback_20260923_v1/completed102.json','7c03247919319c8e1a1a12be2fd8ccdba59aec20e0d9ee6634e69cc85fd0d53b'),
 'observation':('current_quote_list_observation_20260923_v1/observation.json','a6d8899fb2bc22f755ecd721271ed173f24a0b959b6ff8da9c96985f940fa990'),
 'plan':('new_cutoff_raw_capture_20260923_v1/plan.json','96696abaaa7a8d9dc2765ce436ec2b312af74f4490243a963732bcf26bfedf71'),
 'capture_index':('new_cutoff_raw_capture_20260923_v1/completion_index_102.json','59e8573257a2d55aa80c8a2788e48fe756b7f2fd96eabc672f2d97f5789140fb'),
 'old_index':('latest_conditional_channels_20260919_v1/tasks/index_6b031ed505bb2553928c5e662222e6015183d013be8e259c2f0510e0fa8b89a8.json','0296915fdd34b8027c45a1052d648e6f7697842a649468ccc27fdba47bbb326a'),
 'old_plan':('latest_conditional_channels_20260919_v1/plan.json','440851a7b7a944a52a7a3d978f4430cf5d0d3f2e4a0553d76c6170c4df45379e'),
 'old_audit':('latest_conditional_channels_20260919_v1/independent_raw_decimal_audit.json','9ab1922b3b37c6926d85596bb99ed08787e92403afa6e8f45452654649530eaa'),
 'registry':('standard_split_exact_gap_20260919_v1/registry_readback.json','61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'),
 'additions':('current_mstr_pdf_split_20260919_v1/three_split_facts.json','e02e164554cb56f2aaed60b89e8adc3f059144bb350e88d7206e2fe74dbd401c'),
 'completeness':('new_cutoff_completeness_20260923_v1/manifest.json','d4b16c34ea81e6925dc8cb1d0f56cfdb80731aa7078c64bfd734b4fb375cfbd1'),
 'hon_partition':('post_action_quote_archive_probe_20260919_v2/HON.json','3192fb3c764ef1df6bbedd766fa4f367c23404e9bfd513b3eb13e003f578e8ff'),
}
FALSE=('price_generation_allowed','prices_reconstructed','returns_computed','fit_performed','http_performed',
 'old_raw_audit_reperformed','complete_corporate_actions_verified','identity_interval_verified','point_in_time_verified',
 'provider_binding_verified','volume_unit_verified','legal_training_input_admitted','promotion_allowed',
 'factor_one_assumed_for_all_channels','complex_events_reclassified_as_ordinary','full_transitive_source_closure_reverified')

def require(ok,message):
    if not ok:raise ValueError(message)

def unique(pairs):
    value={}
    for key,item in pairs:
        require(key not in value,'Duplicate JSON key');value[key]=item
    return value

def loads(raw):
    def reject(x):raise ValueError('Nonfinite token')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)

def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

def reference(role):
    path,digest=BOUND[role]
    require(len(digest)==64 and set(digest)<=set('0123456789abcdef'),'Final hard SHA required')
    return dict(path=str(BASE/path),sha256=digest)

def guard(sources):
    for path,digest in {**sources,**LOADED}.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source bytes changed: '+path)

def read(ref,sources):
    path=str(Path(ref['path']).resolve());digest=ref['sha256']
    require(path not in sources or sources[path]==digest,'Conflicting source SHA')
    raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'Source SHA mismatch')
    sources[path]=digest;return raw

def raw_events(raw,ticker):
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    chart=loads(decoded)['chart'];require(chart['error'] is None and len(chart['result'])==1,'Single successful provider result required')
    result=chart['result'][0];require(result['meta']['symbol']==ticker,'Raw symbol differs')
    events=result.get('events',{});require(type(events) is dict and set(events)<={'splits','dividends'},'Unknown event family')
    splits=events.get('splits',{});require(type(splits) is dict,'Split dictionary required')
    return splits,hashlib.sha256(decoded).hexdigest()

def fraction(n,d):
    require(type(n) in (int,float) and type(d) in (int,float) and n>0 and d>0,'Positive numeric ratio required')
    return Fraction(str(n))/Fraction(str(d))

def normalized(events):
    output={}
    for key,event in events.items():
        require(str(event['date'])==key and type(event['date']) is int,'Exact event key/date required')
        day=datetime.fromtimestamp(event['date'],NY).date().isoformat()
        require(day not in output,'Duplicate event session')
        ratio=fraction(event['numerator'],event['denominator'])
        pieces=event['splitRatio'].split(':');require(len(pieces)==2 and Fraction(pieces[0])>0 and Fraction(pieces[1])>0 and Fraction(pieces[0])/Fraction(pieces[1])==ratio,'Ratio text differs')
        output[day]=(key,ratio)
    return output

def map_events(ticker,old,new,task,registry):
    old_days=normalized(old);new_days=normalized(new)
    added=sorted(set(new)-set(old));missing=sorted(set(old)-set(new));changed=sorted(k for k in set(old)&set(new) if old[k]!=new[k])
    policies=task.get('event_policy') or [];by_day={p['session']:p for p in policies}
    require(len(by_day)==len(policies),'Duplicate policy session')
    for policy in policies:
        day=policy['session'];require(day in old_days,'Policy lacks old provider event')
        require(old_days[day][1]==fraction(policy['numerator'],policy['denominator']),'Old policy ratio mismatch')
        if policy['kind']=='ORDINARY_SPLIT':
            evidence=registry.get((ticker,day))
            require(evidence is not None and evidence['eligible'] and evidence['ratio']==old_days[day][1], 'Ordinary requires eligible specific date/ratio')
        elif policy['kind']=='BEFORE_PARTITION_UNMODELLED':
            require(task.get('regular_floor') and day<=task['regular_floor'],'Partition event beyond floor')
        else:raise ValueError('Unsupported legacy policy kind')
    mapped=[]
    for day,(key,ratio) in new_days.items():
        policy=by_day.get(day)
        if policy and key not in added+changed and fraction(policy['numerator'],policy['denominator'])==ratio:
            row=dict(provider_event_key=key,session=day,provider_event=deepcopy(new[key]),policy=deepcopy(policy),status='SPECIFIC_POLICY_MATCH')
            if policy['kind']=='ORDINARY_SPLIT':row['specific_event_reference']=deepcopy(registry[(ticker,day)]['reference'])
            else:row['partition_floor']=task['regular_floor'];row['event_economics_modelled']=False
        else:row=dict(provider_event_key=key,session=day,provider_event=deepcopy(new[key]),policy=None,status='UNRESOLVED_RETURNED_EVENT')
        mapped.append(row)
    return dict(added_event_keys=added,missing_event_keys=missing,changed_event_keys=changed,
        exact_payload_equal=old==new,events=mapped,
        absent_returned_events_is_not_action_completeness=True,old_policy=deepcopy(policies),regular_floor=task.get('regular_floor'))

def new_window(ticker,complete,calendar,floor):
    result=dict(candidate_cutoff='2026-09-21',numerical_coverage=deepcopy(complete),policy_floor=floor,reasons=[])
    require(complete['ticker']==ticker and complete['status']=='OBSERVATION_NUMERICAL_COVERAGE_ONLY','Completeness channel differs')
    require(complete['latest_complete_ohlcv_date']=='2026-09-21','Cutoff differs')
    if not complete['ohlc_127']['numerical_coverage_complete']:result['reasons'].append('NEW_127_OBSERVED_OHLC_COVERAGE_SHORT')
    if not complete['volume_63']['numerical_coverage_complete']:result['reasons'].append('NEW_63_RAW_VOLUME_COVERAGE_SHORT')
    if floor:
        retained=[d for d in calendar if d>=floor];result['post_floor_observed_day_count']=len(retained)
        if len(retained)<127:result['reasons'].append('NEW_POST_ACTION_PARTITION_SHORT_OF_127')
    if ticker in ('CMCSA','TRI'):result['reasons'].append('COMPLEX_RETURNED_EVENT_NOT_ORDINARY_CERTIFICATE')
    if ticker in ('MNST','CRWD'):result['reasons'].append('SAVED_VOLUME_UNIT_RESTRICTION_RETAINED')
    result['all_volume_units_independently_verified']=False
    return result

def old_task_link(oldtask,planned,audited,plan_sha):
    require(oldtask['task']==planned and oldtask['plan_sha256']==plan_sha,'Old task does not match audited original plan')
    require(oldtask['status']==audited['status'] and planned['reason']==audited['reason'] and
        planned['ticker']==audited['ticker'],'Old audit detail and source task differ')
    if audited['audit'] is not None:
        require(audited['audit']['ticker']==planned['ticker'],'Old numerical audit ticker differs')
    else:require(oldtask['status']=='BLOCKED','Missing old numerical audit')

def build():
    sources=dict(LOADED);guard(sources)
    docs={role:loads(read(reference(role),sources)) for role in BOUND}
    members=docs['observation']['observed_symbols'];require(len(members)==len(set(members))==101,'101 unique observed members required')
    require([r['ticker'] for r in docs['plan']['queue']]==members+['TSM','QQQ','SPY'],'Exact 104 roles required')
    require([r['ticker'] for r in docs['readback']['rows']]==members+['TSM'] and docs['readback']['attempted_prefix_count']==102,'Exact 102 attempted channels required')
    require(docs['readback']['index_sha256']==reference('capture_index')['sha256'] and docs['capture_index']['plan_sha256']==reference('plan')['sha256'],'Capture linkage differs')
    complete=docs['completeness'];require(complete['schema']=='NEW_CUTOFF_NUMERICAL_COMPLETENESS_MANIFEST_V1' and complete['candidate_cutoff']=='2026-09-21' and complete['queue_count']==104,'Completeness scope differs')
    for role in ('readback','observation','plan'):
        require(complete['input_references'][role]==reference(role),'Completeness hard input differs')
    calendar=complete['observed_reference_calendar_127'];require(len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[-1]=='2026-09-21','Observed calendar differs')
    for role in ('readback','observation','plan','capture_index','old_index','old_audit','registry','additions','completeness'):
        require(docs[role]['promotion_allowed'] is False,'Source authority upgraded')
    old_entries={r['ticker']:r for r in docs['old_index']['entries']};audit_rows={r['ticker']:r for r in docs['old_audit']['details']}
    require(set(old_entries)==set(audit_rows)==set(members) and len(docs['old_index']['entries'])==len(docs['old_audit']['details'])==101,'Complete old101 denominator required')
    require(docs['old_audit']['index']==reference('old_index') and docs['old_audit']['plan']==reference('old_plan') and
        docs['old_index']['plan_sha256']==reference('old_plan')['sha256'],'Old audit hard index and plan link differs')
    require([r['ticker'] for r in docs['old_audit']['details']]==[r['ticker'] for r in docs['old_index']['entries']]==
        [r['ticker'] for r in docs['old_plan']['tasks']],'Audited old task order differs')
    planned={r['ticker']:r for r in docs['old_plan']['tasks']}
    new_entries={r['ticker']:r for r in docs['capture_index']['entries']};observations={r['ticker']:r for r in docs['readback']['rows']};plan_rows={r['ticker']:r for r in docs['plan']['queue']};coverage={r['ticker']:r for r in complete['rows']}
    require(set(new_entries)==set(members)|{'TSM'} and len(docs['capture_index']['entries'])==102,'New capture index denominator differs')
    registry={}
    for role in ('registry','additions'):
        for index,event in enumerate(docs[role]['events']):
            key=(event['ticker'],event['first_adjusted_trading_date']);require(key not in registry,'Duplicate specific registry coordinate')
            eligible=event.get('simple_split_guard_eligible') is True if role=='registry' else event['specific_simple_share_split_event_supported'] is True
            original=event.get('source_reference',{})
            path=event.get('raw_path',event.get('primary_raw_path',original.get('raw_path')));digest=event.get('raw_sha256',event.get('primary_raw_sha256',original.get('raw_sha256')))
            require(path and digest,'Original specific event bytes reference required');read(dict(path=path,sha256=digest),sources)
            execution_ref=None
            if event.get('execution_evidence'):
                execution=event['execution_evidence'];execution_ref=dict(path=execution['raw_path'],sha256=execution['raw_sha256']);read(execution_ref,sources)
            registry[key]=dict(eligible=eligible,ratio=fraction(event['new_shares'],event['old_shares']),reference=dict(parent=reference(role),event_index=index,original_raw_reference=dict(path=path,sha256=digest),additional_execution_raw_reference=execution_ref))
    require(len(registry)==28 and sum(x['eligible'] for x in registry.values())==26,'28 specific / 26 eligible registry required')
    rows=[]
    for ticker in members:
        oldref={k:old_entries[ticker][k] for k in ('path','sha256')};oldtask=loads(read(oldref,sources));require(oldtask['task']['ticker']==ticker,'Old task ticker differs')
        old_task_link(oldtask,planned[ticker],audit_rows[ticker],reference('old_plan')['sha256'])
        prior_ref=plan_rows[ticker]['prior_receipt']['receipt_reference'];prior=loads(read(prior_ref,sources));require(prior['ticker']==ticker and prior['http_status']==200,'Old receipt differs')
        oldraw=dict(path=prior['raw_path'],sha256=prior['raw_sha256'])
        if oldtask['task'].get('raw_reference'):require(oldraw==oldtask['task']['raw_reference'],'Old task and receipt raw differ')
        entry=new_entries[ticker];receipt_ref=dict(path=entry['receipt_path'],sha256=entry['receipt_sha256']);receipt=loads(read(receipt_ref,sources))
        require(receipt['ticker']==ticker and receipt['http_status']==200 and receipt['attempt_count']==1 and receipt['promotion_allowed'] is False,'New receipt scope differs')
        require(observations[ticker]['receipt_sha256']==receipt_ref['sha256'],'Readback receipt link differs')
        newraw=dict(path=receipt['raw_path'],sha256=receipt['raw_sha256']);oldsplit,olddecoded=raw_events(read(oldraw,sources),ticker);newsplit,newdecoded=raw_events(read(newraw,sources),ticker)
        observation=observations[ticker]['observation'];require(newdecoded==observation['decoded_sha256'] and newsplit==observation['raw_returned_events'].get('splits',{}),'Independent saved raw readback differs')
        mapping=map_events(ticker,oldsplit,newsplit,oldtask['task'],registry)
        floor=oldtask['task'].get('regular_floor');floor_source='OLD_TASK_EXPLICIT_PARTITION' if floor else None
        if ticker=='HON':
            proposal=docs['hon_partition']['original_interval_plan_row']['proposed_interval']
            require(proposal['ticker']==ticker and proposal['first_post_action_session']=='2026-06-29' and
                proposal['post_action_cusip']=='438516205' and proposal['point_in_time_verified'] is False and
                proposal['simple_split_whole_channel_admitted'] is False,'Saved HON partition differs')
            floor=proposal['first_post_action_session'];floor_source=dict(reference=reference('hon_partition'),
                pointer='original_interval_plan_row.proposed_interval.first_post_action_session',interval_certified=False)
        window=new_window(ticker,coverage[ticker],calendar,floor)
        if not mapping['exact_payload_equal']:window['reasons'].append('NEW_OLD_SPLIT_PAYLOAD_DIFF_REQUIRES_REVIEW')
        if any(e['status']=='UNRESOLVED_RETURNED_EVENT' for e in mapping['events']):window['reasons'].append('UNRESOLVED_RETURNED_EVENTS')
        rows.append(dict(ticker=ticker,role='OBSERVED_MEMBER_PROVIDER_CHANNEL',new_raw_reference=newraw,new_receipt_reference=receipt_ref,
            new_decoded_sha256=newdecoded,old_decoded_sha256=olddecoded,old_raw_reference=oldraw,old_receipt_reference=prior_ref,
            old_task_reference=oldref,old_audit_reference=reference('old_audit'),old_status=audit_rows[ticker]['status'],old_reason=audit_rows[ticker]['reason'],
            old_liquidity_status=(audit_rows[ticker].get('audit') or {}).get('liquidity_status'),
            old_returned_splits=oldsplit,new_returned_splits=newsplit,event_policy_bridge=mapping,new_window_derivation=window,
            event_family_scope='SPLITS_ONLY_DIVIDENDS_PRESERVED_IN_RAW_REFERENCE_NOT_CLASSIFIED',
            floor_evidence_basis=floor_source,zero_returned_splits_implies_factor_one=False,**dict.fromkeys(FALSE,False)))
    require(sum(p['kind']=='ORDINARY_SPLIT' for r in rows for p in r['event_policy_bridge']['old_policy'])==26 and
        sum(p['kind']=='BEFORE_PARTITION_UNMODELLED' for r in rows for p in r['event_policy_bridge']['old_policy'])==3,
        'Exact old 26 ordinary / 3 partition policy denominator required')
    counts=dict(ordinary_policy_matches=sum(e.get('policy',{}).get('kind')=='ORDINARY_SPLIT' for r in rows for e in r['event_policy_bridge']['events'] if e.get('policy')),
        partition_policy_matches=sum(e.get('policy',{}).get('kind')=='BEFORE_PARTITION_UNMODELLED' for r in rows for e in r['event_policy_bridge']['events'] if e.get('policy')),
        changed_channels=sum(not r['event_policy_bridge']['exact_payload_equal'] for r in rows))
    guard(sources)
    return dict(schema='NEW_CUTOFF_101_EVENT_POLICY_BRIDGE_V1',member_queue_count=101,full_capture_queue_count=104,
        additional_roles={'TSM':'INCUMBENT_ONLY_NOT_MEMBER','QQQ':'UNATTEMPTED_PRIOR_URL_MISSING','SPY':'UNATTEMPTED_PRIOR_URL_MISSING'},
        candidate_cutoff='2026-09-21',september22_missing_close_preserved=True,rows=rows,counts=counts,
        observed_reference_calendar_127=calendar,input_references={role:reference(role) for role in BOUND},source_hashes=sources,
        scope='POLICY_REUSE_EVIDENCE_ONLY_NOT_PRICE_OR_IDENTITY_ADMISSION',**dict.fromkeys(FALSE,False))

def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required')
    value=build();guard(value['source_hashes']);payload=encoded(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as handle:handle.write(payload);handle.flush();os.fsync(handle.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==payload,'Published bytes differ')
    return dict(path=str(OUTPUT),sha256=hashlib.sha256(payload).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
