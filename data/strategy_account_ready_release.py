"""Read-only verification of a pinned real-account monthly preparation receipt.

The receipt admits a candidate, never fresh execution quotes or an account write.
Callers must supply independently approved pins and recheck revision under their
activation transaction. Clock injection is for tests; production uses UTC now.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from fractions import Fraction
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, replay, require
from data.strategy_account_runtime import ACCOUNT_ID
from data.strategy_account_runtime_archive import _document, _digest, require_archived_configuration
from data.strategy_account_monthly_release import resolve_monthly_runtime
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_unit_review import review_interval
from data.strategy_account_mark_reference import decode_current_mark
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources


def validate_ready_release(*, root, receipt_path, receipt_sha256, account_state, clock=None):
    root = Path(root).absolute()
    state = deepcopy(account_state)
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    require(isinstance(now, datetime) and now.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
    require(state['account_id'] == ACCOUNT_ID and replay(state['account_id'],
        [event['payload'] for event in state['events']]) == state, 'READY_ACCOUNT_REPLAY_MISMATCH')
    total = 0
    def raw(path, digest=None):
        nonlocal total
        CurrentQuantityV2CurrentCashSources._path(path)
        location = root/path
        require(not any(item.is_symlink() or (item.exists() and
            getattr(item.lstat(), 'st_file_attributes', 0) & 0x400)
            for item in (location, *location.parents)), 'READY_LINK_REFUSED')
        with location.open('rb') as stream:
            value = stream.read(32*1024*1024+1)
        total += len(value)
        require(len(value) <= 32*1024*1024 and total <= 256*1024*1024, 'READY_SOURCE_BUDGET')
        if digest is not None:
            _digest(digest)
            require(sha256(value).hexdigest() == digest, 'READY_SOURCE_CHANGED')
        return value
    def document(path, digest=None):
        return _document(raw(path, digest))
    def stamp(value):
        at = datetime.fromisoformat(value)
        require(at.utcoffset() is not None, 'READY_AWARE_TIMESTAMP_REQUIRED')
        return at
    receipt = document(receipt_path, receipt_sha256)
    require(receipt.get('status') == 'READY_FOR_ACTIVATION_NOT_ACTIVATED'
        and receipt.get('account_writes') is False and receipt.get('service_activated') is False
        and receipt.get('orders_created') is False and type(receipt.get('search_calls')) is int
        and receipt['search_calls'] == 0, 'READY_CANDIDATE_RECEIPT_REQUIRED')
    require(receipt['account_id'] == state['account_id'] and receipt['account_revision'] == state['revision'],
            'READY_ACCOUNT_REVISION_CHANGED')
    require(receipt['target_month'] == now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m'),
            'READY_CURRENT_MONTH_REQUIRED')
    files = receipt['files']
    require(type(files) is dict and set(files) == {'registry','archive','runtime','unit_review','complete'},
            'READY_FILE_BINDINGS_REQUIRED')
    for binding in files.values():
        require(type(binding) is dict and set(binding) == {'path','sha256'}, 'READY_FILE_BINDING_INVALID')
    documents = {name: document(value['path'],value['sha256']) for name,value in files.items()}
    configuration = resolve_monthly_runtime(root=root, registry_path=files['registry']['path'],
        registry_sha256=files['registry']['sha256'], clock=lambda:now, account_state=state)
    require(configuration == documents['runtime'], 'READY_RUNTIME_BINDING_MISMATCH')
    require_archived_configuration(root=root,archive_path=files['archive']['path'],
        archive_sha256=files['archive']['sha256'],configuration=configuration)
    directory = Path(files['complete']['path']).parent
    require(files['unit_review']['path'] == (directory/'unit_review.json').as_posix(), 'READY_REVIEW_PATH_MISMATCH')
    started = document((directory/'started.json').as_posix())
    complete = documents['complete']; review = documents['unit_review']
    require(complete['status'] == 'EVIDENCE_ASSEMBLED_NOT_EXECUTED' and complete['account_mutated'] is False
        and started['account_id'] == state['account_id'] and started['revision'] == state['revision']
        and started['training_manifest_sha256'] == configuration['training_sha256'], 'READY_CAPTURE_BINDING_MISMATCH')
    require(stamp(configuration['training_closed_at']) <= stamp(started['started_at'])
        <= stamp(review['reviewed_at']) <= stamp(complete['finished_at']) <= stamp(receipt['finished_at']) <= now
        and review['reviewed_at'] == receipt['reviewed_at']
        and stamp(started['started_at']).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
            == receipt['target_month'], 'READY_REVIEW_TIME_INVALID')
    refs = complete['documents']; pins = complete['source_hashes']
    require(type(refs) is dict and set(refs) == {'marks','unit_review'} and len(set(refs.values())) == 2
        and type(pins) is dict and 0 < len(pins) <= 2000, 'READY_CAPTURE_SOURCE_DOMAIN')
    sources = {}
    for path,digest in pins.items():
        CurrentQuantityV2CurrentCashSources._path(path)
        if path in refs.values():
            label = next(name for name,value in refs.items() if value == path)
            physical = (directory/(label+'.json')).as_posix()
        elif path.startswith('strategy-action-capture/'):
            require(len(Path(path).parts) == 2, 'READY_ACTION_PATH_INVALID')
            physical = (directory/'actions'/Path(path).name).as_posix()
        elif re.fullmatch('[a-f0-9]{64}\\.(raw|receipt\\.json)', path):
            physical = (directory/'market'/path).as_posix()
        else:
            physical = path
        sources[path] = raw(physical,digest)
    require(all(path in sources for path in refs.values())
        and pins[refs['unit_review']] == files['unit_review']['sha256'], 'READY_DOCUMENT_BINDING_MISMATCH')
    marks = _document(sources[refs['marks']])
    require(review['marks_sha256'] == pins[refs['marks']] and review['account_revision'] == state['revision']
        and review['training_manifest_sha256'] == configuration['training_sha256'], 'READY_UNIT_REVIEW_BINDING_MISMATCH')
    # These quotes are checked at their original capture completion, not reused
    # as live activation/execution quotations.
    for sid,mark in marks.items():
        mark_pins = mark['source_hashes']
        require(set(mark_pins) == set(mark['source_references']) and all(pins.get(path) == digest
            for path,digest in mark_pins.items()), 'READY_MARK_SOURCE_BINDING_MISMATCH')
        quote_receipts = [_document(sources[path]) for path in mark_pins if path.endswith('.receipt.json')]
        require(len(quote_receipts) == 1, 'READY_QUOTE_RECEIPT_REQUIRED')
        quote = quote_receipts[0]
        require(quote['security_id'] == sid and quote['ticker'] == mark['ticker']
            and quote['captured_at'] == mark['captured_at']
            and mark_pins.get(quote['raw_path']) == quote['raw_sha256'], 'READY_QUOTE_BINDING_MISMATCH')
        decoded = decode_current_mark(sources[quote['raw_path']],ticker=mark['ticker'],
            captured_at=stamp(mark['captured_at']),now=stamp(complete['finished_at']),maximum_age_seconds=120)
        require(Fraction(decoded['last_price']) == Fraction(mark['price'])
            and stamp(decoded['last_at']) == stamp(mark['observed_at']), 'READY_QUOTE_VALUE_MISMATCH')
    action_complete = document((directory/'actions/complete.json').as_posix())
    action_started = document((directory/'actions/started.json').as_posix())
    require(action_complete['status'] == 'CAPTURED_NOT_REVIEWED'
        and action_complete['request_sha256'] == sha256(canonical(action_started['request'])).hexdigest(),
        'READY_ACTION_CAPTURE_BINDING_MISMATCH')
    action_pins = action_complete['source_hashes']
    require(type(action_pins) is dict and action_pins and all(pins.get(path) == digest
        for path,digest in action_pins.items()), 'READY_ACTION_SOURCE_MISMATCH')
    provider = StrategyAccountEvidenceProvider(root=root,manifest_path=configuration['training_manifest'],
        manifest_sha256=configuration['training_sha256'],training_closed_at=configuration['training_closed_at'],
        market_capture=None,action_capture=None,limits_builder=None,output_root=root,
        runtime_pins=configuration['runtime_pins'])
    _, historical = provider.training()
    needed = set(historical['metadata']) | {sid for sid,q in state['shares'].items() if q}
    needed |= {order['security_id'] for order in state['orders'].values() if order['status'] == 'OPEN'}
    require(set(marks) == needed, 'READY_MARK_DOMAIN_MISMATCH')
    reviewed = review_interval(state=state,securities={sid:dict(ticker=mark['ticker']) for sid,mark in marks.items()},
        marks=marks,action_package=dict(files={path:sources[path] for path in action_pins},
            source_hashes=action_pins,documents=action_complete['documents']),
        training_manifest_sha256=configuration['training_sha256'],
        historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest(),
        historical_price_basis=historical['price_basis'],training_closed_at=configuration['training_closed_at'],
        marks_sha256=pins[refs['marks']],now=review['reviewed_at'])
    require(reviewed == review, 'READY_REVIEW_REPLAY_MISMATCH')
    return dict(configuration=configuration,receipt=deepcopy(receipt),
        registry_path=files['registry']['path'],registry_sha256=files['registry']['sha256'],
        archive_path=files['archive']['path'],archive_sha256=files['archive']['sha256'],
        account_id=state['account_id'],account_revision=state['revision'])
