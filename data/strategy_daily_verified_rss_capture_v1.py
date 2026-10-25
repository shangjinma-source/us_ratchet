"""Real-clock RSS metadata wait with original item-time checks and saved audit."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import capture_session as original_capture, stamp
from data.strategy_rss_verified_transport_v1 import VerifiedRssTransportV1
from scripts.current_research_official_alert_capture import fetch_official_feed, parse_official_feed


def capture_session(*, root, configuration_bytes, configuration_sha256, execute=False,
                    fetch_daily=None, fetch_official=None, clock=None, sleep=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    records = []
    def sink(evidence, raw):
        require(not records, 'DAILY_RSS_TIMING_DUPLICATE')
        records.append((deepcopy(evidence), raw))
        feed = parse_official_feed(raw, observed_at=stamp(evidence['transport_received_at']))
        require(all(row['future_publication'] is False and row['publication_time_issue'] is None
                    for row in feed['items']), 'DAILY_RSS_ITEM_TIME_REVIEW')
    adapter = VerifiedRssTransportV1(fetch=fetch_official or fetch_official_feed,
                                   sink=sink, clock=clock, sleep=sleep)
    result = original_capture(root=root, configuration_bytes=configuration_bytes,
        configuration_sha256=configuration_sha256, execute=execute, fetch_daily=fetch_daily,
        fetch_official=adapter, clock=clock)
    if not records:
        return result
    output = Path(result['output'])
    evidence, raw = records[0]
    def save(name, body):
        with (output/name).open('xb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
        require((output/name).read_bytes() == body, 'DAILY_RSS_AUDIT_READBACK')
    save('official.transport.response.bin', raw)
    save('official.transport.json', canonical(evidence))
    if result['status'] != 'CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED':
        return result
    capture_raw = (output/'official.response.bin').read_bytes()
    capture_receipt_raw = (output/'official.receipt.json').read_bytes()
    receipt = json.loads(capture_receipt_raw)
    require(raw == capture_raw and sha256(raw).hexdigest() == evidence['raw_sha256']
            == receipt['raw_sha256'], 'DAILY_RSS_AUDIT_RAW')
    now = stamp(clock())
    require(stamp(evidence['transport_received_at']) <= stamp(evidence['verified_at'])
            <= stamp(receipt['received_at']) <= stamp(result['finished_at']) <= now,
            'DAILY_RSS_AUDIT_CLOCK')
    binding = dict(schema='DAILY_RSS_TRANSPORT_BINDING_V1', transport=evidence,
        capture_receipt_sha256=sha256(capture_receipt_raw).hexdigest(),
        capture_received_at=receipt['received_at'], raw_sha256=evidence['raw_sha256'])
    save('official.timing.json', canonical(binding))
    return result


def attach_timing(*, reviewed, capture_files):
    """Extend the reviewed closure only after replaying actual receipt bindings."""
    require(reviewed.get('receipt') is not None, 'DAILY_RSS_REVIEW_REQUIRED')
    raw = capture_files['official.timing.json']; value = json.loads(raw)
    transport = value['transport']
    receipt = json.loads(capture_files['official.receipt.json'])
    require(value['schema'] == 'DAILY_RSS_TRANSPORT_BINDING_V1'
            and value['capture_receipt_sha256'] == sha256(capture_files['official.receipt.json']).hexdigest()
            and value['raw_sha256'] == transport['raw_sha256']
            == sha256(capture_files['official.response.bin']).hexdigest()
            and value['capture_received_at'] == receipt['received_at']
            and transport['status'] == 'VERIFIED_BEFORE_CAPTURE_RETURN'
            and transport['raw_modified'] is False,
            'DAILY_RSS_TIMING_BINDING')
    arrived, verified = stamp(transport['transport_received_at']), stamp(transport['verified_at'])
    require(arrived <= verified <= stamp(receipt['received_at']), 'DAILY_RSS_TIMING_ORDER')
    feed = parse_official_feed(capture_files['official.response.bin'], observed_at=arrived)
    published = stamp(feed['channel']['published_at_utc'])
    require(feed['channel']['publication_time_issue'] is None and (published-arrived).total_seconds() <= 1
            and published <= verified and (published <= arrived or (verified-arrived).total_seconds() <= 2)
            and all(row['future_publication'] is False and row['publication_time_issue'] is None
                    for row in feed['items']), 'DAILY_RSS_TIMING_REVIEW')
    result = deepcopy(reviewed)
    name = 'daily-rss-timing/'+sha256(raw).hexdigest()+'.json'
    result['files'][name] = raw
    result['receipt']['source_sha256'][name] = sha256(raw).hexdigest()
    require(len(result['files']) <= 2000 and sum(map(len,result['files'].values())) <= 32*1024*1024,
            'DAILY_RSS_CLOSURE_BUDGET')
    return result
