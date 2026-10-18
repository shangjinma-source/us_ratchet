"""Pinned original journal observation -> conditional account execution reference.

Authority and mapping must come from the server, not browser input. This adapter
never discovers a latest file, recovers an old success as current, or fetches.
"""
import base64
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from data.current_research_intraday_buy_plan import _require, _time
from data.current_research_intraday_execution import decode_intraday_reference
from data.current_research_intraday_execution_reference import POLICY
from data.current_research_intraday_paper_ledger import _MemoryPath
from data.current_research_intraday_review import review_intraday_session

MAX_EVENTS = 1000
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


class _PinnedJournal:
    def __init__(self, files):
        self.root = _MemoryPath({name:base64.b64encode(raw).decode('ascii') for name,raw in files.items()})

    def read_event(self, path, *, expected_sha256):
        raw=(self.root/path).read_bytes()
        _require(sha256(raw).hexdigest()==expected_sha256,'EVENT_HASH_MISMATCH')
        event=json.loads(raw)
        for item in event['captures']:
            _require(item['path']==f"raw/{item['sha256']}.bin",'RAW_PATH_INVALID')
            _require(sha256((self.root/item['path']).read_bytes()).hexdigest()==item['sha256'],'RAW_HASH_MISMATCH')
        return event


def read_journal_execution_reference(*, root, binding, current_reference, event_hashes, now, frozen_files=None, current_reference_reader=None):
    """Read fixed original event/dependency hashes and original USED bytes.

    binding exact keys: account_id, target_month, research_id, security_id,
    ticker, session. frozen_files maps original relative paths to bytes; it is
    for immutable replay, never a claim that the old authority is still live.
    ``now`` validates freshness only and does not alter the frozen reference.
    Expected hashes must be server-held original receipts, not freshly computed
    hashes offered as independent proof. Without current_reference_reader only
    the supplied authority snapshot is checked, not ongoing live authority.
    """
    now=_time(now);base=Path(root).resolve()
    _require(isinstance(binding,dict) and set(binding)=={'account_id','target_month','research_id','security_id','ticker','session'},'EXACT_JOURNAL_BINDING_REQUIRED')
    _require(all(isinstance(v,str) and v for v in binding.values()),'INVALID_JOURNAL_BINDING')
    _require(re.fullmatch('[0-9a-f]{24}',binding['research_id']) and re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',binding['target_month']) and binding['session'][:7]==binding['target_month'],'BINDING_MONTH_OR_RESEARCH_INVALID')
    authority=deepcopy(current_reference)
    if current_reference_reader is not None:
        _require(callable(current_reference_reader) and current_reference_reader(binding['research_id'])==authority,'CURRENT_AUTHORITY_CHANGED')
    _require(isinstance(authority,dict) and authority.get('schema')=='CURRENT_INTRADAY_EXECUTION_REFERENCE_V1' and authority.get('status')=='AVAILABLE'
             and authority.get('research_id')==binding['research_id'] and authority.get('research_only') is True and authority.get('execution_blocked') is True,'NO_AVAILABLE_CURRENT_AUTHORITY')
    _require(type(authority.get('attempt_token')) is int and authority['attempt_token']>0,'INVALID_AUTHORITY_ATTEMPT')
    receipt=authority['current_receipt'];response=authority['response']
    _require(isinstance(receipt,dict) and receipt.get('status')=='SAVED' and isinstance(response,dict) and response.get('status')=='AVAILABLE','CURRENT_RECEIPT_REQUIRED')
    _require(response.get('observation_record')==receipt,'AUTHORITY_RECEIPT_MISMATCH')
    for key in ('research_id','process_boot_id','observation_sequence'):
        _require(response.get(key)==authority.get(key),'AUTHORITY_RESPONSE_MISMATCH:'+key)
    _require(isinstance(event_hashes,dict) and 0<len(event_hashes)<=MAX_EVENTS and event_hashes.get(receipt['event_path'])==receipt['event_sha256'],'CURRENT_EVENT_NOT_PINNED_OR_TOO_MANY')
    files={};consumed={};total_bytes=0
    def read(name,digest):
        nonlocal total_bytes
        _require(isinstance(name,str) and '\\' not in name and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and ':' not in name,'SOURCE_PATH_INVALID')
        _require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),'INVALID_SOURCE_HASH')
        if name in consumed:
            _require(consumed[name]==digest,'SOURCE_PIN_CONFLICT')
            return files[name]
        if frozen_files is None:
            path=(base/name).resolve()
            _require(path.is_relative_to(base),'SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
            size=path.stat().st_size
            _require(size<=MAX_SOURCE_BYTES and total_bytes+size<=MAX_TOTAL_BYTES,'SOURCE_BYTE_BUDGET_EXCEEDED')
            raw=path.read_bytes()
        else:
            _require(isinstance(frozen_files,dict),'INVALID_FROZEN_FILES');raw=frozen_files[name]
        _require(isinstance(raw,bytes) and len(raw)<=MAX_SOURCE_BYTES and total_bytes+len(raw)<=MAX_TOTAL_BYTES and sha256(raw).hexdigest()==digest,'SOURCE_HASH_MISMATCH')
        files[name]=raw;consumed[name]=digest;total_bytes+=len(raw)
        return raw
    for path,digest in event_hashes.items():
        _require(re.fullmatch(r'events/'+re.escape(binding['session'])+r'/[0-9a-f]{32}\.json',path),'EVENT_SESSION_PATH_MISMATCH')
        event=json.loads(read(path,digest))
        for capture in event['captures']:
            _require(capture['path']==f"raw/{capture['sha256']}.bin",'CAPTURE_PATH_MISMATCH')
            read(capture['path'],capture['sha256'])
    journal=_PinnedJournal(files)
    audit=review_intraday_session('',binding['session'],expected_event_hashes=event_hashes,journal=journal,inventory_scope='PINNED_CAP_CLOSURE')
    _require(audit['status']=='REVIEWED_LOCAL_OBSERVATIONS' and not audit['missing_receipts'] and not audit['events_with_issues'],'JOURNAL_DEPENDENCY_REVIEW_FAILED:'+json.dumps([(r['path'],r['issues']) for r in audit['records'] if r['issues']]))
    event=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
    _require(event['event_id']==receipt['event_id'],'CURRENT_EVENT_ID_MISMATCH')
    for key in ('research_id','process_boot_id','observation_sequence'):
        _require(event[key]==authority[key],'CURRENT_EVENT_AUTHORITY_MISMATCH:'+key)
    archived=deepcopy(response);archived.pop('observation_record',None)
    _require(archived==event['response'],'CURRENT_RESPONSE_NOT_ORIGINAL_OBSERVATION')
    _require(_time(authority['attempt_started_at'])<=_time(event['request_started_at'])<=_time(event['request_finished_at'])<=_time(authority['attempt_finished_at'])<=now,'AUTHORITY_ATTEMPT_TIME_MISMATCH')
    selected=event['research_binding']['selected_security']
    _require(selected['security_id']==binding['security_id'] and selected['ticker']==binding['ticker'],'RESEARCH_SECURITY_MAPPING_MISMATCH')
    rows=[r for r in event['response']['stocks'] if r['ticker']==binding['ticker'] and r['status']=='AVAILABLE' and r['session']==binding['session']]
    _require(len(rows)==1,'CURRENT_ROW_MISSING_OR_AMBIGUOUS');row=rows[0]
    used=[r for r in event['captures'] if r['role']=='USED' and r['ticker']==binding['ticker']]
    _require(len(used)==1,'USED_CAPTURE_NOT_UNIQUE');used=used[0]
    checked=_time(row['checked_at']);captured=_time(used['captured_at'])
    _require(captured<=checked<=now,'CURRENT_CHECKED_TIME_INVALID')
    historical=decode_intraday_reference(files[used['path']],ticker=binding['ticker'],now=checked,captured_at=captured)
    current=decode_intraday_reference(files[used['path']],ticker=binding['ticker'],now=now,captured_at=captured)
    _require(now<_time(current['refresh_by']) and historical==current,'CURRENT_REFERENCE_EXPIRED_OR_CHANGED')
    replay_at=authority['attempt_finished_at']
    _require(_time(replay_at)<_time(current['refresh_by']),'AUTHORITY_FINISHED_AFTER_EXPIRY')
    if current_reference_reader is not None:
        _require(current_reference_reader(binding['research_id'])==authority,'CURRENT_AUTHORITY_CHANGED')
    last=Fraction(current['last_price']);sell=Fraction(-(-(last*100).numerator//(last*100).denominator),100)
    return dict(policy=POLICY,source_kind='INTRADAY_JOURNAL_OBSERVATION_V1',security_id=binding['security_id'],ticker=binding['ticker'],
        session=binding['session'],scope_id=binding['account_id']+':'+binding['target_month'],
        session_open=current['session_open'],session_close=current['session_close'],last_price=current['last_price'],last_at=current['last_at'],
        minute_low=current['minute_low'],minute_start=current['minute_start'],minute_end=current['minute_end'],captured_at=used['captured_at'],
        checked_at=row['checked_at'],replay_at=replay_at,valid_until=current['refresh_by'],buy_limit=str(Fraction(row['limit_price'])),sell_limit=str(sell),
        prior_buy_cap=None if row['cap_before'] is None else str(Fraction(row['cap_before'])),source_hashes=consumed,
        journal_event_path=receipt['event_path'],journal_event_sha256=receipt['event_sha256'],journal_event_hashes=deepcopy(event_hashes),
        journal_authority=deepcopy(authority),journal_binding=deepcopy(binding),source_bytes_verified=True,source_authenticated=False,
        latest_tip_authenticated=False,research_only=True,execution_blocked=True,account_mutated=False,
        limitations=['Server-owned current authority and account-to-research mapping are explicit trust inputs, not exchange authentication.',
                    'Original journal observation and USED capture times are retained; freshness is rechecked without fetching.',
                    'BUY uses reviewed original cap. SELL ceil(last) is conditional, not bid/ask or proven execution improvement.',
                    'No corporate-action completeness, actual fill, or UI delivery certification.'])
