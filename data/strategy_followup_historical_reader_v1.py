"""Isolated pinned historical reader; independent outer follow-up checks remain mandatory."""
import ast
import base64
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

PROJECTS = {'core', 'data', 'scripts', 'backtest'}
ENTRY = 'data/saved_frontier_first_window_v1.py'

def require(ok, reason):
    if not ok: raise ValueError(reason)

def safe_path(root, name):
    path=Path(name)
    require(not path.is_absolute() and '..' not in path.parts, 'HISTORICAL_PATH_ESCAPE')
    full=root/path
    require(full.resolve().is_relative_to(root.resolve()), 'HISTORICAL_PATH_ESCAPE')
    require(not any(p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&1024) for p in (full,*full.parents)), 'HISTORICAL_LINK_REJECTED')
    return full

def historical_pins(root, reference):
    pins={}; refs={}; seen=set()
    for _ in range(48):
        name=reference['path']; digest=reference['sha256']
        require(name not in seen, 'HISTORICAL_PREPARATION_CYCLE');seen.add(name)
        path=safe_path(root,name)
        require(path.stat().st_size<=1024*1024,'HISTORICAL_PREPARATION_SIZE')
        raw=path.read_bytes()
        require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==digest, 'HISTORICAL_PREPARATION_CHANGED')
        refs[name]=digest; doc=json.loads(raw)
        for key,value in doc.get('source_pins',{}).items(): pins.setdefault(key.replace('\\','/'),value)
        bases=[value for key,value in doc.items() if key.startswith('base_') and isinstance(value,dict) and set(value)=={'path','sha256'}]
        require(len(bases)<=1,'HISTORICAL_PREPARATION_AMBIGUOUS')
        if not bases:return pins,refs
        reference=bases[0]
    raise ValueError('HISTORICAL_PREPARATION_BOUND')

def code_closure(root, files, pins, supplemental_directory=None):
    found={}; pending=[ENTRY]
    while pending:
        name=pending.pop()
        if name in found:continue
        require(len(found)<250,'HISTORICAL_IMPORT_BOUND')
        if name in files:raw=files[name]
        else:
            require(name in pins,'HISTORICAL_DEPENDENCY_UNPINNED:'+name)
            candidate=(Path(supplemental_directory)/(pins[name]+'.bin')) if supplemental_directory else root/'data/cache/followup_historical_sources'/(pins[name]+'.bin')
            if candidate.exists():
                candidate=safe_path(root,candidate.absolute().relative_to(root.absolute()))
                require(candidate.stat().st_size<=2*1024*1024,'HISTORICAL_CODE_SIZE')
                raw=candidate.read_bytes()
            else:
                source=safe_path(root,name)
                require(source.stat().st_size<=2*1024*1024,'HISTORICAL_CODE_SIZE')
                raw=source.read_bytes()
            require(sha256(raw).hexdigest()==pins[name],'HISTORICAL_DEPENDENCY_BYTES_UNAVAILABLE:'+name)
        require(len(raw)<=2*1024*1024,'HISTORICAL_CODE_SIZE')
        found[name]=raw
        for node in ast.walk(ast.parse(raw)):
            if isinstance(node,ast.ImportFrom):
                require(not node.level,'HISTORICAL_RELATIVE_IMPORT_UNSUPPORTED')
                modules=[node.module]
            elif isinstance(node,ast.Import):modules=[a.name for a in node.names]
            else:continue
            for module in modules:
                if module and module.split('.')[0] in PROJECTS:pending.append(module.replace('.','/')+'.py')
    return found

