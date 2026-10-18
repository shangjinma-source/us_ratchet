"""Three complete returned regular-date segments; conditional quotes, no returns."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_current_regular_segment_quote_research as module
from scripts.ndx_current_22_price_capture_20260919 import save


def build(ticker):
    guard = module.original
    folder = guard.BASE / 'current_22_price_capture_20260919_v1'
    receipt = json.loads((folder / (ticker + '.receipt.json')).read_bytes())
    sources = {}
    raw, receipt, _, _ = guard.load_capture(ticker=ticker, raw_path=receipt['raw_path'],
                                           raw_sha256=receipt['raw_sha256'], sources=sources)
    body = json.loads(raw)['chart']['result'][0]
    dates = [datetime.fromtimestamp(t, timezone.utc).astimezone(guard.nominal.NEW_YORK).date().isoformat()
             for t in body['timestamp']]
    calendar = [day for day in dates if module.FLOORS[ticker] <= day < receipt['completed_training_excludes_dates_on_or_after']]
    report = module.reconstruct_regular_segment_quote(ticker=ticker, raw_path=receipt['raw_path'],
        raw_sha256=receipt['raw_sha256'], calendar=calendar, quote_field_basis=guard.nominal.BASIS)
    quotes = body['indicators']['quote'][0]
    positions = {day: index for index, day in enumerate(dates)}
    error = Decimal(0)
    with localcontext() as context:
        context.prec = 50
        for row in report['reconstruction']['rows']:
            factor = Decimal(1)
            for event in body.get('events', {}).get('splits', {}).values():
                day = datetime.fromtimestamp(event['date'], timezone.utc).astimezone(guard.nominal.NEW_YORK).date().isoformat()
                if day > row['session']:
                    factor *= Decimal(str(event['numerator'])) / Decimal(str(event['denominator']))
            for field in ('open', 'close'):
                expected = Decimal(str(quotes[field][positions[row['session']]])) * factor
                difference = abs(expected - Decimal(str(row['nominal_' + field])))
                if difference > Decimal('1e-10'):
                    raise ValueError('Independent Decimal regular quote differs')
                error = max(error, difference)
    report.update(calendar_source='ALL_RETURNED_PROVIDER_DATES_WITHIN_EXPLICIT_REGULAR_FLOOR_AND_COMPLETED_RECEIPT_BOUNDARY',
                  complete_exchange_calendar_verified=False, independent_decimal_quote_check_count=len(calendar) * 2,
                  independent_decimal_max_absolute_error=str(error), training_performed=False)
    expected = report['historical_expected_source_hashes']
    guard.gap.merge(expected, sources)
    source = Path(__file__).resolve()
    guard.gap.merge(expected, {str(source): hashlib.sha256(source.read_bytes()).hexdigest()})
    return guard.gap.attach_partition(report, expected, guard.gap.partition(expected, guard.gap.drift.load_contract(), require_all=True))


if __name__ == '__main__':
    output = module.original.BASE / 'current_regular_segment_quote_probe_20260919_v1'
    output.mkdir(exist_ok=False)
    entries = []
    for ticker in module.FLOORS:
        report = build(ticker)
        path = output / (ticker + '.json')
        digest = save(path, report)
        module.original.gap.partition(report['historical_expected_source_hashes'], module.original.gap.drift.load_contract(), require_all=True)
        entry = dict(ticker=ticker, path=str(path), sha256=digest,
                     rows=report['reconstruction']['row_count'], max_error=report['independent_decimal_max_absolute_error'])
        entries.append(entry)
        print(json.dumps(entry), flush=True)
    path = output / 'index.json'
    digest = save(path, dict(schema='THREE_REGULAR_CONDITIONAL_QUOTES_V1', entries=entries,
                            price_identity_verified=False, point_in_time_verified=False, promotion_allowed=False))
    print(json.dumps(dict(path=str(path), sha256=digest)))
