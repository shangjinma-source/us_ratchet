"""Capture and archive a new paper security's first reviewed daily window."""
from hashlib import sha256
import json
import os
from pathlib import Path

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import pinned, reject_links, stamp
from data.strategy_paper_application_descriptor_v2 import NY
from data.strategy_monthly_supplement_capture import capture_supplement
from data.strategy_prospective_paper_first_window_v2 import (
    verified_first_window_context, review_paper_first_window,
)


def load_first_window_archive(*, root, directory, trusted_complete_sha256, expected_binding):
    """Restore only a caller-anchored complete archive; never infer new approval."""
    root=Path(root).absolute();path=Path(directory).absolute();reject_links(path)
    require(path.resolve().is_relative_to(root.resolve()) and not (path/'failed.json').exists(),
            'PAPER_FIRST_ARCHIVE_RECOVERY_REQUIRED')
    def read(name,digest):
        require(isinstance(digest,str) and len(digest)==64 and
                all(c in '0123456789abcdef' for c in digest),'PAPER_FIRST_ARCHIVE_DIGEST')
        target=path/name;reject_links(target)
        require(target.is_file() and target.stat().st_size<=32*1024*1024,'PAPER_FIRST_ARCHIVE_FILE')
        raw=target.read_bytes()
        require(sha256(raw).hexdigest()==digest,'PAPER_FIRST_ARCHIVE_HASH')
        return raw
    complete=json.loads(read('complete.json',trusted_complete_sha256))
    require(complete['schema']=='PAPER_FIRST_WINDOW_ARCHIVE_V2' and
            complete['status']=='FIRST_WINDOW_REVIEWED_NOT_ADMITTED' and
            complete['binding']==expected_binding,'PAPER_FIRST_ARCHIVE_BINDING')
    raw=read('receipt.json',complete['receipt_sha256']);receipt=json.loads(raw)
    require(receipt['source_sha256']==complete['source_sha256'] and
            0<len(receipt['source_sha256'])<=2000 and receipt['normalization_reviewed'] is True and
            receipt['unresolved_units']==[] and receipt['pending_rights']==[] and
            receipt['account_id']==expected_binding['account_id'] and
            receipt['account_revision']==expected_binding['account_revision'] and
            receipt['target_id']==expected_binding['target_id'] and
            receipt['execution_session']['date']==expected_binding['session'],
            'PAPER_FIRST_ARCHIVE_RECEIPT')
    files={};size=0
    for name,digest in receipt['source_sha256'].items():
        body=read('files/'+digest+'.bin',digest);size+=len(body)
        require(size<=32*1024*1024,'PAPER_FIRST_ARCHIVE_BUDGET');files[name]=body
    return dict(receipt_bytes=raw,trusted_receipt_sha256=complete['receipt_sha256'],files=files,
                status=complete['status'],account_mutated=False)


