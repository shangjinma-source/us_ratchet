"""Create-only all-security first-window collection; no account or policy writes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_first_window_v1 import SOURCES, review_first_window
from data.strategy_daily_security_domain_v1 import plan_security_domain, aggregate_security_packets
from data.strategy_daily_rolling_parent_v3 import pinned, bounded_read
from data.strategy_daily_session_capture import capture_session, reject_links, stamp

RUNNER_SOURCES = SOURCES | {'data/strategy_daily_domain_runner_v1.py'}


def run_domain_sources(*, root, configuration_bytes, configuration_sha256,
                       account_reader, target_reader, execute=False,
                       fetch_daily=None, fetch_official=None, clock=None):
    """Server-configured first-window path. An existing claim is never retried.

    The root and run path must be fixed by server deployment, not request input.
    A succeeding packet still has no release and cannot enable daily trading.
    """
    clock=clock or (lambda:datetime.now(timezone.utc));began=stamp(clock())
    reject_links(root);root=Path(root).resolve()
    require(sha256(configuration_bytes).hexdigest()==configuration_sha256,'DOMAIN_RUN_CONFIG_HASH')
    config=json.loads(configuration_bytes)
    require(config['schema']=='SERVER_DAILY_DOMAIN_RUNNER_V1','DOMAIN_RUN_CONFIG_SCHEMA')
    require(RUNNER_SOURCES<={r['path'] for r in config['source_pins']},'DOMAIN_RUN_CODE_PINS')
    def sources():
        for reference in config['source_pins']:
            raw=pinned(root,reference,maximum=32*1024*1024)
            if reference['path'] in RUNNER_SOURCES:
                require(raw==(Path(__file__).resolve().parents[1]/reference['path']).read_bytes(),
                        'DOMAIN_RUN_EXECUTING_SOURCE_CHANGED')
    sources()
    calendar_raw=pinned(root,config['calendar'],maximum=8*1024*1024)
    calendar=json.loads(calendar_raw);sessions=calendar['sessions']
    today=began.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    by_date={row['date']:row for row in sessions}
    if today not in by_date or stamp(by_date[today]['close'])<=began:
        return dict(status='WAIT_CURRENT_SESSION',http_calls=0)
    require(today>=config['first_execution_date'],'DOMAIN_RUN_NOT_STARTED')
    state=account_reader();target=target_reader()
    if target is None:return dict(status='WAIT_MONTHLY_TARGET',http_calls=0)
    if target['payload']['target_month']!=today[:7]:
        return dict(status='WAIT_MONTHLY_TARGET',http_calls=0)
    domain=plan_security_domain(root=root,state=state,target=target,
        identity_reference=config['identity'],source_paths=config['unit_source_paths'])
    metadata={}
    for sid,entry in domain['securities'].items():
        if entry['unit_baseline'] is None:
            return dict(status='WAIT_UNIT_BASELINE',security_id=sid,http_calls=0)
        candidates=[]
        for name,digest in entry['unit_baseline']['source_hashes'].items():
            raw=pinned(root,dict(path=config['unit_source_paths'][name],sha256=digest),maximum=8*1024*1024)
            try: document=json.loads(raw)
            except (json.JSONDecodeError,UnicodeDecodeError):continue
            if isinstance(document,dict) and 'chart' in document:
                for row in document['chart']['result']:
                    meta=row['meta']
                    candidates.append(dict(security_id=sid,ticker=meta['symbol'],
                        currency=meta['currency'],exchangeName=meta.get('exchangeName'),
                        instrumentType=meta['instrumentType']))
        require(candidates and all(row==candidates[0] for row in candidates),'DOMAIN_BASELINE_IDENTITY_CONFLICT')
        security=candidates[0]
        require(security['ticker']==entry['ticker'] and security['currency']=='USD'
                and security['exchangeName']=='NMS' and security['instrumentType']=='EQUITY',
                'DOMAIN_BASELINE_IDENTITY_UNSUPPORTED')
        metadata[sid]=security
    path=root/config['runs_root']/today;reject_links(path)
    require(path.resolve().is_relative_to(root) and path.resolve()!=root,'DOMAIN_RUN_PATH')
    if path.exists():
        if not (path/'terminal.json').is_file():
            return dict(status='NEEDS_RECOVERY',reason='PARTIAL_DOMAIN_RUN',http_calls=0)
        terminal=json.loads(bounded_read(path/'terminal.json'))
        if terminal.get('status')!='CONDITIONAL_DOMAIN_PACKET_SAVED_POLICY_UNRELEASED':
            return dict(status='NEEDS_RECOVERY',reason=terminal.get('reason','FAILED_DOMAIN_RUN'),http_calls=0)
        require(terminal['configuration_sha256']==configuration_sha256 and terminal['session']==today,
                'DOMAIN_SAVED_CONFIGURATION')
        receipt_raw=bounded_read(path/'receipt.json');manifest_raw=bounded_read(path/'manifest.json')
        require(sha256(receipt_raw).hexdigest()==terminal['receipt_sha256'] and
                sha256(manifest_raw).hexdigest()==terminal['manifest_sha256'],'DOMAIN_SAVED_HASH')
        receipt=json.loads(receipt_raw);manifest=json.loads(manifest_raw)
        require(receipt['schema']=='SERVER_REVIEWED_DAILY_EVIDENCE_V1' and receipt['normalization_reviewed'] is True
                and receipt['unresolved_units']==[] and receipt['pending_rights']==[]
                and receipt.get('release_sha256') is None,'DOMAIN_SAVED_REVIEW')
        require(receipt['execution_session']==by_date[today] and
                stamp(receipt['source_received_at'])<=stamp(receipt['available_at'])<=stamp(terminal['finished_at'])<=began
                and stamp(terminal['finished_at'])<stamp(by_date[today]['close'])
                and stamp(receipt['source_received_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==today,
                'DOMAIN_SAVED_TIME')
        intent=json.loads(bounded_read(path/'intent.json'))
        require(intent['configuration_sha256']==configuration_sha256 and intent['session']==today
                and {p['security_id'] for p in receipt['aggregate_parents']}==set(intent['securities']),
                'DOMAIN_SAVED_SECURITY_DOMAIN')
        require(set(manifest)==set(receipt['source_sha256']) and 0<len(manifest)<=2000,'DOMAIN_SAVED_SOURCES')
        saved={};total=0
        for name,reference in manifest.items():
            require(reference['sha256']==receipt['source_sha256'][name] and
                    reference['path']==(path/'files'/(reference['sha256']+'.bin')).relative_to(root).as_posix(),
                    'DOMAIN_SAVED_SOURCE_PATH')
            body=pinned(root,reference,maximum=32*1024*1024-total);total+=len(body);saved[name]=body
        require(all(name in saved and name!=receipt['normalized_inputs_path'] for name in receipt['raw_source_paths'])
                and bool(receipt['raw_source_paths']),'DOMAIN_SAVED_RAW_DOMAIN')
        inputs=json.loads(saved[receipt['normalized_inputs_path']])
        dates=[s['date'] for s in sessions];previous=sessions[dates.index(today)-1]
        require(inputs['signal_date']==previous['date'] and
                stamp(inputs['observed_at'])==stamp(receipt['market_asof'])==stamp(previous['close']),
                'DOMAIN_SAVED_MARKET_ASOF')
        for parent in receipt['aggregate_parents']:
            require(parent['path'] in saved and sha256(saved[parent['path']]).hexdigest()==parent['sha256'],
                    'DOMAIN_SAVED_PARENT')
        return dict(status='EXISTING_DOMAIN_PACKET_VERIFIED',http_calls=0,output=str(path))
    if not execute:return dict(status='DRY_RUN_NO_HTTP_NO_FILES',http_calls=0,securities=sorted(metadata))
    path.mkdir(parents=True,exist_ok=False);calls=0
    from data.current_quantity_v2_paper_action_sources import fetch_daily_actions
    from scripts.current_research_official_alert_capture import fetch_official_feed
    def daily(*args):
        nonlocal calls
        calls+=1
        return (fetch_daily or fetch_daily_actions)(*args)
    def official():
        nonlocal calls
        calls+=1
        return (fetch_official or fetch_official_feed)()
    def save(name,raw):
        destination=path/name;destination.parent.mkdir(parents=True,exist_ok=True)
        reject_links(destination)
        with destination.open('xb') as stream:stream.write(raw if type(raw)is bytes else canonical(raw))
    save('intent.json',dict(configuration_sha256=configuration_sha256,session=today,
        account_revision=state['revision'],target_id=target['target_id'],
        securities=sorted(metadata),started_at=began.isoformat(),automatic_retry=False))
    save('configuration.json',configuration_bytes)
    def check():
        sources()
        require(pinned(root,config['calendar'],maximum=8*1024*1024)==calendar_raw,'DOMAIN_RUN_CALENDAR_CHANGED')
        require(account_reader()==state and target_reader()==target,'DOMAIN_RUN_SNAPSHOT_CHANGED')
        require(plan_security_domain(root=root,state=state,target=target,
            identity_reference=config['identity'],source_paths=config['unit_source_paths'])==domain,
            'DOMAIN_RUN_BASELINE_CHANGED')
        current=stamp(clock())
        require(began<=current<stamp(by_date[today]['close']) and
                current.astimezone(ZoneInfo('America/New_York')).date().isoformat()==today,'DOMAIN_RUN_SESSION_ENDED')
        return current
    try:
        packets={}
        for sid,security in sorted(metadata.items()):
            check();key=sha256(sid.encode()).hexdigest()
            # REVIEWED refers only to the exact mapping already established by
            # the target unit review; first-window prices remain unreviewed.
            identity=dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',
                security=security,review_kind='DERIVED_EXACT_TARGET_UNIT_BASELINE_IDENTITY',
                baseline=domain['securities'][sid]['unit_baseline']['review_reference'],
                source_authenticated=False,coverage_complete=False,new_policy_approval=False)
            identity_raw=canonical(identity);save(key+'/identity.json',identity_raw)
            identity_ref=dict(path=(path/key/'identity.json').relative_to(root).as_posix(),
                sha256=sha256(identity_raw).hexdigest())
            capture_config=dict(schema='SERVER_DAILY_SESSION_CAPTURE_V1',source_pins=config['source_pins'],
                calendar=config['calendar'],identity_review=identity_ref,security=security,
                output_root=(path/key/'captures').relative_to(root).as_posix())
            capture_raw=canonical(capture_config)
            result=capture_session(root=root,configuration_bytes=capture_raw,
                configuration_sha256=sha256(capture_raw).hexdigest(),execute=True,
                fetch_daily=daily,fetch_official=official,clock=clock)
            require(result['status']=='CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED','DOMAIN_CAPTURE_NOT_COMPLETE')
            check()
            directory=path/key/'captures'/today
            capture_files={name:bounded_read(directory/name,32*1024*1024) for name in
                ('daily.response.bin','daily.receipt.json','official.response.bin','official.receipt.json')}
            review_config=dict(schema='SERVER_FIRST_DAILY_WINDOW_V1',source_pins=config['source_pins'],
                calendar=config['calendar'],identity=config['identity'],security_id=sid,
                release_sha256=None,unit_source_paths=config['unit_source_paths'])
            review_raw=canonical(review_config)
            reviewed=review_first_window(root=root,configuration_bytes=review_raw,
                configuration_sha256=sha256(review_raw).hexdigest(),capture_files=capture_files,
                state=state,target=target,clock=clock)
            save(key+'/review-result.json',{k:v for k,v in reviewed.items() if k!='files'})
            require(reviewed['receipt'] is not None,'DOMAIN_FIRST_REVIEW_FAILED:'+reviewed.get('reason',''))
            receipt_raw=canonical(reviewed['receipt'])
            packets[sid]=dict(receipt_bytes=receipt_raw,trusted_receipt_sha256=sha256(receipt_raw).hexdigest(),
                              files=reviewed['files'])
        current=check()
        combined=aggregate_security_packets(domain=domain,packets=packets,state=state,target=target,now=current.isoformat())
        require(combined.get('receipt') is not None,'DOMAIN_AGGREGATE_NOT_READY')
        manifest={}
        for name,raw in combined['files'].items():
            digest=sha256(raw).hexdigest();relative='files/'+digest+'.bin'
            if not (path/relative).exists():save(relative,raw)
            manifest[name]=dict(path=(path/relative).relative_to(root).as_posix(),sha256=digest)
        check();save('manifest.json',manifest);save('receipt.json',combined['receipt'])
        finished=check()
        terminal=dict(status='CONDITIONAL_DOMAIN_PACKET_SAVED_POLICY_UNRELEASED',session=today,
            configuration_sha256=configuration_sha256,http_calls=calls,finished_at=finished.isoformat(),
            receipt_sha256=sha256(canonical(combined['receipt'])).hexdigest(),
            manifest_sha256=sha256(canonical(manifest)).hexdigest(),policy_approved=False,
            source_authenticated=False,coverage_complete=False)
        save('terminal.json',terminal);return terminal
    except Exception as error:
        terminal=dict(status='NEEDS_RECOVERY',reason=str(error),http_calls=calls,
            session=today,configuration_sha256=configuration_sha256,finished_at=stamp(clock()).isoformat())
        if not (path/'terminal.json').exists():save('terminal.json',terminal)
        return terminal
