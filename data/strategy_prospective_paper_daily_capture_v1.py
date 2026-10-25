"""Capture/normalize registered historical evidence into formal paper daily signal.

Reviewed parents must be pinned in the registered descriptor source closure.
Their account and WEB policy fields confer no permission on this paper account.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import os
from core.strategy_account_ledger import canonical
from backtest.current_strategy_prospective_paper_book_v1 import replay,_context
from data.strategy_paper_application_descriptor_v1 import require,stamp
from data.strategy_prospective_paper_selection_v1 import verify_prospective_target
from data.strategy_prospective_paper_daily_v1 import verify_prospective_daily
from data.strategy_daily_session_capture import pinned,reject_links
from data.strategy_verified_context_daily_capture_v1 import capture_session
from data.strategy_verified_context_daily_normalizer_v1 import normalize_verified_capture
from data.strategy_paper_execution_preview_v1 import _local_import_closure

CODE_PATHS=_local_import_closure({'data/strategy_prospective_paper_daily_capture_v1.py'})


def capture_prospective_daily(*,root,book,authority,admitted_decisions,selection_result,selection_arguments,
        release_path,capture_requests,output_directory,admitted_settlements=None,clock=None,
        fetch_daily=None,fetch_official=None):
    clock=clock or (lambda:datetime.now(timezone.utc));started=stamp(clock())
    original=deepcopy((book,authority,admitted_decisions,admitted_settlements,selection_result,selection_arguments,capture_requests))
    app=_context(authority,started)
    require(CODE_PATHS<=set(app['code_sha256']),'PAPER_DAILY_CAPTURE_CODE_SCOPE')
    current=replay(book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements)
    selected=verify_prospective_target(selection_result,**selection_arguments)
    previous=replay(selection_arguments['book'],authority=selection_arguments['authority'],
        admitted_decisions=selection_arguments['admitted_decisions'],admitted_settlements=selection_arguments.get('admitted_settlements'))
    require(previous['descriptor_sha256']==current['descriptor_sha256'] and previous['registration_sha256']==current['registration_sha256'] and
        previous['operations']==current['operations'][:len(previous['operations'])],'PAPER_DAILY_CAPTURE_ANCESTRY')
    require(started>=max(stamp(current['last_available_at']),stamp(selection_result['payload']['computation_finished_at'])),
        'PAPER_DAILY_CAPTURE_STATE_FUTURE')
    quantities=selected['target_quantities'];needed={s for s,q in quantities.items() if q}
    require(needed and set(capture_requests)==needed,'PAPER_DAILY_CAPTURE_DOMAIN')
    root=Path(root).absolute();reject_links(root)
    packets={}
    for sid,request in capture_requests.items():
        parent=request['parent_reference'];config_raw=request['configuration_bytes'];config=json.loads(config_raw)
        require(sha256(config_raw).hexdigest()==request['configuration_sha256'] and config['security']['security_id']==sid,
            'PAPER_DAILY_CAPTURE_CONFIG')
        require(app['source_sha256'].get(parent['path'])==parent['sha256'] and
            authority['descriptor_arguments']['source_bytes'][parent['path']]==pinned(root,parent),
            'PAPER_DAILY_PARENT_NOT_REGISTERED')
        identity=config['identity_review']
        require(app['source_sha256'].get(identity['path'])==identity['sha256'] and
            authority['descriptor_arguments']['source_bytes'][identity['path']]==pinned(root,identity),
            'PAPER_DAILY_IDENTITY_NOT_REGISTERED')
        require(config['calendar']['sha256']==app['calendar_sha256'] and
            pinned(root,config['calendar'])==authority['descriptor_arguments']['calendar_bytes'],'PAPER_DAILY_CAPTURE_CALENDAR')
        collected=capture_session(root=root,configuration_bytes=config_raw,configuration_sha256=request['configuration_sha256'],
            execute=True,fetch_daily=fetch_daily,fetch_official=fetch_official,clock=clock)
        require(collected['status']=='CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED','PAPER_DAILY_CAPTURE_INCOMPLETE')
        normalized=normalize_verified_capture(root=root,capture_directory=collected['output'],
            expected_configuration_sha256=request['configuration_sha256'],parent_reference=parent,clock=clock)
        require(normalized['status']=='CONDITIONAL_HISTORY_READY_NOT_ACCOUNT_ADMITTED',normalized.get('reason','PAPER_DAILY_NORMALIZATION'))
        packets[sid]=normalized
    files={};histories={};raw_paths=[];receipts=[];common=None
    for sid,packet in packets.items():
        receipt=packet['receipt'];inputs=json.loads(packet['files'][receipt['normalized_inputs_path']])
        signature={k:inputs[k] for k in ('signal_date','observed_at','session_dates','session_close_times')}
        require(common is None or common==signature,'PAPER_DAILY_MIXED_CALENDAR')
        common=signature;histories[sid]=inputs['histories'][sid];receipts.append(receipt);raw_paths.extend(receipt['raw_source_paths'])
        for path,raw in packet['files'].items():
            require(path not in files or files[path]==raw,'PAPER_DAILY_SOURCE_COLLISION');files[path]=raw
    binding=selection_result['payload']['input_binding']
    cutoff=binding['training_cutoff_date']
    require(cutoff==binding['historical_search_arguments']['decision_date'] and cutoff in common['session_dates'] and
        cutoff<=common['signal_date'],'PAPER_DAILY_TRAINING_ALIGNMENT')
    normalized=dict(common,histories=histories,base_target=dict(quantities=deepcopy(quantities),
        price_units={sid:histories[sid]['units']['basis_id'] for sid in needed},origin_reference=selected['target_id'],
        monthly_decision_date=cutoff))
    normalized_raw=canonical(normalized);name='paper-daily-normalized/'+sha256(normalized_raw).hexdigest()+'.json';files[name]=normalized_raw
    _context(authority,stamp(clock()))
    require((book,authority,admitted_decisions,admitted_settlements,selection_result,selection_arguments,capture_requests)==original,
        'PAPER_DAILY_CAPTURE_INPUT_CHANGED')
    finished=stamp(clock());session=receipts[0]['execution_session']
    require(started<=finished<stamp(session['close']) and all(r['execution_session']==session for r in receipts),'PAPER_DAILY_CAPTURE_CLOCK')
    release=authority['descriptor_arguments']['source_bytes'][release_path]
    receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',release_sha256=sha256(release).hexdigest(),
        account_id=book['account_id'],account_revision=book['revision'],target_id=selected['target_id'],
        normalized_inputs_path=name,normalization_reviewed=True,unresolved_units=[],pending_rights=[],
        market_asof=common['observed_at'],research_observed_at_semantics='MARKET_ASOF_NOT_RECEIPT',
        source_received_at=max(stamp(r['source_received_at']) for r in receipts).isoformat(),available_at=finished.isoformat(),
        execution_session=session,valid_from=max(finished,stamp(session['open'])).isoformat(),valid_until=session['close'],
        raw_source_paths=sorted(set(raw_paths)),source_sha256={p:sha256(b).hexdigest() for p,b in files.items()},
        source_authenticated=False,coverage_complete=False,parent_reviews={sid:capture_requests[sid]['parent_reference']['sha256'] for sid in needed})
    raw=canonical(receipt)
    args=dict(book=book,authority=authority,admitted_decisions=admitted_decisions,admitted_settlements=admitted_settlements,
        selection_result=selection_result,selection_arguments=selection_arguments,now=finished.isoformat(),release_path=release_path,
        receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest(),files=files)
    verified=verify_prospective_daily(**args)
    directory=Path(output_directory).absolute();reject_links(directory)
    require(directory.resolve().is_relative_to(root.resolve()),'PAPER_DAILY_OUTPUT_OUTSIDE_ROOT')
    directory.mkdir(parents=True,exist_ok=False);(directory/'files').mkdir()
    try:
        for digest in set(receipt['source_sha256'].values()):
            value=next(body for path,body in files.items() if receipt['source_sha256'][path]==digest)
            path=directory/'files'/(digest+'.bin')
            with path.open('xb') as stream:
                stream.write(value);stream.flush();os.fsync(stream.fileno())
            require(path.read_bytes()==value,'PAPER_DAILY_ARCHIVE_READBACK')
        with (directory/'receipt.json').open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        tail=stamp(clock());require(tail>=finished and tail<stamp(session['close']),'PAPER_DAILY_CAPTURE_CLOCK')
        require((book,authority,admitted_decisions,admitted_settlements,selection_result,selection_arguments,capture_requests)==original,
            'PAPER_DAILY_CAPTURE_INPUT_CHANGED')
        complete=dict(schema='PROSPECTIVE_PAPER_DAILY_ARCHIVE_COMPLETE_V1',status=verified['status'],
            receipt_sha256=sha256(raw).hexdigest(),source_sha256=receipt['source_sha256'],completed_at=tail.isoformat(),
            account_id=book['account_id'],account_revision=book['revision'],target_id=selected['target_id'],descriptor_sha256=book['descriptor_sha256'])
        complete_raw=canonical(complete)
        with (directory/'complete.json').open('xb') as stream:
            stream.write(complete_raw);stream.flush();os.fsync(stream.fileno())
        final=stamp(clock());require(final>=tail and final<stamp(session['close']),'PAPER_DAILY_CAPTURE_CLOCK')
    except BaseException:
        with (directory/'failed.json').open('xb') as stream:
            stream.write(canonical(dict(status='FAILED_PRESERVED',receipt_is_not_admission=True)))
            stream.flush();os.fsync(stream.fileno())
        raise
    return dict(status=verified['status'],daily_arguments=args,verified=verified,receipt=receipt,
        receipt_sha256=sha256(raw).hexdigest(),archive_complete_sha256=sha256(complete_raw).hexdigest(),directory=str(directory),account_mutated=False,orders_created=False)


def load_prospective_daily_archive(*,directory,trusted_complete_sha256,daily_arguments,clock):
    """Reopen only an independently retained successful archive hash, then reverify."""
    directory=Path(directory).absolute();reject_links(directory)
    require(not (directory/'failed.json').exists(),'PAPER_DAILY_ARCHIVE_FAILED')
    def read(path):
        reject_links(path)
        require(path.is_file() and path.stat().st_nlink==1 and path.stat().st_size<=32*1024*1024,'PAPER_DAILY_ARCHIVE_FILE')
        return path.read_bytes()
    complete_raw=read(directory/'complete.json')
    require(sha256(complete_raw).hexdigest()==trusted_complete_sha256,'PAPER_DAILY_ARCHIVE_COMPLETE_HASH')
    complete=json.loads(complete_raw)
    require(complete['schema']=='PROSPECTIVE_PAPER_DAILY_ARCHIVE_COMPLETE_V1','PAPER_DAILY_ARCHIVE_SCHEMA')
    raw=read(directory/'receipt.json');require(sha256(raw).hexdigest()==complete['receipt_sha256'],'PAPER_DAILY_ARCHIVE_RECEIPT_HASH')
    receipt=json.loads(raw);require(receipt['source_sha256']==complete['source_sha256'],'PAPER_DAILY_ARCHIVE_DOMAIN')
    files={};total=0
    for path,digest in complete['source_sha256'].items():
        require(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'PAPER_DAILY_ARCHIVE_DIGEST')
        body=read(directory/'files'/(digest+'.bin'));total+=len(body)
        require(sha256(body).hexdigest()==digest and total<=32*1024*1024,'PAPER_DAILY_ARCHIVE_BLOB_HASH')
        files[path]=body
    now=stamp(clock());require(now>=stamp(complete['completed_at']),'PAPER_DAILY_ARCHIVE_CLOCK')
    args=deepcopy(daily_arguments);args.update(now=now.isoformat(),receipt_bytes=raw,trusted_receipt_sha256=complete['receipt_sha256'],files=files)
    require(args['book']['descriptor_sha256']==complete['descriptor_sha256'] and args['book']['revision']==complete['account_revision'],
        'PAPER_DAILY_ARCHIVE_ACCOUNT_CHANGED')
    verified=verify_prospective_daily(**args)
    final=stamp(clock());require(final>=now and final<stamp(receipt['valid_until']),'PAPER_DAILY_ARCHIVE_EXPIRED')
    return dict(status=verified['status'],verified=verified,daily_arguments=args,account_mutated=False,orders_created=False)
