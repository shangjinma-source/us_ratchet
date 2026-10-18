"""Fixed source-lead capture. No HTTP without explicit execute; no admission."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import json
import logging
import multiprocessing
import time
import os
import re
import stat

SOURCE = Path(__file__).absolute()
# Initial immutable version observed by this loaded module. External host approval
# is separate; this value only prevents parent/child versions drifting mid-run.
LOADED_SOURCE_SHA = sha256(SOURCE.read_bytes()).hexdigest()

ROOT = Path('E:/Git/us_ratchet')
PLAN = ROOT / 'tmp/remaining_nine_sec_acquisition_plan_20261009_v1/plan.json'
PLAN_SHA = '3ea09c9309a88e0cf354335686a1088519a0263d4a7f5ce2f5f5c4c2af35e756'
OUTPUT_ROOT = ROOT / 'tmp/remaining_nine_sec_original_capture_20261009_v1'
DEADLINE_SECONDS = 25.0
HTML_BYTES = 32_000_000
INDEX_BYTES = 2_000_000
FALSE = dict(source_authenticity_verified=False, source_available_at_verified=False,
             point_in_time_verified=False, issuer_interval_verified=False,
             classification_performed=False, registry_apply_called=False,
             qualified_pool_created=False, execution_authorized=False, promotion_allowed=False)

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(raw): return sha256(raw).hexdigest()
def clock(): return datetime.now(timezone.utc).isoformat()
def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')

def save(path, raw):
    safe_path(path)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Durable exclusive bytes differ')
    return {'path': str(path), 'sha256': digest(raw)}

def safe_path(path):
    """Reject symlinks, junctions and all Windows reparse points, including ancestors."""
    for part in reversed((path, *path.parents)):
        try: metadata = part.lstat()
        except FileNotFoundError: continue
        junction = getattr(part, 'is_junction', None)
        require(not part.is_symlink() and not (callable(junction) and junction())
                and not (getattr(metadata, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT),
                'Linked or reparse path forbidden')

def own_version():
    safe_path(SOURCE)
    require(digest(SOURCE.read_bytes()) == LOADED_SOURCE_SHA, 'Loaded capture source version drift')

def inventory(path):
    safe_path(path)
    require(path.is_dir() and not path.is_symlink(), 'Invalid protected namespace')
    for member in path.rglob('*'): safe_path(member)
    return sorted(p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file())

def _bound_inputs():
    own_version()
    safe_path(PLAN)
    raw = PLAN.read_bytes()
    require(digest(raw) == PLAN_SHA, 'Fixed plan bytes mismatch')
    plan = json.loads(raw)
    require(plan['http_performed'] is False and plan['execution_authorized'] is False, 'Plan is not an admission')
    jobs = []
    for row in plan['proposed_first_batch_primary_and_index_roster']:
        cik = row['cik']; accession = row['declared_filing']['accessionNumber']
        name = row['declared_filing']['primaryDocument']; ticker = row['ticker_context_only_not_sid']
        require(re.fullmatch(r'\d{10}', cik) and re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession), 'Fixed SEC coordinates')
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) and '..' not in name, 'Fixed primary filename')
        base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}'
        expected_folder = ROOT / 'tmp/remaining_nine_sec_original_capture_20261009_v1' / ticker / accession.replace('-', '')
        require(row['planned_new_namespace_not_created'] == str(expected_folder), 'Plan namespace role mismatch')
        require(row['primary_url'] == base + '/' + name and row['attachment_listing_url_to_capture_once'] == base + '/index.json', 'Closed SEC URLs')
        for role, url, limit in [('primary', row['primary_url'], HTML_BYTES), ('index', row['attachment_listing_url_to_capture_once'], INDEX_BYTES)]:
            jobs.append(dict(ticker=ticker, cik=cik, accession=accession, role=role, url=url,
                             max_bytes=limit, declared_filing=row['declared_filing'], source_submission_reference=row['source_submission_reference']))
    require(len(jobs) == 34 and len({j['url'] for j in jobs}) == 34, 'Fixed unique 17+17 roster')
    sources = dict(plan['source_hashes']); sources[str(PLAN)] = PLAN_SHA
    sources[str(SOURCE)] = LOADED_SOURCE_SHA
    return jobs, sources, plan['protected_namespace_inventories']

def _guard(sources, namespaces):
    own_version()
    for path, checksum in sources.items():
        p = Path(path)
        safe_path(p)
        require(not p.is_symlink() and digest(p.read_bytes()) == checksum, 'Fixed source drift')
    for path, names in namespaces.items(): require(inventory(Path(path)) == names, 'Fixed namespace drift')

def _sec_headers():
    # Same existing SEC identity policy; never return identity in logs or receipts.
    value = os.environ.get('SEC_USER_AGENT', '').strip()
    require(len(value) >= 12 and '@' in value, 'SEC_USER_AGENT identifying contact required')
    email = re.search(r'[^\s<>]+@[^\s<>]+', value)
    return {'User-Agent': value, 'From': email.group(0) if email else '', 'Accept-Encoding': 'identity'}

def _http_worker(sender, url, max_bytes, parent_loaded_sha):
    """Only parent-selected literal URL. Process can be terminated during DNS/read."""
    connection = None
    try:
        # spawn reimports this source; it must still be the parent's registered
        # version before importing/constructing any network transport.
        own_version()
        require(LOADED_SOURCE_SHA == parent_loaded_sha, 'Spawn parent/child source mismatch')
        import http.client
        from urllib.parse import urlsplit
        target = urlsplit(url)
        require(target.scheme == 'https' and target.netloc == 'www.sec.gov' and not target.query and not target.fragment, 'Closed official origin')
        connection = http.client.HTTPSConnection('www.sec.gov', timeout=DEADLINE_SECONDS)
        connection.request('GET', target.path, headers=_sec_headers())
        response = connection.getresponse()
        sender.send(('metadata', {'http_status': response.status, 'requested_url': url, 'final_url': url,
                                  'response_headers_subset': {k: response.getheader(k) for k in ('Content-Type', 'Content-Length', 'Last-Modified', 'ETag', 'Location')}}))
        count = 0
        while count <= max_bytes:
            chunk = response.read1(min(65_536, max_bytes + 1 - count))
            if not chunk: break
            sender.send(('chunk', chunk)); count += len(chunk)
        sender.send(('complete', None))
    except Exception as error:
        # Exception type only: do not emit contact/header/env contents.
        sender.send(('error', type(error).__name__))
    finally:
        if connection is not None: connection.close()
        sender.close()

def _start_transport(url, max_bytes):
    own_version()
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_http_worker, args=(sender, url, max_bytes, LOADED_SOURCE_SHA), daemon=True)
    process.start(); sender.close()
    return process, receiver

def _request_once(url, max_bytes):
    started = time.monotonic(); deadline = started + DEADLINE_SECONDS
    process = receiver = None
    raw = bytearray(); metadata = {}; error = None; completed = False
    try:
        process, receiver = _start_transport(url, max_bytes)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: error = 'TOTAL_REQUEST_DEADLINE_EXCEEDED'; break
            if not receiver.poll(remaining): error = 'TOTAL_REQUEST_DEADLINE_EXCEEDED'; break
            try: kind, value = receiver.recv()
            except EOFError: error = 'TRANSPORT_ENDED_WITHOUT_COMPLETE'; break
            if time.monotonic() >= deadline: error = 'TOTAL_REQUEST_DEADLINE_EXCEEDED'; break
            if kind == 'metadata':
                require(not metadata, 'Repeated response metadata'); metadata = value
            elif kind == 'chunk':
                require(isinstance(value, bytes) and len(value) <= 65_536, 'Bounded transport chunk')
                raw.extend(value)
                if len(raw) > max_bytes: error = 'RESPONSE_BYTE_BOUND_EXCEEDED'; break
            elif kind == 'complete': completed = True; break
            elif kind == 'error': error = 'NETWORK_' + value; break
            else: error = 'UNKNOWN_TRANSPORT_MESSAGE'; break
    except Exception as failure:
        error = 'TRANSPORT_' + type(failure).__name__
    finally:
        if process is not None:
            if process.is_alive(): process.terminate()
            process.join(timeout=1)
            if process.is_alive(): process.kill(); process.join(timeout=1)
        if receiver is not None: receiver.close()
    status = metadata.get('http_status')
    if error is None and not completed: error = 'INCOMPLETE_TRANSPORT'
    if error is None and 300 <= (status or 0) < 400: error = 'REDIRECT_NOT_FOLLOWED'
    if error is None and status != 200: error = 'HTTP_STATUS_NOT_200'
    return dict(raw_bytes=bytes(raw), response=metadata, error=error,
                monotonic_elapsed_seconds=time.monotonic() - started, request_completed=completed)

def capture(*, execute=False):
    if execute is not True:
        return dict(status='NOT_EXECUTED_EXPLICIT_HTTP_AUTHORIZATION_REQUIRED', network_attempt_count=0, **FALSE)
    require(not OUTPUT_ROOT.exists(), 'Create-only capture root already exists')
    safe_path(OUTPUT_ROOT)
    own_version()
    jobs, sources, namespaces = _bound_inputs()
    _guard(sources, namespaces)
    _sec_headers()  # Validate policy before creating an attempt; never print contents.
    require(not OUTPUT_ROOT.exists(), 'Capture root appeared before START')
    OUTPUT_ROOT.mkdir()
    expected_files = {}; expected_directories = set(); results = []; attempted = 0
    def publish(path, value):
        result = save(path, value); expected_files[str(path.relative_to(OUTPUT_ROOT)).replace('\\', '/')] = result['sha256']; return result
    def output_guard():
        require(inventory(OUTPUT_ROOT) == sorted(expected_files), 'Capture namespace drift')
        require({p.relative_to(OUTPUT_ROOT).as_posix() for p in OUTPUT_ROOT.rglob('*') if p.is_dir()} == expected_directories, 'Capture directory inventory drift')
        for path, checksum in expected_files.items(): require(digest((OUTPUT_ROOT / path).read_bytes()) == checksum, 'Capture saved bytes drift')
    try:
        publish(OUTPUT_ROOT / 'started.json', encoded(dict(schema='REMAINING_NINE_SEC_CAPTURE_BATCH_STARTED_V1',
                plan_reference={'path':str(PLAN),'sha256':PLAN_SHA}, local_capture_started_at_utc=clock(),
                source_hashes=sources, namespace_inventories=namespaces, automatic_retry_performed=False, **FALSE)))
        for job in jobs:
            _guard(sources, namespaces); output_guard()
            folder = OUTPUT_ROOT / job['ticker'] / job['accession'].replace('-', '')
            folder.mkdir(parents=True, exist_ok=True)
            expected_directories.update([job['ticker'], folder.relative_to(OUTPUT_ROOT).as_posix()])
            role = job['role']; begin = clock()
            publish(folder / (role + '.started.json'), encoded(dict(schema='SINGLE_SEC_SOURCE_REQUEST_STARTED_V1',
                    job=job, local_request_started_at_utc=begin, attempt_count=1, total_deadline_seconds=DEADLINE_SECONDS,
                    automatic_retry_performed=False, **FALSE)))
            output_guard(); attempted += 1
            logging.info('SEC source attempt %d/%d %s %s', attempted, len(jobs), job['ticker'], role)
            response = _request_once(job['url'], job['max_bytes'])
            raw = response.pop('raw_bytes')
            require(len(raw) <= job['max_bytes'] + 1, 'Parent raw capture bound')
            rawref = publish(folder / (role + '.raw.bin'), raw)
            error = response['error']
            if error is None:
                if role == 'primary' and b'<html' not in raw[:10000].lower(): error = 'EXPECTED_HTML_PRIMARY_NOT_OBSERVED'
                elif role == 'index':
                    try:
                        payload = json.loads(raw)
                        require(isinstance(payload,dict) and isinstance(payload.get('directory',{}).get('item'),list), 'SEC index shape')
                    except (ValueError,TypeError,UnicodeError): error = 'EXPECTED_SEC_INDEX_JSON_NOT_OBSERVED'
            receipt = dict(schema='SINGLE_SEC_SOURCE_REQUEST_RECEIPT_V1', job=job, raw_reference=rawref,
                           raw_byte_count=len(raw), local_request_started_at_utc=begin, local_request_completed_at_utc=clock(),
                           source_available_at_utc=None, response=response, error=error, network_attempt_count=1,
                           redirects_followed=0, automatic_retry_performed=False,
                           status='CAPTURED_PENDING_SOURCE_AND_CONTENT_REVIEW' if error is None else 'FAILED_RAW_BYTES_PRESERVED', **FALSE)
            publish(folder / (role + '.receipt.json'), encoded(receipt)); results.append(receipt)
            if error is not None:
                publish(folder / (role + '.failure.json'), encoded(dict(error=error, raw_reference=rawref, **FALSE)))
                raise ValueError('Request failed; original attempt retained: ' + error)
            _guard(sources,namespaces); output_guard()
        publish(OUTPUT_ROOT / 'result.json', encoded(dict(schema='REMAINING_NINE_SEC_CAPTURE_BATCH_RESULT_V1',
                status='ALL_FIXED_PRIMARY_AND_INDEX_CAPTURES_PENDING_INDEPENDENT_REVIEW', network_attempt_count=attempted,
                complete_receipts=results, attachments_automatically_fetched=0, **FALSE)))
        _guard(sources,namespaces); output_guard()
        return dict(status='CAPTURED_PENDING_REVIEW',network_attempt_count=attempted, **FALSE)
    except Exception as error:
        failure = OUTPUT_ROOT / 'failure.json'
        if not failure.exists(): save(failure,encoded(dict(schema='REMAINING_NINE_SEC_CAPTURE_BATCH_FAILED_V1',
                error_type=type(error).__name__, error=str(error), network_attempt_count=attempted,
                completed_receipt_count=len(results), failed_receipt_count=sum(r['error'] is not None for r in results),
                not_attempted_count=len(jobs)-attempted,
                not_attempted_jobs=jobs[attempted:],
                not_attempted_is_not_a_HTTP_missing_source_result=True,
                local_failure_clock_utc=clock(), retry_allowed=False, **FALSE)))
        raise

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Fixed SEC source-lead capture; explicit approved execution only')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    print(json.dumps(capture(execute=args.execute),ensure_ascii=False))
