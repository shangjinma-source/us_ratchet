"""Independent rolling parent bridge; frozen capture/normalization code is unchanged.

A missing previous exchange session never falls back to an older successful run.
Content-addressed archives are restored into an isolated logical-path workspace.
"""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import reject_links, require, stamp
from data.strategy_daily_continuity_normalizer import normalize_saved_capture


def pinned(root, reference, maximum=1024*1024):
    path=Path(root)/reference['path'];reject_links(path)
    require(path.resolve().is_relative_to(Path(root).resolve()) and path.is_file(),
            'ROLLING_SOURCE_PATH_INVALID')
    require(path.stat().st_size<=maximum,'ROLLING_SOURCE_READ_BUDGET')
    raw=bounded_read(path,maximum)
    require(sha256(raw).hexdigest()==reference['sha256'],'SOURCE_HASH_CHANGED')
    return raw


def bounded_read(path,maximum=1024*1024):
    reject_links(path)
    with Path(path).open('rb') as source:
        raw=source.read(maximum+1)
    require(len(raw)<=maximum,'ROLLING_SOURCE_READ_BUDGET')
    return raw


def previous_session_parent(*, root, calendar_reference, runs_root, accepted_configuration_sha256,
                            seed_receipt_reference, seed_source_paths, now):
    reject_links(root)
    root=Path(root).resolve()
    calendar=json.loads(pinned(root,calendar_reference))
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','ROLLING_CALENDAR_SCHEMA')
    dates=[row['date'] for row in calendar['sessions']]
    require(dates==sorted(set(dates)),'ROLLING_CALENDAR_ORDER')
    today=stamp(now).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(today in dates and dates.index(today)>1,'WAIT_CALENDAR_SESSION')
    previous=calendar['sessions'][dates.index(today)-1]
    seed_raw=pinned(root,seed_receipt_reference);seed=json.loads(seed_raw)
    directory=root/runs_root/previous['date'];reject_links(directory)
    require(directory.resolve().is_relative_to(root),'ROLLING_RUN_OUTSIDE_ROOT')
    if previous['date']==seed['execution_session']['date'] and not directory.exists():
        receipt_raw=seed_raw
        manifest={name:dict(path=seed_source_paths[name],sha256=digest)
                  for name,digest in seed['source_sha256'].items()}
        provenance=dict(kind='FIXED_SEED',receipt_reference=seed_receipt_reference)
    else:
        terminal_path=directory/'terminal.json';reject_links(terminal_path)
        require(terminal_path.is_file(),'WAIT_PREVIOUS_SESSION_PACKET')
        require(terminal_path.stat().st_size<=1024*1024,'ROLLING_TERMINAL_READ_BUDGET')
        terminal=json.loads(bounded_read(terminal_path))
        require(terminal.get('status')=='DAILY_CONDITIONAL_PACKET_SAVED','WAIT_PREVIOUS_SESSION_RECOVERY')
        require(terminal['session']==previous['date'] and terminal['configuration_sha256'] in accepted_configuration_sha256,
                'ROLLING_PARENT_CONFIGURATION_CHANGED')
        for key,name in (('receipt_reference','receipt.json'),('manifest_reference','source-paths.json')):
            require(terminal[key]['path']==(directory/name).relative_to(root).as_posix(),'ROLLING_PACKET_PATH_CHANGED')
        receipt_raw=pinned(root,terminal['receipt_reference'])
        manifest=json.loads(pinned(root,terminal['manifest_reference']))
        for reference in manifest.values():
            require(reference['path']==(directory/'files'/(reference['sha256']+'.bin')).relative_to(root).as_posix(),
                    'ROLLING_SOURCE_PATH_CHANGED')
        require(stamp(terminal['finished_at'])<=stamp(now),'ROLLING_PARENT_FUTURE')
        provenance=dict(kind='PREVIOUS_SESSION_PACKET',receipt_reference=terminal['receipt_reference'])
    receipt=json.loads(receipt_raw)
    require(receipt['execution_session']['date']==previous['date'] and all(
            stamp(receipt['execution_session'][key])==stamp(previous[key]) for key in ('open','close')),
            'ROLLING_PARENT_SESSION_CHANGED')
    expected_signal=calendar['sessions'][dates.index(today)-2]
    require(stamp(receipt['market_asof'])==stamp(expected_signal['close']),
            'ROLLING_PARENT_MARKET_ASOF_CHANGED')
    require(receipt.get('normalization_reviewed') is True and receipt.get('unresolved_units')==[]
            and receipt.get('pending_rights')==[],'ROLLING_REVIEW_REQUIRED')
    require(receipt.get('release_sha256')==seed.get('release_sha256'),'ROLLING_POLICY_CHANGED')
    require(stamp(receipt['source_received_at'])<=stamp(receipt['available_at'])<=stamp(now),'ROLLING_PARENT_FUTURE')
    require(stamp(receipt['source_received_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
            ==previous['date'],'ROLLING_PARENT_RECEIVED_SESSION_CHANGED')
    if provenance['kind']=='PREVIOUS_SESSION_PACKET':
        require(stamp(receipt['available_at'])<=stamp(terminal['finished_at']),'ROLLING_PARENT_FINISH_CHANGED')
    require(set(manifest)==set(receipt['source_sha256']) and 0<len(manifest)<=2000,'ROLLING_SOURCE_DOMAIN')
    files={};total=0
    for name,reference in manifest.items():
        require(reference['sha256']==receipt['source_sha256'][name],'ROLLING_SOURCE_HASH_BINDING')
        raw=pinned(root,reference,maximum=32*1024*1024-total);total+=len(raw)
        require(total<=32*1024*1024,'ROLLING_SOURCE_BUDGET')
        files[name]=raw
    inputs=json.loads(files[receipt['normalized_inputs_path']])
    require(inputs['signal_date']==expected_signal['date'],'ROLLING_PARENT_SIGNAL_DATE_CHANGED')
    return dict(receipt_bytes=receipt_raw,files=files,provenance=provenance)


def normalize_with_archived_parent(*, root, capture_directory, expected_configuration_sha256,
                                  parent, state, target, clock):
    """No network/account changes. The caller publishes a successful bundle create-only."""
    reject_links(root);root=Path(root).resolve()
    directory=root/capture_directory;reject_links(directory)
    require(directory.resolve().is_relative_to(root),'ROLLING_CAPTURE_OUTSIDE_ROOT')
    config_raw=pinned(root,dict(path=(directory/'configuration.json').relative_to(root).as_posix(),
                               sha256=expected_configuration_sha256))
    config=json.loads(config_raw)
    staged=dict(parent['files'])
    def include(name,raw):
        require(name not in staged or staged[name]==raw,'ROLLING_LOGICAL_PATH_CONFLICT')
        staged[name]=raw
    for reference in config['source_pins']+[config['calendar'],config['identity_review']]:
        include(reference['path'],pinned(root,reference))
    identity=json.loads(staged[config['identity_review']['path']])
    if identity.get('review_status')=='DERIVED_FROM_REVIEWED_PARENT':
        reference=identity['parent_reference'];raw=pinned(root,reference);include(reference['path'],raw)
        for name,digest in json.loads(raw)['source_sha256'].items():
            include(name,pinned(root,dict(path=name,sha256=digest)))
    for name in ('configuration.json','calendar.json','identity-review.source','intent.json','terminal.json',
                 'daily.receipt.json','daily.response.bin','official.receipt.json','official.response.bin'):
        path=directory/name;reject_links(path)
        require(path.stat().st_size<=32*1024*1024,'ROLLING_CAPTURE_BUDGET')
        include(path.relative_to(root).as_posix(),bounded_read(path,32*1024*1024))
    parent_raw=parent['receipt_bytes'];digest=sha256(parent_raw).hexdigest()
    parent_name='rolling-parent/'+digest+'.json';include(parent_name,parent_raw)
    require(len(staged)<=2000 and sum(map(len,staged.values()))<=32*1024*1024,'ROLLING_STAGING_BUDGET')
    with TemporaryDirectory(prefix='ratchet-daily-parent-') as temporary:
        workspace=Path(temporary)
        for name,raw in staged.items():
            path=workspace/name
            require(not Path(name).is_absolute() and path.resolve().is_relative_to(workspace),'ROLLING_LOGICAL_PATH_INVALID')
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as output:output.write(raw)
        result=normalize_saved_capture(root=workspace,capture_directory=capture_directory,
            expected_configuration_sha256=expected_configuration_sha256,
            parent_reference=dict(path=parent_name,sha256=digest),state=state,target=target,clock=clock)
    if result.get('receipt') is not None:
        require(result['receipt'].get('release_sha256')==json.loads(parent_raw).get('release_sha256'),
                'ROLLING_POLICY_CHANGED')
        result['rolling_parent_provenance']=parent['provenance']
    return result
