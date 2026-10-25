"""V3 journal-backed evidence, isolated candidate without production wiring.

The fsynced journal is authoritative. Compatibility projections are read back
but not individually fsynced. Missing projections fail closed in old consumers.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import struct
import sys
from threading import Lock
from core.strategy_account_ledger import canonical
from data.current_quantity_v2_paper_action_sources import fetch_daily_actions, daily_url
from scripts.current_research_official_alert_capture import fetch_official_feed, URL


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def stamp(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    require(isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None, 'AWARE_CLOCK_REQUIRED')
    return value.astimezone(timezone.utc)


def safe_error(error, stage, http_status=None):
    allowed = {'TimeoutError', 'URLError', 'HTTPError', 'OSError', 'ValueError',
               'KeyError', 'TypeError', 'PermissionError', 'FileNotFoundError'}
    category = type(error).__name__
    nested = getattr(error, 'reason', None)
    errno = getattr(error, 'errno', None)
    nested_errno = getattr(nested, 'errno', None)
    return dict(stage=stage, exception_category=category if category in allowed else 'OTHER',
                errno=errno if type(errno) is int else None,
                nested_reason_category=type(nested).__name__ if type(nested).__name__ in allowed else None,
                nested_errno=nested_errno if type(nested_errno) is int else None,
                http_status=http_status if type(http_status) is int else None)


def reason_code(error, fallback):
    allowed = {
        'INCOMPLETE_ACTION_DOMAIN', 'ACTION_RAW_BYTES_INVALID', 'ACTION_RESPONSE_INVALID',
        'ACTION_CAPTURE_WINDOW_EXPIRED', 'SERVER_CLOCK_ROLLBACK', 'RSS_RAW_BYTES_INVALID',
        'RSS_RESPONSE_INVALID', 'ACTION_PACKAGE_TOO_LARGE', 'ACTION_JOURNAL_CLOSED',
        'ACTION_JOURNAL_SHORT_WRITE', 'ACTION_INDEX_CHANGED', 'ACTION_JOURNAL_TRUNCATED',
        'ACTION_FRAME_INVALID', 'ACTION_FRAME_NAME', 'ACTION_FRAME_DOMAIN',
        'ACTION_FRAME_HASH', 'ACTION_JOURNAL_INCOMPLETE', 'ACTION_PROJECTION_SHORT_WRITE',
        'ACTION_PROJECTION_CHANGED', 'ACTION_METADATA_SHORT_WRITE', 'ACTION_COMPLETE_EXISTS',
        'ACTION_DIGEST_COLLISION', 'AWARE_CLOCK_REQUIRED'}
    # Never call arbitrary exception/argument __str__, even during failure handling.
    value = error.args[0] if type(error) is ValueError and len(error.args) == 1 else None
    return value if type(value) is str and value in allowed else fallback


class FramedActionJournalV3:
    HEADER = struct.Struct('>4sHQ32s')
    MAGIC = b'ACV3'
    PREFIX = 'strategy-action-capture/'

    def __init__(self, directory, maximum_bytes=128*1024*1024):
        require(type(maximum_bytes) is int and 0 < maximum_bytes <= 128*1024*1024,
                'ACTION_BUDGET_INVALID')
        self.directory = Path(directory)
        self.maximum_bytes = maximum_bytes
        self.stream = (self.directory/'capture.journal').open('xb')
        self.lock = Lock()
        self.entries = {}
        self.pending_content = {}
        self.total = 0
        self.failed = False
        self.sealed = False
        self.files = {}
        self.pins = {}
        self.storage_receipt = None

    def put(self, raw, suffix):
        require(type(raw) is bytes and suffix in {'.raw', '.json', '.xml'},
                'ACTION_STORAGE_INPUT')
        digest = sha256(raw).hexdigest()
        name = digest + suffix
        path = self.PREFIX + name
        with self.lock:
            require(not self.failed and not self.sealed, 'ACTION_JOURNAL_CLOSED')
            if path in self.entries:
                require(self.pending_content[path] == raw, 'ACTION_DIGEST_COLLISION')
                return path
            require(self.total+len(raw) <= self.maximum_bytes and len(self.entries) < 2000,
                    'ACTION_PACKAGE_TOO_LARGE')
            encoded = name.encode('ascii')
            frame = self.HEADER.pack(self.MAGIC, len(encoded), len(raw), bytes.fromhex(digest))
            offset = self.stream.tell()
            try:
                for block in (frame, encoded, raw):
                    require(self.stream.write(block) == len(block), 'ACTION_JOURNAL_SHORT_WRITE')
                self.entries[path] = dict(offset=offset, length=len(raw), sha256=digest)
                self.pending_content[path] = raw
                self.total += len(raw)
            except BaseException:
                self.failed = True
                raise
        return path

    @classmethod
    def replay(cls, journal, index, maximum_bytes=128*1024*1024, *, with_digest=False):
        require(type(index) is dict and 0 < len(index) <= 2000, 'ACTION_INDEX_INVALID')
        found = {}
        total = 0
        journal_hash = sha256()
        with Path(journal).open('rb') as stream:
            while True:
                offset = stream.tell()
                header = stream.read(cls.HEADER.size)
                if not header:
                    break
                require(len(header) == cls.HEADER.size, 'ACTION_JOURNAL_TRUNCATED')
                magic, name_size, size, digest = cls.HEADER.unpack(header)
                require(magic == cls.MAGIC and 65 <= name_size <= 69,
                        'ACTION_FRAME_INVALID')
                require(size <= maximum_bytes-total, 'ACTION_PACKAGE_TOO_LARGE')
                name_bytes = stream.read(name_size)
                require(len(name_bytes) == name_size, 'ACTION_JOURNAL_TRUNCATED')
                name = name_bytes.decode('ascii')
                require(re.fullmatch(r'[a-f0-9]{64}\.(raw|json|xml)', name),
                        'ACTION_FRAME_NAME')
                path = cls.PREFIX+name
                require(path not in found and path in index, 'ACTION_FRAME_DOMAIN')
                raw = stream.read(size)
                require(len(raw) == size, 'ACTION_JOURNAL_TRUNCATED')
                expected = dict(offset=offset, length=size, sha256=digest.hex())
                require(index[path] == expected and sha256(raw).hexdigest() == digest.hex()
                        and name[:64] == digest.hex(), 'ACTION_FRAME_HASH')
                found[path] = raw
                total += size
                journal_hash.update(header)
                journal_hash.update(name_bytes)
                journal_hash.update(raw)
        require(set(found) == set(index), 'ACTION_JOURNAL_INCOMPLETE')
        return (found, journal_hash.hexdigest()) if with_digest else found

    def finish(self):
        with self.lock:
            require(not self.failed and not self.sealed, 'ACTION_JOURNAL_CLOSED')
            self.sealed = True
            try:
                self.stream.flush()
                os.fsync(self.stream.fileno())
                self.stream.close()
                # No successful files/pins map exists until disk replay passes.
                index_raw = canonical(self.entries)
                index_path = self.directory/'capture.index.json'
                with index_path.open('xb') as stream:
                    stream.write(index_raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                saved_index = index_path.read_bytes()
                require(saved_index == index_raw, 'ACTION_INDEX_CHANGED')
                restored, journal_digest = self.replay(self.directory/'capture.journal',
                                       json.loads(saved_index), self.maximum_bytes, with_digest=True)
                for path, raw in restored.items():
                    projection = self.directory/path.removeprefix(self.PREFIX)
                    with projection.open('xb') as stream:
                        require(stream.write(raw) == len(raw), 'ACTION_PROJECTION_SHORT_WRITE')
                        stream.flush()
                    require(projection.read_bytes() == raw, 'ACTION_PROJECTION_CHANGED')
                self.storage_receipt = dict(protocol='FSYNCED_FRAMED_JOURNAL_V3',
                    journal_path='capture.journal', journal_sha256=journal_digest,
                    index_path='capture.index.json', index_sha256=sha256(index_raw).hexdigest(),
                    unique_entries=len(restored), raw_bytes=self.total,
                    projections_individually_fsynced=False, projections_disk_readback=True)
                self.files = restored
                self.pending_content.clear()
                self.pins = {path: sha256(raw).hexdigest() for path, raw in restored.items()}
                return self.storage_receipt
            except BaseException:
                self.failed = True
                raise

    def close(self):
        if not self.stream.closed:
            self.stream.close()


class StrategyAccountActionCaptureV3:
    def __init__(self, *, fetch=fetch_daily_actions, rss_fetch=fetch_official_feed,
                 clock=None, max_workers=4):
        require(type(max_workers) is int and max_workers == 4, 'BOUNDED_CONCURRENCY_REQUIRED')
        self.fetch = fetch
        self.rss_fetch = rss_fetch
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.workers = max_workers

    def capture(self, request, output_directory):
        request = deepcopy(request)
        require(type(request) is dict and set(request) == {
            'account_id', 'state_revision', 'window_start', 'observed_floor',
            'securities', 'current_target_quantities'}, 'ACTION_REQUEST_FIELDS')
        require(all(type(request[k]) is str and bool(request[k])
                    for k in ('account_id', 'state_revision')), 'ACTION_ACCOUNT_BINDING')
        began = stamp(self.clock())
        start, floor = stamp(request['window_start']), stamp(request['observed_floor'])
        require(start <= floor <= began, 'ACTION_REQUEST_TIME')
        securities, targets = request['securities'], request['current_target_quantities']
        require(type(securities) is dict and 0 < len(securities) <= 200
                and type(targets) is dict, 'ACTION_DOMAIN_REQUIRED')
        require(all(type(sid) is str and bool(sid) and type(row) is dict
                    and type(row.get('ticker')) is str
                    and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}', row['ticker'])
                    for sid, row in securities.items()), 'ACTION_IDENTITY_REQUIRED')
        require(len({row['ticker'] for row in securities.values()}) == len(securities),
                'DUPLICATE_TICKER_MAPPING')
        require(all(type(q) is int and q >= 0 and (q == 0 or sid in securities)
                    for sid, q in targets.items()), 'ACTION_TARGET_DOMAIN')
        directory = Path(output_directory)
        require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                        for p in [directory.absolute(), *directory.absolute().parents]),
                'ACTION_DIRECTORY_SYMLINK')
        directory.mkdir(parents=True, exist_ok=False)

        def write(name, raw):
            with (directory/name).open('xb') as stream:
                require(stream.write(raw) == len(raw), 'ACTION_METADATA_SHORT_WRITE')
                stream.flush()
                os.fsync(stream.fileno())

        write('started.json', canonical(dict(request=request, started_at=began.isoformat(),
                                             automatic_retry=False, storage_protocol='FRAMED_JOURNAL_V3')))
        storage = FramedActionJournalV3(directory)
        diagnostics = {}
        diagnostic_lock = Lock()

        def in_window(at):
            require(began <= at and (at-began).total_seconds() < 120, 'ACTION_CAPTURE_WINDOW_EXPIRED')

        def one(sid):
            stage, status = 'worker_start', None
            try:
                ticker = securities[sid]['ticker']
                before = stamp(self.clock())
                in_window(before)
                stage = 'fetch'
                response = self.fetch(ticker, start-timedelta(days=7), before)
                received = stamp(self.clock())
                status = response.get('status')
                stage = 'raw_validate'
                raw = response['body']
                require(type(raw) is bytes and 0 < len(raw) <= 4*1024*1024,
                        'ACTION_RAW_BYTES_INVALID')
                stage = 'raw_journal_append'
                rawpath = storage.put(raw, '.raw')
                stage = 'receipt_build'
                url = daily_url(ticker, start-timedelta(days=7), before)
                receipt = dict(security_id=sid, ticker=ticker, raw_path=rawpath,
                    raw_sha256=sha256(raw).hexdigest(), http_status=response['status'],
                    body_truncated=False, transport_error=None,
                    started_at=before.isoformat(), requested_from=(start-timedelta(days=7)).isoformat(),
                    requested_through=before.isoformat(), received_at=received.isoformat(),
                    events_requested=['dividends', 'splits'], interval='1d', url=url,
                    response_url=response.get('url', url),
                    request_period1=int((start-timedelta(days=7)).timestamp()),
                    request_period2=int(before.timestamp())+1)
                stage = 'receipt_journal_append'
                path = storage.put(canonical(receipt), '.json')
                stage = 'response_validate'
                require(response['status'] == 200 and response.get('url', url) == url,
                        'ACTION_RESPONSE_INVALID')
                stage = 'clock_validate'
                require(received >= before, 'SERVER_CLOCK_ROLLBACK')
                in_window(received)
                # Pending only: not returned as successful evidence until fsync/replay.
                return path, received
            except Exception as error:
                with diagnostic_lock:
                    diagnostics[sid] = safe_error(error, stage, status)
                raise

        stage = 'workers'
        try:
            pending_receipts, times, failures = {}, [], {}
            with ThreadPoolExecutor(max_workers=4) as pool:
                jobs = {pool.submit(one, sid): sid for sid in sorted(securities)}
                for job in as_completed(jobs):
                    sid = jobs[job]
                    try:
                        path, observed = job.result()
                        pending_receipts[sid] = path
                        times.append(observed)
                    except Exception as error:
                        # Existing protocol reason codes only, no exception text export.
                        failures[sid] = reason_code(error, 'ACTION_TRANSPORT_FAILED')
            if failures:
                write('failures.json', canonical(failures))
                raise ValueError('INCOMPLETE_ACTION_DOMAIN')
            require(set(pending_receipts) == set(securities), 'INCOMPLETE_ACTION_DOMAIN')
            stage = 'rss_fetch'
            before = stamp(self.clock())
            in_window(before)
            require(before >= max(times), 'SERVER_CLOCK_ROLLBACK')
            response = self.rss_fetch()
            received = stamp(self.clock())
            raw = response['body']
            require(type(raw) is bytes and 0 < len(raw) <= 2*1024*1024, 'RSS_RAW_BYTES_INVALID')
            stage = 'rss_journal_append'
            rsspath = storage.put(raw, '.xml')
            rssreceipt = storage.put(canonical(dict(url=URL, response_url=response.get('url', URL),
                http_status=response['status'], started_at=before.isoformat(), received_at=received.isoformat(),
                raw_sha256=sha256(raw).hexdigest(), stored_bytes=len(raw))), '.json')
            require(response['status'] == 200 and response.get('url', URL) == URL, 'RSS_RESPONSE_INVALID')
            require(received >= before, 'SERVER_CLOCK_ROLLBACK')
            in_window(received)
            stage = 'journal_fsync_replay_projection'
            durable = storage.finish()
            stage = 'final_clock'
            finished = stamp(self.clock())
            in_window(finished)
            require(finished >= received, 'SERVER_CLOCK_ROLLBACK')
            result = dict(files=storage.files, source_hashes=storage.pins,
                documents=dict(action_receipts=pending_receipts, rss_raw=rsspath, rss_receipt=rssreceipt))
            stage = 'complete_persist'
            write('complete.pending.json', canonical(dict(status='CAPTURED_NOT_REVIEWED',
                request_sha256=sha256(canonical(request)).hexdigest(),
                source_hashes=storage.pins, documents=result['documents'],
                storage=durable, finished_at=finished.isoformat(),
                finished_at_semantics='EVIDENCE_REPLAY_FINISHED_BEFORE_METADATA_BARRIER',
                automatic_retry=False)))
            # The complete marker itself may incur a slow durability barrier.
            # Stage it first and never publish it after crossing the same window.
            post_write_at = stamp(self.clock())
            require(post_write_at >= finished >= received, 'SERVER_CLOCK_ROLLBACK')
            in_window(post_write_at)
            require(not (directory/'complete.json').exists(), 'ACTION_COMPLETE_EXISTS')
            (directory/'complete.pending.json').rename(directory/'complete.json')
            return deepcopy(result)
        except Exception as error:
            diagnostics['_capture'] = safe_error(error, stage)
            try:
                if not storage.stream.closed:
                    storage.stream.flush()
                    os.fsync(storage.stream.fileno())
            except Exception as secondary:
                diagnostics['_failure_journal_flush'] = safe_error(secondary, 'failure_journal_flush')
            try:
                write('diagnostics.json', canonical(diagnostics))
                write('failed.json', canonical(dict(status='BLOCKED',
                    reason=reason_code(error, 'ACTION_CAPTURE_FAILED'),
                    finished_at=stamp(self.clock()).isoformat(), automatic_retry=False)))
            except Exception:
                # No successful return; preserve primary exception and partial files.
                pass
            raise
        finally:
            primary_exception = sys.exc_info()[0]
            try:
                storage.close()
            except Exception:
                if primary_exception is None:
                    raise
