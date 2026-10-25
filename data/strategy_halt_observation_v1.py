"""Persist one bounded halt-source observation before interpreting its contents."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL, diagnose_halt_gaps

MAX_BYTES = 2 * 1024 * 1024


def fetch_halts():
    request = Request(SOURCE_URL, headers={'User-Agent': 'us-ratchet-halt-observation/1.0'})
    with urlopen(request, timeout=8) as response:
        return dict(url=response.geturl(), status=response.status,
                    body=response.read(MAX_BYTES + 1))


def capture_halt_observation(*, evidence_root, requests, fetch=fetch_halts, clock=None):
    """Requests contain trusted ticker/session and raw-evidence-derived gaps.

    This performs no quote/order/account operation. Call before obtaining execution
    quotes, never after them: the extra network request must not age a valid order.
    Failure leaves its own receipt and never reuses an old successful observation.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    if not isinstance(requests, list) or not 1 <= len(requests) <= 100:
        raise ValueError('HALT_REQUEST_BUDGET')
    started = clock()
    if started.utcoffset() is None:
        raise ValueError('HALT_AWARE_CLOCK')
    directory = Path(evidence_root) / ('halt-' + uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(schema='HALT_SOURCE_CAPTURE_V1', url=SOURCE_URL,
                   started_at=started.isoformat(), status='FAILED',
                   orders_created=False, account_mutated=False)
    try:
        response = fetch()
        received = clock()
        if response['url'] != SOURCE_URL:
            raise ValueError('HALT_SOURCE_BINDING')
        receipt.update(received_at=received.isoformat(),
                       http_status=response['status'])
        raw = response['body']
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
            raise ValueError('HALT_RAW_BUDGET')
        (directory / 'source.raw').write_bytes(raw)
        receipt.update(bytes=len(raw), raw_sha256=sha256(raw).hexdigest())
        observations = [diagnose_halt_gaps(raw=raw, receipt=receipt, now=clock(),
                                          **item) for item in requests]
        (directory / 'observations.json').write_text(
            json.dumps(observations, ensure_ascii=False, indent=2), encoding='utf-8')
        receipt['status'] = 'OBSERVED_NOT_TRADE_AUTHORIZATION'
        return dict(evidence_directory=str(directory), observations=observations)
    except Exception as error:
        # Do not persist arbitrary upstream error text, URLs or credentials.
        code = str(error) if isinstance(error, ValueError) else ''
        receipt['reason'] = code if code.startswith('HALT_') and code.replace('_', '').isalnum() else 'HALT_OBSERVATION_FAILED'
        raise
    finally:
        (directory / 'receipt.json').write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