WORKER = r'''import base64,json,sys
from datetime import datetime
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
def audit(event,args):
    if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.posix_spawn'):
        raise RuntimeError('HISTORICAL_NETWORK_OR_PROCESS_FORBIDDEN')
    if event=='open':
        mode=args[1];flags=args[2]
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (1|2|64|512|1024)):
            raise RuntimeError('HISTORICAL_WRITE_FORBIDDEN')
sys.dont_write_bytecode=True
sys.addaudithook(audit)
request=json.loads(Path(sys.argv[2]).read_bytes())
request['configuration_bytes']=base64.b64decode(request['configuration_bytes'])
request['capture_files']={k:base64.b64decode(v) for k,v in request['capture_files'].items()}
now=datetime.fromisoformat(request.pop('now'))
from data.saved_frontier_first_window_v1 import review_first_window
result=review_first_window(root=root,clock=lambda:now,**request)
if result.get('files') is not None: result['files']={k:base64.b64encode(v).decode('ascii') for k,v in result['files'].items()}
print(json.dumps(result,sort_keys=True))
'''

def read_historical_frontier_capture(*, root, preparation_reference, archived_files, prepared, capture, state, target, proposal, risk_state, now, supplemental_directory=None):
    root=Path(root).resolve()
    require(isinstance(now,datetime) and now.tzinfo is not None,'HISTORICAL_CLOCK_REQUIRED')
    pins,refs=historical_pins(root,preparation_reference)
    for configuration in prepared['configurations'].values():
        for ref in configuration['source_pins']:
            name=ref['path'].replace('\\','/')
            require(name in archived_files and sha256(archived_files[name]).hexdigest()==ref['sha256'],'HISTORICAL_ARCHIVED_CODE_CHANGED')
    code=code_closure(root,archived_files,pins,supplemental_directory)
    all_files=dict(archived_files)
    for name,raw in code.items():
        require(name not in all_files or all_files[name]==raw,'HISTORICAL_CODE_COLLISION');all_files[name]=raw
    input_binding=target['payload']['decision']['payload']['input_binding']
    for configuration in prepared['configurations'].values():
        for logical,name in configuration.get('unit_source_paths',{}).items():
            require(logical in input_binding['source_hashes'],'HISTORICAL_UNIT_PIN_MISSING')
            expected=input_binding['source_hashes'][logical]
            raw=all_files.get(name)
            if raw is None:
                path=safe_path(root,name)
                require(path.stat().st_size<=8*1024*1024,'HISTORICAL_UNIT_SIZE')
                raw=path.read_bytes()
            require(sha256(raw).hexdigest()==expected,'HISTORICAL_UNIT_CHANGED')
            all_files[name]=raw
            require(len(all_files)<=2500 and sum(map(len,all_files.values()))<=160*1024*1024,'HISTORICAL_MATERIALIZATION_BOUND')
    require(sum(map(len,all_files.values()))<=160*1024*1024,'HISTORICAL_MATERIALIZATION_BOUND')
    with TemporaryDirectory(prefix='us_ratchet_history_') as directory:
        folder=Path(directory);workspace=folder/'source';workspace.mkdir()
        for name,raw in all_files.items():
            destination=safe_path(workspace,name);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
        worker=folder/'worker.py';worker.write_text(WORKER,encoding='utf-8')
        def first_window(*,root,clock,**request):
            request=dict(request,configuration_bytes=base64.b64encode(request['configuration_bytes']).decode('ascii'),capture_files={k:base64.b64encode(v).decode('ascii') for k,v in request['capture_files'].items()},now=now.isoformat())
            request['extra_security_ids']=sorted(request.get('extra_security_ids',()))
            arguments=folder/'input.json';arguments.write_text(json.dumps(request),encoding='utf-8')
            completed=subprocess.run([sys.executable,'-I','-B',str(worker),str(workspace),str(arguments)],cwd=folder,capture_output=True,text=True,encoding='utf-8',timeout=60,check=False)
            require(completed.returncode==0,'HISTORICAL_READER_FAILED:'+completed.stderr[-2000:])
            result=json.loads(completed.stdout)
            if result.get('receipt') is None: result['reason']=str(result.get('reason'))+':'+completed.stderr[-1500:]
            if result.get('files') is not None:result['files']={k:base64.b64decode(v) for k,v in result['files'].items()}
            return result
        def packets(**kwargs):return _review_packets(first_window=first_window,**kwargs)
        result=_read_capture(packet_reviewer=packets,root=workspace,prepared=prepared,capture=capture,state=state,target=target,proposal=proposal,risk_state=risk_state,now=now)
    result['historical_scope']={}
    for sid,packet in result['packets'].items():
        receipt=json.loads(packet['receipt_bytes'])
        monthly=json.loads(packet['files'][receipt['monthly_history_inputs_path']])
        units=json.loads(packet['files'][monthly['histories'][sid]['units']['review_reference']])
        if 'future_notice_scope' in units:result['historical_scope'][sid]=units['future_notice_scope']
    result['historical_provenance']=dict(code_sha256={k:sha256(v).hexdigest() for k,v in code.items()},materialized_sha256={k:sha256(v).hexdigest() for k,v in all_files.items()},preparation_chain=refs,review_clock=now.isoformat(),legacy_source_review_sha256=pins.get('data/saved_frontier_source_review_v1.py'),isolated=True,live_import_fallback=False,scope='Historical first-window leaf; current independently pinned packet/source/risk/execution reviewers')
    return result

