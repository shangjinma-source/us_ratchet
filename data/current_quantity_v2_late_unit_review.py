"""Bounded public screening for late historical minutes, never action certification.

Capture uses real interval action and RSS transports by default. Replay performs
no I/O except the supplied pinned-byte reader and never requires a fresh quote.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import html
import re
import xml.etree.ElementTree as ET

from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources, daily_url
from data.current_quantity_v2_paper_ledger import digest
from data.current_quantity_v2_bounded_unit_review import _quote
from data.current_quantity_v2_difference_plan import require, stamp
from scripts.current_research_official_alert_capture import parse_official_feed, URL

STATUS = 'NO_KNOWN_UNIT_CHANGE_UNDER_BOUNDED_PUBLIC_REVIEW'
POLICY = 'BOUNDED_LATE_CAPTURE_PUBLIC_ACTIONS_V1'
ERROR = 'LATE_UNIT_REVIEW_UNAVAILABLE'
CANDIDATE = 'LATE_UNIT_CHANGE_CANDIDATE'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def replay(review, *, reference, capture_raw_sha256, captured_at, observed_at, read):
    """Recompute status from pinned raw evidence; hashes are not authentication."""
    try:
        captured, observed = stamp(captured_at), stamp(observed_at)
        old = stamp(reference['captured_at']); evidence = review['bounded_evidence']
        require(review['status'] == STATUS and evidence['policy'] == POLICY, ERROR)
        require(review['security_id'] == reference['security_id'] and review['ticker'] == reference['ticker']
                and review['price_basis'] == reference['price_basis']
                and review['reference_sha256'] == digest(reference)
                and review['reference_source_hashes'] == reference['source_hashes']
                and review['capture_raw_sha256'] == capture_raw_sha256
                and stamp(review['covered_from']) == old
                and stamp(review['covered_through']) == captured
                and old <= captured <= stamp(review['reviewed_at']) <= observed, ERROR)
        pins = evidence['source_hashes']; paths = review['source_references']
        require(type(pins) is dict and 0 < len(pins) <= 2000 and type(paths) is list
                and len(paths) == len(set(paths)) and set(paths) == set(pins), ERROR)
        files = {}; total = 0
        for path in paths:
            require(type(path) is str and bool(path), ERROR)
            raw = read(path); total += len(raw)
            require(type(raw) is bytes and len(raw) <= 4*1024*1024
                    and total <= 128*1024*1024 and sha256(raw).hexdigest() == pins[path], ERROR)
            files[path] = raw
        require(all(pins.get(p) == h for p,h in reference['source_hashes'].items()), ERROR)
        _quote(files, reference['source_hashes'],
               {'security_id':reference['security_id'], 'ticker':reference['ticker']}, old, observed, False)
        raw = files[evidence['capture_raw_path']]
        require(sha256(raw).hexdigest() == capture_raw_sha256, ERROR)
        current = json.loads(raw)['chart']['result'][0]
        def chart_ok(chart):
            meta = chart['meta']
            require(meta['symbol'] == reference['ticker'] and meta['currency'] == 'USD'
                    and meta['instrumentType'] == 'EQUITY', ERROR)
            require(not any(v for k,v in chart.get('events', {}).items() if k != 'dividends'), CANDIDATE)
            return meta
        chart_ok(current)
        receipt = json.loads(files[evidence['action_receipt_path']])
        start, end = stamp(receipt['requested_from']), stamp(receipt['requested_through'])
        received = stamp(receipt['received_at'])
        require(receipt['security_id'] == reference['security_id'] and receipt['ticker'] == reference['ticker']
                and receipt['http_status'] == 200 and receipt['body_truncated'] is False
                and receipt['transport_error'] is None and receipt['events_requested'] == ['dividends','splits']
                and receipt['interval'] == '1d' and start <= old <= captured <= end <= received
                and receipt['request_period1'] == int(start.timestamp())
                and receipt['request_period2'] == int(end.timestamp())+1
                and receipt['url'] == daily_url(reference['ticker'], start, end), ERROR)
        daily_raw = files[receipt['raw_path']]
        require(sha256(daily_raw).hexdigest() == receipt['raw_sha256'], ERROR)
        daily = json.loads(daily_raw)['chart']
        require(daily.get('error') is None and len(daily['result']) == 1, ERROR)
        meta = chart_ok(daily['result'][0])
        rss_receipt = json.loads(files[evidence['rss_receipt_path']]); rss = files[evidence['rss_raw_path']]
        rss_at = stamp(rss_receipt['received_at'])
        require(rss_receipt['url'] == URL and rss_receipt['http_status'] == 200
                and rss_receipt['raw_sha256'] == sha256(rss).hexdigest()
                and rss_receipt['stored_bytes'] == len(rss)
                and received <= stamp(rss_receipt['started_at']) <= rss_at <= stamp(review['reviewed_at']), ERROR)
        feed = parse_official_feed(rss, observed_at=rss_at)
        require(not feed['channel']['publication_time_issue']
                and feed['channel']['future_publication'] is not True
                and all(not item['publication_time_issue'] and item['future_publication'] is False
                        for item in feed['items']), ERROR)
        names = [meta[k].strip() for k in ('longName','shortName')
                 if isinstance(meta.get(k),str) and len(meta[k].strip()) >= 2]
        def normalized(value):
            return ' '.join(re.sub(r'<[^>]*>', ' ', html.unescape(value)).split())
        for item in ET.fromstring(rss).iter():
            if item.tag.rsplit('}',1)[-1] != 'item': continue
            text = normalized(' '.join(item.itertext()))
            require(not any(re.search(r'(?<![A-Za-z0-9])'+re.escape(term)+r'(?![A-Za-z0-9])', text, re.I)
                            for term in map(normalized, [reference['ticker']]+names)), CANDIDATE)
        return dict(policy=POLICY, status=STATUS, coverage_complete=False, source_authenticated=False,
                    retention_unknown=True, limited_name_coverage=not bool(names),
                    limitations=['Public sources may omit actions; no match is not proof of no unit changes.'])
    except ValueError as error:
        if str(error) in (ERROR, CANDIDATE): raise
        raise ValueError(ERROR) from error
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError(ERROR) from error


class BoundedLateUnitReview:
    def __init__(self, *, action_sources=None, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sources = action_sources or PaperActionEvidenceSources(clock=self.clock)

    def capture(self, *, reference, capture_raw, captured_at, origin_files, account_id, state_revision):
        """Return bytes for caller archival, never a fabricated human review file."""
        captured = stamp(captured_at); now = stamp(self.clock())
        require(type(capture_raw) is bytes and 0 < len(capture_raw) <= 4*1024*1024
                and stamp(reference['captured_at']) <= captured <= now, ERROR)
        sid = reference['security_id']
        package = self.sources.capture(dict(account_id=account_id, state_revision=state_revision,
            window_start=reference['captured_at'], observed_floor=captured.isoformat(),
            securities={sid:{'ticker':reference['ticker']}}, current_target_quantities={}))
        files = dict(package['files'])
        for path, h in reference['source_hashes'].items():
            raw = origin_files[path]
            require(type(raw) is bytes and sha256(raw).hexdigest() == h
                    and (path not in files or files[path] == raw), ERROR)
            files[path] = raw
        raw_hash = sha256(capture_raw).hexdigest(); raw_path = 'late-review/'+raw_hash+'.raw'
        require(raw_path not in files or files[raw_path] == capture_raw, ERROR)
        files[raw_path] = capture_raw
        pins = {p:sha256(raw).hexdigest() for p,raw in files.items()}
        reviewed = stamp(self.clock()); docs = package['documents']
        review = dict(security_id=sid, ticker=reference['ticker'], price_basis=reference['price_basis'],
            status=STATUS, reference_sha256=digest(reference), reference_source_hashes=reference['source_hashes'],
            capture_raw_sha256=raw_hash, covered_from=reference['captured_at'], covered_through=captured.isoformat(),
            reviewed_at=reviewed.isoformat(), source_references=sorted(pins), bounded_evidence=dict(policy=POLICY,
                source_hashes=pins, capture_raw_path=raw_path, action_receipt_path=docs['action_receipts'][sid],
                rss_raw_path=docs['rss_raw'], rss_receipt_path=docs['rss_receipt']))
        replay(review, reference=reference, capture_raw_sha256=raw_hash, captured_at=captured,
               observed_at=reviewed, read=files.__getitem__)
        path = 'late-review/'+digest(review)+'.json'; files[path] = canonical(review)
        return dict(files=files, source_hashes={p:sha256(raw).hexdigest() for p,raw in files.items()}, review_path=path)