def capture_first_window(*, directory, review_arguments, read_binding,
                         fetch_daily=None, fetch_official=None):
    """read_binding must read the current server book/target, not browser state."""
    arguments = dict(review_arguments, capture_files={})
    context = verified_first_window_context(**arguments)
    root = context['root']
    path = Path(directory).absolute()
    reject_links(path)
    require(path.resolve().is_relative_to(root.resolve()) and path.resolve() != root.resolve(),
            'PAPER_FIRST_CAPTURE_PATH')
    if path.exists():
        return dict(status='NEEDS_RECOVERY', directory=str(path), account_mutated=False)
    config = json.loads(context['configuration_bytes'])
    calendar = json.loads(pinned(root, config['calendar']))
    sessions = calendar['sessions']
    dates = [row['date'] for row in sessions]
    require(dates == sorted(set(dates)), 'PAPER_FIRST_CALENDAR_ORDER')
    now = stamp(context['clock']())
    today = now.astimezone(NY).date().isoformat()
    if today not in dates:
        return dict(status='WAIT_CALENDAR_SESSION', http_calls=0, account_mutated=False)
    index = dates.index(today)
    session = sessions[index]
    if not stamp(session['open']) <= now < stamp(session['close']):
        return dict(status='WAIT_CURRENT_SESSION', http_calls=0, account_mutated=False)
    epoch = config['monthly_decision_date']
    require(index >= 20 and epoch in dates and dates.index(epoch) < index,
            'PAPER_FIRST_COMPLETE_WINDOW_REQUIRED')
    first = min(index-20, dates.index(epoch))
    require(index-first <= 64, 'PAPER_FIRST_WINDOW_BUDGET')
    sid = context['entry']['security_id']
    binding = dict(account_id=context['account_id'], account_revision=context['account_revision'],
                   target_id=context['target_id'], session=today)
    require(read_binding() == binding, 'PAPER_FIRST_CAPTURE_SNAPSHOT_CHANGED')
    request = dict(account_id=binding['account_id'], state_revision=binding['account_revision'],
        window_start=sessions[first]['open'], observed_floor=session['open'],
        securities={sid: dict(ticker=context['entry']['ticker'])},
        current_target_quantities={sid: context['target_quantities'].get(sid, 0)})

    def check_binding():
        require(stamp(context['clock']()) < stamp(session['close']), 'PAPER_FIRST_CAPTURE_SESSION_ENDED')
        return read_binding()

    path.mkdir(parents=True, exist_ok=False)
    def save(name, raw):
        target = path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        reject_links(target)
        with target.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(target.read_bytes() == raw, 'PAPER_FIRST_CAPTURE_READBACK')

    save('intent.json', canonical(dict(binding=binding, request=request,
        configuration_sha256=review_arguments['configuration_sha256'])))
    try:
        captured = capture_supplement(directory=path/'transport', request=request, binding=binding,
            read_binding=check_binding, execute=True, fetch_daily=fetch_daily,
            fetch_official=fetch_official, clock=context['clock'])
        require(captured['status'] == 'CAPTURED_REVIEW_REQUIRED', 'PAPER_FIRST_CAPTURE_INCOMPLETE')
        files = captured['files']
        for name, raw in files.items():
            require(sha256(raw).hexdigest() == captured['source_hashes'][name], 'PAPER_FIRST_CAPTURE_HASH')
        documents = captured['documents']
        original = json.loads(files[documents['action_receipts'][sid]])
        rss_receipt = json.loads(files[documents['rss_receipt']])
        daily = files[original['raw_path']]
        rss = files[documents['rss_raw']]
        require(original['security_id'] == sid and original['ticker'] == context['entry']['ticker'] and
                original['body_truncated'] is False and original['transport_error'] is None,
                'PAPER_FIRST_CAPTURE_RECEIPT')
        daily_receipt = dict(status='CAPTURED', attempts=1, http_status=original['http_status'],
            stored_bytes=len(daily), raw_sha256=original['raw_sha256'], url=original['url'],
            requested_from=original['requested_from'], started_at=original['requested_through'],
            received_at=original['received_at'])
        official_receipt = dict(status='CAPTURED', attempts=1, http_status=rss_receipt['http_status'],
            stored_bytes=rss_receipt['stored_bytes'], raw_sha256=rss_receipt['raw_sha256'],
            url=rss_receipt['url'], started_at=rss_receipt['started_at'], received_at=rss_receipt['received_at'])
        reviewed = review_paper_first_window(**dict(review_arguments, capture_files={
            'daily.response.bin':daily, 'daily.receipt.json':canonical(daily_receipt),
            'official.response.bin':rss, 'official.receipt.json':canonical(official_receipt)}))
        closure = dict(reviewed['files'])
        prefix = 'paper-first-original/'+captured['capture_id']+'/'
        for name, body in files.items():
            require(prefix+name not in closure, 'PAPER_FIRST_CAPTURE_COLLISION')
            closure[prefix+name] = body
        closure[prefix+'binding.json'] = canonical(dict(binding=binding, request=request))
        require(len(closure) <= 2000 and sum(map(len, closure.values())) <= 32*1024*1024,
                'PAPER_FIRST_ARCHIVE_BUDGET')
        receipt = dict(reviewed['receipt'], source_sha256={n:sha256(b).hexdigest() for n,b in closure.items()})
        for digest in set(receipt['source_sha256'].values()):
            body = next(b for n,b in closure.items() if receipt['source_sha256'][n] == digest)
            save('files/'+digest+'.bin', body)
        receipt_raw = canonical(receipt)
        save('receipt.json', receipt_raw)
        require(check_binding() == binding, 'PAPER_FIRST_CAPTURE_SNAPSHOT_CHANGED')
        complete = dict(schema='PAPER_FIRST_WINDOW_ARCHIVE_V2', status='FIRST_WINDOW_REVIEWED_NOT_ADMITTED',
            binding=binding, receipt_sha256=sha256(receipt_raw).hexdigest(),
            source_sha256=receipt['source_sha256'], account_mutated=False, policy_approved=False)
        complete_raw = canonical(complete)
        save('complete.json', complete_raw)
        return dict(complete, directory=str(path), complete_sha256=sha256(complete_raw).hexdigest(),
            receipt_bytes=receipt_raw, files=closure)
    except BaseException as error:
        save('failed.json', canonical(dict(status='FAILED_PRESERVED', reason=str(error), automatic_retry=False)))
        raise