from copy import deepcopy
from core.strategy_account_ledger import canonical
from data.saved_frontier_source_review_v1 import review_proposal_monthly_sources

def _review_packets(*, first_window, root, capture, request, binding, state, target,
                              configurations, proposal, extra_security_ids=(), clock=None):
    """Produce native reviewed SID packets without policy approval or publication.

    Configurations are supplied by the server, including pinned identity/baseline
    closure and fixed calendar. Original capture receipts remain in each closure.
    """
    review_first_window=first_window
    require(capture['status']=='CAPTURED_REVIEW_REQUIRED' and capture['binding']==binding and
        capture['capture_id']==sha256(canonical(dict(binding=binding,request=request))).hexdigest(),
        'SUPPLEMENT_REVIEW_BINDING')
    require(state['account_id']==binding['account_id'] and state['revision']==binding['account_revision'] and
        target['target_id']==binding['target_id'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    files=capture['files'];pins=capture['source_hashes'];documents=capture['documents']
    require(set(files)==set(pins) and sum(map(len,files.values()))<=128*1024*1024,'SUPPLEMENT_SOURCE_BUDGET')
    for name,raw in files.items():require(sha256(raw).hexdigest()==pins[name],'SUPPLEMENT_SOURCE_CHANGED')
    require(set(configurations)==set(documents['action_receipts'])==set(request['securities']),
        'SUPPLEMENT_PACKET_DOMAIN')
    rss=files[documents['rss_raw']];rss_receipt=json.loads(files[documents['rss_receipt']])
    packets={}
    for sid,configuration in configurations.items():
        require(configuration['security_id']==sid,'SUPPLEMENT_PACKET_IDENTITY')
        original=json.loads(files[documents['action_receipts'][sid]])
        require(original['security_id']==sid and original['ticker']==request['securities'][sid]['ticker'] and
            original['http_status']==200 and original['body_truncated'] is False and original['transport_error'] is None,
            'SUPPLEMENT_PACKET_RECEIPT')
        daily=files[original['raw_path']]
        require(original['raw_sha256']==sha256(daily).hexdigest() and rss_receipt['raw_sha256']==sha256(rss).hexdigest(),
            'SUPPLEMENT_PACKET_HASH')
        # Derived receipt fields are an adapter view of the saved original;
        # never replace its real request/receipt timestamps with the review time.
        daily_receipt=dict(status='CAPTURED',attempts=1,http_status=original['http_status'],
            stored_bytes=len(daily),raw_sha256=original['raw_sha256'],url=original['url'],
            requested_from=original['requested_from'],started_at=original['requested_through'],received_at=original['received_at'])
        official_receipt=dict(status='CAPTURED',attempts=1,http_status=rss_receipt['http_status'],
            stored_bytes=rss_receipt['stored_bytes'],raw_sha256=rss_receipt['raw_sha256'],url=rss_receipt['url'],
            started_at=rss_receipt['started_at'],received_at=rss_receipt['received_at'])
        raw=canonical(configuration)
        reviewed=review_first_window(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
            capture_files={'daily.response.bin':daily,'daily.receipt.json':canonical(daily_receipt),
                'official.response.bin':rss,'official.receipt.json':canonical(official_receipt)},
            state=state,target=target,proposal=proposal,extra_security_ids=extra_security_ids,clock=clock)
        require(reviewed.get('receipt') is not None,'SUPPLEMENT_REVIEW_FAILED:'+str(reviewed.get('reason')))
        closure=reviewed['files']
        for name,body in files.items():
            name='supplement-original/'+capture['capture_id']+'/'+name
            require(name not in closure or closure[name]==body,'SUPPLEMENT_SOURCE_COLLISION');closure[name]=body
        closure['supplement-original/'+capture['capture_id']+'/binding.json']=canonical(dict(binding=binding,request=request))
        require(len(closure)<=2000 and sum(map(len,closure.values()))<=32*1024*1024,'SUPPLEMENT_PACKET_BUDGET')
        receipt=dict(reviewed['receipt'],source_sha256={name:sha256(body).hexdigest() for name,body in closure.items()})
        receipt_raw=canonical(receipt)
        packets[sid]=dict(receipt_bytes=receipt_raw,trusted_receipt_sha256=sha256(receipt_raw).hexdigest(),files=closure)
    return dict(status='SUPPLEMENT_PACKETS_REVIEWED_POLICY_UNRELEASED',packets=packets,
                account_writes=False,policy_approved=False)

def _read_capture(*, packet_reviewer, root, prepared, capture, state, target, proposal,
                          risk_state, now):
    require(prepared['status'] == 'SUPPLEMENT_REQUEST_PREPARED', 'WAIT_FRONTIER_PREPARED_REQUEST')
    extra = set() if risk_state is None else set(risk_state['peaks']) | set(risk_state['exited'])
    reviewed = packet_reviewer(root=root, capture=capture,
        request=prepared['request'], binding=prepared['binding'], state=state, target=target,
        configurations=prepared['configurations'], proposal=proposal,
        extra_security_ids=extra, clock=lambda: now)
    combined = None
    identities = {}
    execution = None
    for sid, packet in reviewed['packets'].items():
        receipt = json.loads(packet['receipt_bytes'])
        current = json.loads(packet['files'][receipt['monthly_history_inputs_path']])
        if combined is None:
            combined = deepcopy(current)
            combined['histories'] = {}
            combined['base_target']['quantities'] = {}
            combined['base_target']['price_units'] = {}
            execution = receipt['execution_session']
        require(receipt['execution_session'] == execution and
                current['session_dates'] == combined['session_dates'] and
                current['signal_date'] == combined['signal_date'] and
                current['session_close_times'] == combined['session_close_times'],
                'FRONTIER_REVIEW_CALENDAR_CONFLICT')
        history = deepcopy(current['histories'][sid])
        epoch = current['base_target']['monthly_decision_date']
        history['closes'] = [row for row in history['closes'] if row['date'] >= epoch]
        combined['histories'][sid] = history
        combined['base_target']['quantities'][sid] = current['base_target']['quantities'][sid]
        combined['base_target']['price_units'][sid] = current['base_target']['price_units'][sid]
        meta = json.loads(packet['files'][history['source_reference']])['chart']['result'][0]['meta']
        identities[sid] = dict(ticker=meta['symbol'], exchange=meta['exchangeName'])
    require(combined is not None, 'FRONTIER_EMPTY_REVIEW')
    result = review_proposal_monthly_sources(target=target, proposal=proposal, state=state,
        risk_state=risk_state, inputs=combined, identities=identities, capture=capture,
        request=prepared['request'], execution_session=execution, now=now)
    return dict(review=result, packets=reviewed['packets'], identities=identities,
                account_mutated=False, production_admitted=False)


