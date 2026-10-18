"""Inspect saved provider responses for the final historical window; no splice."""
import hashlib
import gzip
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'tmp/historical_official_event_overlay_20261014_v1/corrected_price_coverage.json'
PANEL = ROOT / 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
OUTPUT = ROOT / 'tmp/saved_historical_gap_quotes_20261014_v1'


def main():
    if OUTPUT.exists():
        raise ValueError('Create-only output exists')
    sources = {}

    def read(path):
        raw = path.read_bytes()
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    window = read(INPUT)['dates'][-1]
    calendar = read(PANEL)['calendar']
    required = [d for d in calendar if window['next21_first'] <= d <= window['next21_last']]
    assert len(required) == 21
    index = {}
    for folder in sorted((ROOT / 'data/cache/research').glob('provider_gap*capture*')):
        manifest_path = folder / 'manifest.json'
        if not manifest_path.exists():
            continue
        manifest = read(manifest_path)
        for probe in manifest.get('probes', []):
            index.setdefault(probe['ticker'], []).append((folder, probe))
    results = []
    for ticker in window['missing_next21_tickers']:
        attempts = []
        for folder, probe in index.get(ticker, []):
            path = folder / (ticker + '.response.bin')
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            assert digest == probe['response_sha256'], ticker
            sources[str(path.relative_to(ROOT))] = digest
            decoded = gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw
            assert hashlib.sha256(decoded).hexdigest() == probe['decoded_sha256'], ticker
            payload = json.loads(decoded)
            chart = payload['chart']
            item = dict(path=str(path.relative_to(ROOT)), sha256=digest,
                        provider_error=chart.get('error'), complete=False)
            if chart.get('result'):
                assert len(chart['result']) == 1
                result = chart['result'][0]
                meta = result['meta']
                assert meta['symbol'].upper() == ticker
                assert meta['currency'] == 'USD'
                timezone = ZoneInfo(meta['exchangeTimezoneName'])
                quotes = result['indicators']['quote'][0]
                timestamps = result['timestamp']
                assert all(len(quotes[key]) == len(timestamps) for key in ('open','high','low','close'))
                rows = {}
                for i, timestamp in enumerate(timestamps):
                    day = datetime.fromtimestamp(timestamp, timezone).date().isoformat()
                    assert day not in rows
                    rows[day] = {key: quotes[key][i] for key in ('open','high','low','close')}
                valid, missing = {}, []
                for day in required:
                    row = rows.get(day)
                    if row is None or not all(type(v) in (int,float) and math.isfinite(v) and v > 0 for v in row.values()):
                        missing.append(day)
                        continue
                    assert row['low'] <= min(row['open'],row['close']) <= max(row['open'],row['close']) <= row['high']
                    valid[day] = row
                item.update(complete=not missing, missing_dates=missing, rows=valid,
                            metadata={key:meta.get(key) for key in ('symbol','currency','exchangeName','exchangeTimezoneName','instrumentType')},
                            first_observed=min(rows), last_observed=max(rows),
                            quote_basis='PROVIDER_QUOTE_OHLC_NOT_ADJCLOSE_NOT_AUTHENTICATED',
                            returned_splits=result.get('events',{}).get('splits',{}))
            attempts.append(item)
        results.append(dict(ticker=ticker, complete_saved_quote_window=any(a['complete'] for a in attempts), attempts=attempts))
    report = dict(status='COMPLETE_SAVED_RESPONSE_WINDOW_INSPECTION', decision=window['decision_cutoff'],
                  required_dates=required, rows=results, source_hashes=sources,
                  complete_tickers=[r['ticker'] for r in results if r['complete_saved_quote_window']],
                  unresolved_tickers=[r['ticker'] for r in results if not r['complete_saved_quote_window']],
                  mixed_price_sources_spliced=False, strategy_calls=0, network_calls=0,
                  identity_and_adjustment_authenticated=False)
    for relative, digest in sources.items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() == digest
    OUTPUT.mkdir()
    (OUTPUT/'result.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('complete_tickers','unresolved_tickers')}))


if __name__ == '__main__':
    main()
