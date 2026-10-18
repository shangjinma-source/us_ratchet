"""Prepare a review-only service input from frozen99 data; never run a search."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import gzip
import json
from pathlib import Path

from data.current_research_ohlc_panel import parse_provider_ohlc


def prepare(*, root, prepared_path, expected_sha256, output):
    root = Path(root).resolve()
    raw = (root / prepared_path).read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('PREPARED_HASH_MISMATCH')
    prepared = json.loads(raw)
    arguments = deepcopy(prepared['search_arguments'])
    if prepared['status'] != 'READY_CONDITIONAL' or len(arguments['prices']) != 99:
        raise ValueError('EXPECTED_FROZEN99_DOMAIN')
    pins = dict(prepared['source_hashes'])
    pins[prepared_path] = expected_sha256
    # Verify every historical provenance file before producing a new binding.
    for name, expected in pins.items():
        if sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_HASH_MISMATCH:' + name)
    basis = 'CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN'
    arguments.update(quote_as_of=arguments['decision_date'], price_basis=basis)
    quotes, sources, checks = [], {}, []
    for sid, price in arguments['prices'].items():
        ticker = arguments['metadata'][sid]['ticker']
        name = 'data/cache/research/current_raw_capture_20261014_v1/' + ticker + '.response.bin'
        if name not in pins:
            raise ValueError('NO_PINNED_DAILY_SOURCE:' + ticker)
        encoded = (root / name).read_bytes()
        if sha256(encoded).hexdigest() != pins[name]:
            raise ValueError('DAILY_SOURCE_CHANGED:' + ticker)
        channel = parse_provider_ohlc(encoded, ticker)
        index = channel['dates'].index(arguments['decision_date'])
        decoded = json.loads(gzip.decompress(encoded) if encoded[:2] == b'\x1f\x8b' else encoded, parse_float=Decimal)
        row = decoded['chart']['result'][0]['indicators']['quote'][0]
        opened, high, low, close = [row[key][index] for key in ('open', 'high', 'low', 'close')]
        if (any(value is None or value <= 0 for value in (opened, high, low, close))
                or not low <= min(opened, close) <= max(opened, close) <= high
                or Fraction(close) != Fraction(price)):
            raise ValueError('DECISION_PRICE_COORDINATE_MISMATCH:' + ticker)
        sources[sid] = dict(path=name, price_basis=basis)
        quotes.append(dict(security_id=sid, as_of=arguments['decision_date'],
                           price=price, price_basis=basis, source_references=[name]))
        checks.append(dict(ticker=ticker, decision_close_exact=str(Fraction(close))))
    directory = root / output
    directory.mkdir()
    payload = dict(search_arguments=arguments, valuation_quotes=quotes, bar_sources=sources)
    with (directory / 'input.json').open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
    receipt = dict(status='DRAFT_REQUIRES_SERVICE_SOURCE_REVIEW', admission_granted=False,
                   source_hashes=pins, checks=checks, search_calls=0, book_calls=0,
                   input_sha256=sha256((directory / 'input.json').read_bytes()).hexdigest(),
                   limitations=['Historical conditional prices only; no live order instruction.',
                                'Full point-in-time universe and economic total return not established.'])
    with (directory / 'receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    return receipt
