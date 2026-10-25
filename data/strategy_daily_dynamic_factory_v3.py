"""Server-owned dynamic domain scheduler; one immutable claim per actual session.

No production wiring. All source callbacks are actual transports or isolated
test injections. Existing packets are admitted by hashes, never mtime.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical,require
from data.strategy_daily_first_window_v2 import SOURCES,review_first_window
from data.strategy_daily_security_domain_v1 import plan_security_domain,locate_unit_baseline_sources,aggregate_security_packets
from data.strategy_daily_sid_continuity_v1 import review_sid_continuity
from data.strategy_daily_rolling_parent_v3 import pinned,bounded_read
from data.strategy_daily_session_capture import reject_links,stamp
from data.strategy_daily_verified_rss_capture_v1 import capture_session,attach_timing

from data.strategy_daily_dynamic_factory_v1 import FACTORY_SOURCES as LEGACY_FACTORY_SOURCES
FACTORY_SOURCES=LEGACY_FACTORY_SOURCES|SOURCES|{'data/strategy_daily_dynamic_factory_v2.py',
    'data/strategy_daily_dynamic_factory_v3.py','data/strategy_daily_verified_rss_capture_v1.py',
    'data/strategy_rss_verified_transport_v1.py'}


def run_dynamic_sources(*,root,configuration_bytes,configuration_sha256,account_reader,target_reader,
                        execute=False,fetch_daily=None,fetch_official=None,clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc));began=stamp(clock())
    reject_links(root);root=Path(root).resolve()
    require(len(configuration_bytes)<=1024*1024 and sha256(configuration_bytes).hexdigest()==configuration_sha256,
            'DYNAMIC_CONFIG_HASH')
    config=json.loads(configuration_bytes)
    require(config['schema']=='SERVER_DYNAMIC_DAILY_SOURCE_V1' and
            config.get('first_window_review_version') == 'CLOSED_AT_ORIGINAL_RECEIPT_V2' and
            config.get('official_time_policy') == 'REAL_WAIT_CHANNEL_MAX_1S_ITEMS_AT_NETWORK_RECEIPT_V1' and
            FACTORY_SOURCES<={r['path'] for r in config['source_pins']},'DYNAMIC_CONFIG_SCHEMA')
    def source_check():
        for ref in config['source_pins']:
            raw=pinned(root,ref,maximum=32*1024*1024)
            if ref['path'] in FACTORY_SOURCES:
                require(raw==(Path(__file__).resolve().parents[1]/ref['path']).read_bytes(),'DYNAMIC_EXECUTING_CODE')
    source_check()
    calendar_raw=pinned(root,config['calendar'],maximum=8*1024*1024);calendar=json.loads(calendar_raw)
    dates=[r['date'] for r in calendar['sessions']]
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ'
            and dates==sorted(set(dates)),'DYNAMIC_CALENDAR')
    today=began.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if today not in dates or today<config['first_execution_date']:
        return dict(status='WAIT_CURRENT_SESSION',http_calls=0)
    index=dates.index(today);session=calendar['sessions'][index]
    if index<20 or began>=stamp(session['close']):return dict(status='WAIT_CURRENT_SESSION',http_calls=0)
    base=root/config['runs_root'];reject_links(base)
    require(base.resolve().is_relative_to(root) and base.resolve()!=root,'DYNAMIC_RUN_ROOT')
    directory=base/today;reject_links(directory)
    def read_saved(day):
        path=base/day;reject_links(path)
        terminal=json.loads(bounded_read(path/'terminal.json'))
        require(terminal['status']=='DYNAMIC_DOMAIN_PACKET_SAVED' and terminal['session']==day
                and terminal['configuration_sha256']==configuration_sha256,'DYNAMIC_PREVIOUS_NOT_ADMITTED')
        require(stamp(terminal['finished_at'])<=began and
                stamp(terminal['finished_at'])<stamp(calendar['sessions'][dates.index(day)]['close']),
                'DYNAMIC_SAVED_TIME')
        result={}
        for sid,packet in terminal['packets'].items():
            key=sha256(sid.encode()).hexdigest()
            for field,name in [('receipt_reference','receipt.json'),('manifest_reference','manifest.json')]:
                require(packet[field]['path']==(path/key/name).relative_to(root).as_posix(),'DYNAMIC_SAVED_PATH')
            raw=pinned(root,packet['receipt_reference']);receipt=json.loads(raw)
            manifest=json.loads(pinned(root,packet['manifest_reference']))
            require(receipt['schema']=='SERVER_REVIEWED_DAILY_EVIDENCE_V1' and receipt['normalization_reviewed'] is True
                    and receipt['unresolved_units']==[] and receipt['pending_rights']==[]
                    and receipt.get('release_sha256')is None and receipt['account_id']==config['account_id'],
                    'DYNAMIC_SAVED_REVIEW')
            require(receipt['execution_session']==calendar['sessions'][dates.index(day)] and
                    stamp(receipt['source_received_at'])<=stamp(receipt['available_at'])<=stamp(terminal['finished_at'])
                    and stamp(receipt['source_received_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==day,
                    'DYNAMIC_PACKET_TIME')
            require(set(manifest)==set(receipt['source_sha256']) and 0<len(manifest)<=2000,'DYNAMIC_SAVED_DOMAIN')
            files={};total=0
            for name,ref in manifest.items():
                require(ref['sha256']==receipt['source_sha256'][name] and
                        ref['path']==(path/'files'/(ref['sha256']+'.bin')).relative_to(root).as_posix(),
                        'DYNAMIC_SAVED_SOURCE_PATH')
                body=pinned(root,ref,maximum=32*1024*1024-total);total+=len(body);files[name]=body
            require(set(json.loads(files[receipt['normalized_inputs_path']])['histories'])=={sid},
                    'DYNAMIC_SAVED_SID')
            result[sid]=dict(receipt_bytes=raw,trusted_receipt_sha256=packet['receipt_reference']['sha256'],files=files)
        # Published combined closure is also independently pinned, not inferred
        # from the existence of individually successful securities.
        require(terminal['aggregate_reference']['path']==(path/'aggregate.json').relative_to(root).as_posix(),
                'DYNAMIC_AGGREGATE_PATH')
        combined=json.loads(pinned(root,terminal['aggregate_reference']))
        require({row['security_id'] for row in combined['aggregate_parents']}==set(result),'DYNAMIC_AGGREGATE_DOMAIN')
        require(terminal['aggregate_manifest_reference']['path']==(path/'aggregate-manifest.json').relative_to(root).as_posix(),
                'DYNAMIC_AGGREGATE_MANIFEST_PATH')
        manifest=json.loads(pinned(root,terminal['aggregate_manifest_reference']))
        require(set(manifest)==set(combined['source_sha256']) and 0<len(manifest)<=2000,'DYNAMIC_AGGREGATE_CLOSURE')
        total=0
        for name,reference in manifest.items():
            require(reference['sha256']==combined['source_sha256'][name] and
                    reference['path']==(path/'files'/(reference['sha256']+'.bin')).relative_to(root).as_posix(),
                    'DYNAMIC_AGGREGATE_SOURCE_PATH')
            total+=len(pinned(root,reference,maximum=32*1024*1024-total))
        return terminal,result
    if directory.exists():
        try:read_saved(today)
        except (ValueError,KeyError,OSError,TypeError) as error:
            return dict(status='NEEDS_RECOVERY',reason=str(error),http_calls=0)
        return dict(status='EXISTING_DYNAMIC_PACKET_VERIFIED',http_calls=0)
    previous={};seen=set()
    if today!=config['first_execution_date']:
        try:
            terminal,previous=read_saved(dates[index-1]);seen=set(terminal['seen_securities'])
        except (ValueError,KeyError,OSError,TypeError) as error:
            return dict(status='WAIT_PREVIOUS_SESSION_EVIDENCE',reason=str(error),http_calls=0)
    state=deepcopy(account_reader());target=deepcopy(target_reader())
    if not target or target['payload']['target_month']!=today[:7]:
        return dict(status='WAIT_MONTHLY_TARGET',http_calls=0)
    require(state['account_id']==config['account_id'],'DYNAMIC_ACCOUNT')
    mapping=locate_unit_baseline_sources(root=root,evidence_root=config['target_evidence_root'],
        binding=target['payload']['decision']['payload']['input_binding'])
    domain=plan_security_domain(root=root,state=state,target=target,identity_reference=config['identity'],
        source_paths=mapping)
    routes={sid:'ROLLING' if sid in previous else 'FIRST' for sid in domain['securities']}
    if any(sid in seen and sid not in previous for sid in routes):
        return dict(status='WAIT_PREVIOUS_SECURITY_EVIDENCE',http_calls=0)
    for sid,route in routes.items():
        if route=='FIRST' and domain['securities'][sid]['unit_baseline']is None:
            return dict(status='WAIT_UNIT_BASELINE',security_id=sid,http_calls=0)
    if not execute:return dict(status='DRY_RUN_NO_HTTP_NO_FILES',routes=routes,http_calls=0)
    directory.mkdir(parents=True,exist_ok=False);calls=0
    def save(name,body):
        raw=body if type(body)is bytes else canonical(body);path=directory/name
        path.parent.mkdir(parents=True,exist_ok=True);reject_links(path)
        with path.open('xb') as stream:stream.write(raw)
        return dict(path=path.relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
    save('intent.json',dict(session=today,configuration_sha256=configuration_sha256,routes=routes,
        account_revision=state['revision'],target_id=target['target_id'],started_at=began.isoformat()))
    save('configuration.json',configuration_bytes)
    from data.current_quantity_v2_paper_action_sources import fetch_daily_actions
    from scripts.current_research_official_alert_capture import fetch_official_feed
    def daily(*args):
        nonlocal calls
        calls+=1;return (fetch_daily or fetch_daily_actions)(*args)
    def official():
        nonlocal calls
        calls+=1;return (fetch_official or fetch_official_feed)()
    def check():
        source_check()
        require(pinned(root,config['calendar'],maximum=8*1024*1024)==calendar_raw,'DYNAMIC_CALENDAR_CHANGED')
        require(account_reader()==state and target_reader()==target,'DYNAMIC_SNAPSHOT_CHANGED')
        require(plan_security_domain(root=root,state=state,target=target,identity_reference=config['identity'],
                    source_paths=mapping)==domain,'DYNAMIC_DOMAIN_CHANGED')
        current=stamp(clock())
        require(began<=current<stamp(session['close']) and
                current.astimezone(ZoneInfo('America/New_York')).date().isoformat()==today,'DYNAMIC_SESSION_ENDED')
        return current
    try:
        packets={}
        for sid,route in sorted(routes.items()):
            check();entry=domain['securities'][sid];key=sha256(sid.encode()).hexdigest()
            if route=='ROLLING':
                prior=previous[sid];document=json.loads(prior['receipt_bytes'])
                inputs=json.loads(prior['files'][document['normalized_inputs_path']])
                meta=json.loads(prior['files'][inputs['histories'][sid]['source_reference']])['chart']['result'][0]['meta']
                authority=dict(previous_receipt_sha256=prior['trusted_receipt_sha256'])
            else:
                metas=[]
                for name,digest in entry['unit_baseline']['source_hashes'].items():
                    body=pinned(root,dict(path=mapping[name],sha256=digest),maximum=8*1024*1024)
                    try:doc=json.loads(body)
                    except (json.JSONDecodeError,UnicodeDecodeError):continue
                    if isinstance(doc,dict) and 'chart'in doc:metas.extend(r['meta'] for r in doc['chart']['result'])
                require(metas,'DYNAMIC_BASELINE_META_REQUIRED');meta=metas[0]
                require(all(all(row.get(k)==meta.get(k) for k in ('symbol','currency','exchangeName','instrumentType'))
                            for row in metas),'DYNAMIC_BASELINE_META_CONFLICT')
                authority=dict(unit_baseline=entry['unit_baseline']['review_reference'])
            require(meta['symbol']==entry['ticker'],'DYNAMIC_IDENTITY_CHANGED')
            security=dict(security_id=sid,ticker=meta['symbol'],**{k:meta[k] for k in ('currency','exchangeName','instrumentType')})
            identity=dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',security=security,
                derivation='EXACT_PREVIOUS_REVIEW_MAPPING',authority=authority,source_authenticated=False,
                coverage_complete=False,new_policy_approval=False)
            identity_ref=save(key+'/identity.json',identity)
            capture_config=dict(schema='SERVER_DAILY_SESSION_CAPTURE_V1',source_pins=config['source_pins'],
                calendar=config['calendar'],identity_review=identity_ref,security=security,
                output_root=(directory/key/'captures').relative_to(root).as_posix())
            raw=canonical(capture_config)
            captured=capture_session(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
                execute=True,fetch_daily=daily,fetch_official=official,clock=clock)
            require(captured['status']=='CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED','DYNAMIC_CAPTURE_FAILED')
            current=check();captured_path=directory/key/'captures'/today
            raw_files={name:bounded_read(captured_path/name,32*1024*1024) for name in
                ('daily.response.bin','daily.receipt.json','official.response.bin','official.receipt.json','official.timing.json')}
            base_capture_files={name:body for name,body in raw_files.items() if name!='official.timing.json'}
            if route=='FIRST':
                first_config=dict(schema='SERVER_FIRST_DAILY_WINDOW_V2',source_pins=config['source_pins'],
                    calendar=config['calendar'],identity=config['identity'],security_id=sid,
                    release_sha256=None,unit_source_paths=mapping)
                raw=canonical(first_config)
                reviewed=review_first_window(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
                    capture_files=base_capture_files,state=state,target=target,clock=clock)
            else:
                reviewed=review_sid_continuity(security_id=sid,parent_receipt_bytes=prior['receipt_bytes'],
                    trusted_parent_sha256=prior['trusted_receipt_sha256'],parent_files=prior['files'],
                    calendar_bytes=calendar_raw,calendar_reference=config['calendar'],capture_files=base_capture_files,now=current)
            require(reviewed.get('receipt')is not None,'DYNAMIC_REVIEW_FAILED:'+reviewed.get('reason',''))
            reviewed=attach_timing(reviewed=reviewed,capture_files=raw_files)
            raw=canonical(reviewed['receipt'])
            packets[sid]=dict(receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest(),files=reviewed['files'])
        combined=aggregate_security_packets(domain=domain,packets=packets,state=state,target=target,now=check().isoformat())
        require(combined.get('receipt')is not None,'DYNAMIC_AGGREGATE_FAILED')
        references={}
        def write_files(files):
            manifest={}
            for name,raw in files.items():
                digest=sha256(raw).hexdigest();path=directory/'files'/(digest+'.bin')
                ref=dict(path=path.relative_to(root).as_posix(),sha256=digest)
                if not path.exists():save('files/'+digest+'.bin',raw)
                else:require(bounded_read(path,32*1024*1024)==raw,'DYNAMIC_FILE_COLLISION')
                manifest[name]=ref
            return manifest
        for sid,packet in packets.items():
            key=sha256(sid.encode()).hexdigest();manifest=write_files(packet['files']);check()
            references[sid]=dict(receipt_reference=save(key+'/receipt.json',packet['receipt_bytes']),
                manifest_reference=save(key+'/manifest.json',manifest))
        manifest=write_files(combined['files']);check()
        aggregate_ref=save('aggregate.json',combined['receipt']);aggregate_manifest=save('aggregate-manifest.json',manifest)
        finished=check()
        terminal=dict(status='DYNAMIC_DOMAIN_PACKET_SAVED',session=today,configuration_sha256=configuration_sha256,
            packets=references,aggregate_reference=aggregate_ref,aggregate_manifest_reference=aggregate_manifest,
            seen_securities=sorted(seen|set(routes)),routes=routes,http_calls=calls,finished_at=finished.isoformat(),
            policy_approved=False,source_authenticated=False,coverage_complete=False)
        save('terminal.json',terminal);return terminal
    except Exception as error:
        terminal=dict(status='NEEDS_RECOVERY',session=today,configuration_sha256=configuration_sha256,
            reason=str(error),http_calls=calls,finished_at=stamp(clock()).isoformat())
        if not(directory/'terminal.json').exists():save('terminal.json',terminal)
        return terminal
