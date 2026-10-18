"""Fixed raw OHLCV alignment to the sealed close panel; no HTTP or publication."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import io
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from data import current_research_close_panel as close

FIELDS = ('open', 'high', 'low', 'close', 'volume')
HELPER_SHA = '5ebacf528557a869b28b532b79852964b0ed6d1865c553626618284b34c3841d'
SEALED_CLOSE = close.ROOT / 'tmp/price_predictor_fixed_calibration_actual_20261013_v1/extracted_close_panel.json'
SEALED_CLOSE_SHA = '65ce032b4d1da0f40b8983f91e5ce9c852a82c54764335dc734d3428b7a75db2'


def _validate_ohlcv_row(row):
    if type(row) is not list or len(row) != 5:
        raise ValueError('five actual provider fields required')
    for field,value in zip(FIELDS,row):
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)
                or value < 0 or (field != 'volume' and value == 0)):
            raise ValueError('nonfinite/invalid actual OHLCV')
    opened,high,low,closed,_ = row
    if low is not None and high is not None and low > high:
        raise ValueError('actual high is below actual low')
    for value in (opened,closed):
        if value is not None and ((low is not None and value < low)
                or (high is not None and value > high)):
            raise ValueError('actual open/close outside known low/high')


def parse_provider_ohlc(raw: bytes, ticker: str) -> dict:
    """Pure actual provider fields. Missing values remain None, not fabricated bars."""
    if type(raw) is not bytes or len(raw) > close.MAX_BYTES:
        raise ValueError('bounded raw bytes required')
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
            decoded = source.read(close.MAX_BYTES + 1)
    else:
        decoded = raw
    if len(decoded) > close.MAX_BYTES:
        raise ValueError('bounded decoded body required')
    chart = close._loads(decoded)['chart']
    if chart.get('error') is not None or len(chart.get('result') or []) != 1:
        raise ValueError('one successful provider result required')
    channel = chart['result'][0]
    meta = channel['meta']
    expected = dict(symbol=ticker,currency='USD',instrumentType='ETF' if ticker in ('QQQ','SPY') else 'EQUITY',
                    exchangeTimezoneName='America/New_York',dataGranularity='1d')
    if any(meta.get(key) != value for key,value in expected.items()):
        raise ValueError('provider symbol/USD/instrument/timezone/granularity differs')
    stamps = channel['timestamp']
    if (type(stamps) is not list or not 1 <= len(stamps) <= 20_000
            or any(type(stamp) is not int or stamp <= 0 for stamp in stamps)
            or stamps != sorted(set(stamps))):
        raise ValueError('ordered unique integer timestamps required')
    dates = [datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
             for stamp in stamps]
    if dates != sorted(set(dates)):
        raise ValueError('ordered unique New York dates required')
    quotes = channel['indicators']['quote']
    if len(quotes) != 1 or any(type(quotes[0].get(field)) is not list or len(quotes[0][field]) != len(dates) for field in FIELDS):
        raise ValueError('actual OHLCV dimensions differ')
    values = [list(row) for row in zip(*(quotes[0][field] for field in FIELDS))]
    for row in values:
        _validate_ohlcv_row(row)
    events = channel.get('events',{})
    if type(events) is not dict or set(events)-{'splits','dividends'}:
        raise ValueError('unknown provider event family')
    if any(type(events.get(kind,{})) is not dict for kind in ('splits','dividends')):
        raise ValueError('event maps required')
    return dict(ticker=ticker,dates=dates,values=values,raw_sha256=close._digest(raw),
                decoded_sha256=close._digest(decoded),events_sha256=close._digest(close._canonical(events)))


def bind_ohlc_panel(*, sealed_close: dict, channels: dict) -> dict:
    """Pure compact alignment. Association is value equality, not new qualification."""
    if any(sealed_close.get(field) is not False for field in close.FALSE_FLAGS):
        raise ValueError('supplied close authority flags must remain false')
    calendar = sealed_close['calendar'];target = sealed_close['target']
    if (type(calendar) is not list or not 2 <= len(calendar) <= 20_000
            or calendar != sorted(set(calendar)) or calendar[-1] != target):
        raise ValueError('sealed observed calendar/target differs')
    for day in calendar:
        if type(day) is not str or datetime.fromisoformat(day).date().isoformat() != day:
            raise ValueError('exact ISO calendar date required')
    stocks = sealed_close['stocks'];controls = sealed_close['controls']
    if (not stocks or len(stocks) > 101 or [row['ticker'] for row in controls] != list(close.CONTROLS)
            or any(row['ticker'] in close.CONTROLS for row in stocks)):
        raise ValueError('stock/control separation differs')
    names = [row['ticker'] for row in stocks+controls]
    if len(set(names)) != len(names) or set(channels) != set(names):
        raise ValueError('exact unique stock/control channel set required')
    def align(saved):
        ticker = saved['ticker'];channel = channels[ticker]
        if (channel['ticker'] != ticker or len(channel['dates']) != len(channel['values'])
                or channel['dates'] != sorted(set(channel['dates']))
                or len(saved['raw_close']) != len(calendar)):
            raise ValueError('input channel/calendar dimensions differ')
        for day in channel['dates']:
            if type(day) is not str or datetime.fromisoformat(day).date().isoformat() != day:
                raise ValueError('exact ISO provider session required')
        for row in channel['values']:
            _validate_ohlcv_row(row)
        by_date = dict(zip(channel['dates'],channel['values']))
        aligned = [list(by_date[day]) if day in by_date else [None]*5 for day in calendar]
        for index,row in enumerate(aligned):
            if type(row[3]) is not type(saved['raw_close'][index]) or row[3] != saved['raw_close'][index]:
                raise ValueError('raw CLOSE differs from sealed close panel at '+ticker+' '+calendar[index])
        missing = {field:sum(row[index] is None for row in aligned) for index,field in enumerate(FIELDS)}
        return dict(ticker=ticker,values=aligned,missing_field_counts=missing,
                    missing_open_indices=[index for index,row in enumerate(aligned) if row[0] is None],
                    missing_provider_dates=[day for day in calendar if day not in by_date],
                    excluded_future_dates=[day for day in channel['dates'] if day > target],
                    close_matches_sealed_values=True,
                    raw_reference={key:channel[key] for key in ('raw_sha256','decoded_sha256','events_sha256')},
                    old_coordinate_risk_and_gap_reference=saved.get('old_coordinate_risk_and_gap_reference'),
                    **close.FALSE_FLAGS)
    return dict(schema='CURRENT_CONDITIONAL_PROVIDER_OHLCV_PANEL_V1',target=target,calendar=list(calendar),
                fields=list(FIELDS),stocks=[align(row) for row in stocks],
                controls=[dict(align(row),role='REFERENCE_ONLY_NEVER_TRAIN') for row in controls],
                value_shape='PER_CHANNEL_CALENDAR_BY_FIVE_PROVIDER_FIELDS',
                price_basis='CONDITIONAL_PROVIDER_RETURNED_OHLC_NOT_AUTHENTICATED_SPLIT_ADJUSTED',
                economic_total_return_basis='NOT_MODELED',open_execution_authorized=False,
                close_association_scope='SUPPLIED_CLOSE_OBJECT_VALUE_EQUALITY_ONLY',
                no_missing_fill=True,no_date_compression=True,no_sid_created=True,
                **close.FALSE_FLAGS)


def load_current_ohlc_panel(*, execute=False) -> dict:
    if type(execute) is not bool:
        raise ValueError('execute must be boolean')
    references = dict(sealed_close=dict(path=str(SEALED_CLOSE),sha256=SEALED_CLOSE_SHA),
                      final_index=dict(path=str(close.FIXED_REFERENCES['final_index'][0]),sha256=close.FIXED_REFERENCES['final_index'][1]),
                      independent_readback=dict(path=str(close.FIXED_REFERENCES['independent_readback'][0]),sha256=close.FIXED_REFERENCES['independent_readback'][1]),
                      helper=dict(path=str(Path(close.__file__)),sha256=HELPER_SHA))
    if not execute:
        return dict(status='PREPARED_NOT_EXTRACTED',fixed_references=references,source_files_read=0,
                    stock_channel_count=101,control_channel_count=3,publication_performed=False,**close.FALSE_FLAGS)
    close._read_fixed(Path(close.__file__),HELPER_SHA)
    sealed = close._loads(close._read_fixed(SEALED_CLOSE,SEALED_CLOSE_SHA))
    index = close._loads(close._read_fixed(close.FIXED_REFERENCES['final_index'][0],close.FIXED_REFERENCES['final_index'][1]))
    audit = close._loads(close._read_fixed(close.FIXED_REFERENCES['independent_readback'][0],close.FIXED_REFERENCES['independent_readback'][1]))
    names = [row['ticker'] for row in sealed['stocks']+sealed['controls']]
    if (len(sealed['stocks']) != 101 or len(sealed['calendar']) != 1198 or sealed['target'] != close.TARGET
            or sealed['schema'] != 'CURRENT_CONDITIONAL_PROVIDER_CLOSE_PANEL_PREPARATION_V2'
            or index['queue'] != names or [entry['ticker'] for entry in index['entries']] != names
            or index['completed_attempts'] != 104 or audit['channels'] != 104 or audit['source_unchanged'] is not True):
        raise ValueError('fixed sealed close/index/audit association differs')
    checked = {row['ticker']:row for row in audit['channel_checks']};channels = {}
    for entry in index['entries']:
        ticker = entry['ticker']
        if checked[ticker]['raw_sha256'] != entry['raw_sha256']:
            raise ValueError('fixed independent raw hash association differs')
        raw = close._read_fixed(close.RAW_DIRECTORY/(ticker+'.response.bin'),entry['raw_sha256'])
        channels[ticker] = parse_provider_ohlc(raw,ticker)
        if channels[ticker]['dates'] != checked[ticker]['provider_dates']:
            raise ValueError('raw date alignment differs from saved independent dates')
    result = bind_ohlc_panel(sealed_close=sealed,channels=channels)
    for reference in references.values():
        close._read_fixed(Path(reference['path']),reference['sha256'])
    result.update(status='EXTRACTED_CONDITIONAL_NOT_PUBLISHED',fixed_references=references,
                  actual_http_requests=0,publication_performed=False,
                  close_association_scope='FIXED_SEALED_CLOSE_SHA_AND_ALL_ALIGNED_CLOSE_VALUES',
                  source_closure_scope='FIXED_RAW104_AND_METADATA_ONLY_NOT_REPEATED_RAW_AUDIT_OR_TRANSITIVE_QUALIFICATION')
    return result
