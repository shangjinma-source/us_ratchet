"""Capture halt evidence before fresh marks, retaining independent sell recovery."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from data.strategy_halt_observation_v1 import fetch_halts, MAX_BYTES
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL, require


class HaltMarketCaptureV1:
    def __init__(self, market, *, fetch=fetch_halts, clock=None):
        self.market, self.fetch = market, fetch
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def capture(self, **kwargs):
        directory = Path(kwargs['output_directory'])
        # The underlying capture owns its output directory; use a sibling.
        evidence = directory.with_name(directory.name + '-halts')
        evidence.mkdir(parents=True, exist_ok=False)
        started = self.clock()
        receipt = dict(url=SOURCE_URL, started_at=started.isoformat(), status='FAILED')
        raw = None
        try:
            require(started.utcoffset() is not None, 'HALT_AWARE_CLOCK')
            response = self.fetch()
            received = self.clock()
            require(received.utcoffset() is not None and started <= received, 'HALT_CLOCK_ROLLBACK')
            require(response['url'] == SOURCE_URL, 'HALT_SOURCE_BINDING')
            raw = response['body']
            require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'HALT_RAW_BUDGET')
            (evidence/'source.raw').write_bytes(raw)
            receipt.update(received_at=received.isoformat(), http_status=response['status'],
                           bytes=len(raw), raw_sha256=sha256(raw).hexdigest())
            require(response['status'] == 200, 'HALT_HTTP_STATUS')
            receipt['status'] = 'CAPTURED_PENDING_EXECUTION_REVIEW'
        except Exception as error:
            code = str(error) if isinstance(error, ValueError) else ''
            receipt['reason'] = code if code.startswith('HALT_') and code.replace('_','').isalnum() else 'HALT_CAPTURE_UNAVAILABLE'
        encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()
        (evidence/'receipt.json').write_bytes(encoded)
        # A halt outage does not waive review or discard otherwise valid sells.
        result = self.market.capture(**kwargs)
        if receipt['status'] != 'CAPTURED_PENDING_EXECUTION_REVIEW':
            result['halt_capture_failure'] = receipt['reason']
            return result
        raw_path = 'halt-source/' + sha256(raw).hexdigest() + '.raw'
        receipt_path = 'halt-source/' + sha256(encoded).hexdigest() + '.receipt.json'
        for name, value in ((raw_path, raw), (receipt_path, encoded)):
            require(name not in result['files'] and name not in result['source_hashes'], 'HALT_SOURCE_COLLISION')
            result['files'][name] = value
            result['source_hashes'][name] = sha256(value).hexdigest()
        result['halt_evidence'] = dict(raw_path=raw_path, receipt_path=receipt_path)
        return result
