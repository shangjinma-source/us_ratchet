"""Read explicit byte-bound nominal execution closes, never adjusted returns."""
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import re

import pandas as pd

_SOURCE = Path(__file__).resolve()
_LOADED_SOURCE_SHA256 = hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def load_execution_nominal_bundle(*, inventory_path, expected_inventory_sha256,
                                  tickers, execution_calendar):
    """Preserve the exact requested ticker/calendar set with no fill or pruning.

    The inventory may contain other securities. Caller-provided hashes prove
    local consistency, not authenticity or corporate-action completeness.
    """
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def digest_valid(value):
        return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None

    require(isinstance(tickers, (list, tuple)) and tickers
            and all(type(t) is str and t and t.strip() == t for t in tickers)
            and len(set(tickers)) == len(tickers), 'Explicit unique ticker list required')
    require(isinstance(execution_calendar, pd.DatetimeIndex) and len(execution_calendar) > 0
            and execution_calendar.tz is None and not execution_calendar.hasnans
            and execution_calendar.is_unique and execution_calendar.is_monotonic_increasing
            and execution_calendar.equals(execution_calendar.normalize()), 'Invalid complete execution calendar')
    require(hashlib.sha256(_SOURCE.read_bytes()).hexdigest() == _LOADED_SOURCE_SHA256, 'Loader source changed since import')
    observed = {}

    def read(path, expected):
        require(digest_valid(expected), 'Invalid expected SHA256')
        path = Path(path).resolve()
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, 'Source SHA256 mismatch: '+str(path))
        require(path not in observed or observed[path] == expected, 'Inconsistent source reference')
        observed[path] = expected
        return raw

    def table(raw, required):
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        require(rows and rows[0] and len(set(rows[0])) == len(rows[0])
                and all(column and column == column.strip() for column in rows[0]), 'Duplicate/invalid CSV columns')
        require(set(required) <= set(rows[0]), 'Missing required CSV columns')
        require(all(len(row) == len(rows[0]) for row in rows[1:]), 'Malformed CSV row')
        return [dict(zip(rows[0], row)) for row in rows[1:]]

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result

    inventory_path = Path(inventory_path).resolve()
    inventory = table(read(inventory_path, expected_inventory_sha256),
                      ('ticker', 'status', 'path', 'sha256', 'sidecar_path', 'sidecar_sha256'))
    require(inventory and all(row['ticker'] and row['ticker'].strip() == row['ticker'] for row in inventory), 'Invalid inventory ticker')
    require(len({r['ticker'] for r in inventory}) == len(inventory), 'Duplicate inventory ticker')
    by_ticker = {row['ticker']: row for row in inventory}
    require(set(tickers) <= set(by_ticker), 'Requested ticker coverage incomplete')
    columns, evidence = {}, []
    for ticker in tickers:
        row = by_ticker[ticker]
        require(row['status'] == 'FETCHED', 'Inventory member not fetched')
        require(Path(row['path']).is_absolute() and Path(row['sidecar_path']).is_absolute(), 'Absolute inventory source paths required')
        raw = read(row['path'], row['sha256'])
        sidecar = json.loads(read(row['sidecar_path'], row['sidecar_sha256']).decode('utf-8-sig'),
                            object_pairs_hook=unique_object)
        require(isinstance(sidecar, dict) and sidecar.get('dataset_key') == ticker
                and sidecar.get('content_sha256') == row['sha256']
                and sidecar.get('price_basis') == 'unadjusted_nominal_trade_price'
                and sidecar.get('whole_lot_execution_use_only') is True
                and sidecar.get('return_usage_allowed') is False
                and sidecar.get('corporate_action_adjustment') == 'none', 'Nominal sidecar semantics mismatch')
        bars = table(raw, ('Date', 'Close'))
        require(bars, 'Empty nominal price source')
        dates, closes = [], []
        for bar in bars:
            value = bar['Date']
            require(date.fromisoformat(value).isoformat() == value, 'Noncanonical daily Date')
            dates.append(pd.Timestamp(value))
            close = float(bar['Close'])
            require(math.isfinite(close) and close > 0, 'Close must be finite and positive')
            closes.append(close)
        calendar = pd.DatetimeIndex(dates)
        require(calendar.is_unique and calendar.is_monotonic_increasing, 'Duplicate or unsorted nominal Date')
        require(execution_calendar.isin(calendar).all(), 'Nominal calendar coverage incomplete: '+ticker)
        # When descriptive counts/ranges are present, they must match the same
        # parsed bytes, not a different cached version.
        for field, expected in (('row_count', len(bars)), ('data_start', bars[0]['Date']), ('data_end', bars[-1]['Date'])):
            if field in sidecar:
                require(type(sidecar[field]) is type(expected) and sidecar[field] == expected, 'Sidecar range/count mismatch')
        columns[ticker] = pd.Series(closes, index=calendar).loc[execution_calendar].to_numpy()
        evidence.append(dict(ticker=ticker, path=str(Path(row['path']).resolve()), sha256=row['sha256'],
            sidecar_path=str(Path(row['sidecar_path']).resolve()), sidecar_sha256=row['sidecar_sha256'],
            source_rows=len(bars), selected_rows=len(execution_calendar),
            price_basis=sidecar['price_basis'], corporate_action_adjustment='none'))
    prices = pd.DataFrame(columns, index=execution_calendar)
    for path, expected in observed.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Source changed during bundle load')
    require(hashlib.sha256(_SOURCE.read_bytes()).hexdigest() == _LOADED_SOURCE_SHA256, 'Loader source changed during load')
    return dict(schema='ndx_execution_nominal_bundle_research_v1', prices=prices,
        evidence=evidence, inventory_path=str(inventory_path), inventory_sha256=expected_inventory_sha256,
        loader_source_sha256=_LOADED_SOURCE_SHA256, requested_tickers=list(tickers),
        date_start=str(execution_calendar[0].date()), date_end=str(execution_calendar[-1].date()),
        all_requested_tickers_and_sessions_present=True, forward_fill_performed=False,
        external_authenticity_verified=False, corporate_action_coverage_verified=False,
        execution_calendar_authenticity_verified=False, return_usage_allowed=False,
        promotion_allowed=False, order_generation_allowed=False)
