"""Read-only, fingerprinted research selection and its actual saved OHLC.

Only fixed local artifacts are read. No providers, CSV fallback, accounts,
generators, ledger calls or execution actions are reachable from this module.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import logging
import math
from pathlib import Path
from threading import Lock


LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
RESULT = 'tmp/latest_saved_snapshot_actual_20261014_v1/result.json'
PANEL = 'tmp/current_ohlc_actual_projection_20261013_v1/panel.json'
QUOTES = 'tmp/six_quote_prior_close_crosscheck_20261014_v1/readonly_display_payload.json'
PINS = {
    RESULT: '100997505389e5be97d976cfacb5505c5a50b79825ae6130058d90d213a0e258',
    PANEL: '92361a7321765594a5544ab3cb9128410c8296799d99b3d23090e24a37df9822',
    QUOTES: '74d799d83bef5c22ef36156c933288ed257516bac19c6116254b1237221b4ae5',
}


class PreviewSourceError(ValueError):
    """A fixed research artifact is unavailable or failed verification."""


def _require(condition, message):
    if not condition:
        raise PreviewSourceError(message)


def _signature(path):
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino


def _group_bars(daily, interval):
    grouped, previous = [], None
    for row in daily:
        session = date.fromisoformat(row['date'])
        key = row['date'] if interval == 'day' else session.isocalendar()[:2] if interval == 'week' else (session.year, session.month)
        if key != previous:
            grouped.append({**row, 'first_date': row['date'], 'sessions': 1})
            previous = key
        else:
            candle = grouped[-1]
            candle.update(date=row['date'], high=max(candle['high'], row['high']),
                          low=min(candle['low'], row['low']), close=row['close'],
                          volume=candle['volume'] + row['volume'] if candle['volume'] is not None and row['volume'] is not None else None,
                          sessions=candle['sessions'] + 1)
            _require(candle['volume'] is None or math.isfinite(candle['volume']), 'Aggregated volume overflow')
    return grouped


class CurrentPortfolioPreview:
    """One verified in-memory projection; unchanged endpoints perform stat only."""

    def __init__(self, root=ROOT, source_pins=None):
        self.root = Path(root)
        self.pins = dict(PINS if source_pins is None else source_pins)
        _require(set(self.pins) == {RESULT, PANEL, QUOTES}, 'Exactly the fixed result, OHLC and reference quote sources are required')
        self.lock = Lock()
        self.signatures = None
        self.payload = None
        self.series = None

    def _load(self):
        try:
            signatures = {relative: _signature(self.root / relative) for relative in self.pins}
            if self.payload is not None and signatures == self.signatures:
                return
            # Never serve a stale cached result after a changed source fails hash.
            self.payload = self.series = self.signatures = None
            decoded = {}
            for relative, digest in self.pins.items():
                _require(signatures[relative][2] <= 16 * 1024 * 1024, 'Research artifact exceeds size limit')
                raw = (self.root / relative).read_bytes()
                _require(_signature(self.root / relative) == signatures[relative], 'Research artifact changed while reading')
                _require(hashlib.sha256(raw).hexdigest() == digest, 'Research artifact fingerprint mismatch')
                decoded[relative] = json.loads(raw)
            payload, series = self._project(decoded[RESULT], decoded[PANEL], decoded[QUOTES])
            _require(all(_signature(self.root / relative) == signature for relative, signature in signatures.items()),
                     'Research sources changed while building projection')
            self.payload, self.series, self.signatures = payload, series, signatures
            LOGGER.info('Verified saved research preview cache: %s stocks, %s', len(payload['stocks']), payload['as_of'])
        except (OSError, KeyError, TypeError, ValueError, OverflowError) as error:
            self.payload = self.series = self.signatures = None
            if isinstance(error, PreviewSourceError):
                raise
            raise PreviewSourceError('Saved research artifacts unavailable or invalid') from error

    def _project(self, result, panel, quote_payload):
        _require(result['status'] == 'SELECTED_CURRENT_INDICATIVE_RESEARCH_CANDIDATE', 'No sealed selected candidate')
        _require(result['current_adoption_allowed'] is False and result['orders_created'] is False,
                 'Expected non-executable research artifact')
        as_of = result['saved_observation_date']
        calendar = panel['calendar']
        _require(calendar and calendar == sorted(set(calendar)) and calendar[-1] == as_of,
                 'Aligned unique calendar ending at saved observation required')
        for session in calendar:
            _require(date.fromisoformat(session).isoformat() == session, 'ISO observation calendar')
        selected = result['selected_candidate']
        positions = result['selected_positions']
        _require(len(positions) == 6 and len({row['ticker'] for row in positions}) == 6, 'Fixed six-stock research preview required')
        quotes = {row['ticker']: row for row in quote_payload['rows']}
        _require(len(quotes) == len(quote_payload['rows']) and set(quotes) == {row['ticker'] for row in positions},
                 'Reference quotes must match the six selected stocks')
        budget, cash = Fraction(result['fresh_cash_pool']), Fraction(selected['indicative_residual_cash'])
        fees, cost = Fraction(selected['indicative_buy_fee']), Fraction(selected['indicative_total_cost'])
        _require(budget > 0 and cash >= 0 and fees >= 0 and cost + cash == budget, 'Full fresh-cash budget reconciliation failed')
        channels = {row['ticker']: row for row in panel['stocks']}
        stocks, series = [], {}
        invested = Fraction(0)
        for row in positions:
            ticker, units = row['ticker'], row['indicative_units']
            _require(type(units) is int and units > 0, 'Positive whole research units required')
            close = Fraction(str(row['saved_close']))
            notional = close * units
            invested += notional
            quote = quotes[ticker]
            quote_price = float(Fraction(quote['display_price']))
            _require(math.isfinite(quote_price) and quote_price > 0 and
                     quote['reference_snapshot_date'] == as_of and Fraction(str(quote['reference_snapshot_close'])) == close,
                     'Reference quote must bind saved calculation price without replacing it')
            _require(quote['weight_recalculation_allowed'] is False and quote['execution_authorized'] is False,
                     'Newer quote must remain display-only')
            stocks.append({
                'ticker': ticker, 'security_id': row['security_id'], 'issuer_id': row['issuer_id'],
                'target_weight': float(Fraction(row['target_weight'])),
                'stock_internal_weight': float(Fraction(row['stock_internal_weight'])),
                'units': units, 'close': float(close), 'notional': float(notional),
                'actual_weight': float(notional / budget),
                'latest_reference_quote': quote_price, 'quote_asof': quote['display_market_date'],
                'quote_source': quote['source'], 'latest_price_cross_source_verified': False,
            })
            channel = channels[ticker]
            _require(len(channel['values']) == len(calendar), 'Aligned true OHLC observations required')
            daily, missing = [], []
            for session, values in zip(calendar, channel['values']):
                _require(type(values) is list and len(values) == 5, 'Expected actual provider OHLCV row')
                if any(value is None for value in values[:4]):
                    missing.append(session)
                    continue
                _require(all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in values[:4]),
                         'Nonfinite or nonpositive OHLC')
                opened, high, low, closed, volume = values
                _require(low <= min(opened, closed) <= max(opened, closed) <= high, 'Inconsistent actual OHLC range')
                _require(volume is None or (type(volume) in (int, float) and math.isfinite(volume) and volume >= 0), 'Invalid actual volume')
                daily.append(dict(date=session, open=opened, high=high, low=low, close=closed, volume=volume))
            _require(daily and daily[-1]['date'] == as_of and Fraction(str(daily[-1]['close'])) == close,
                     'Selected saved Close must match actual OHLC at observation')
            series[ticker] = {'periods': {interval: _group_bars(daily, interval) for interval in ('day', 'week', 'month')},
                              'missing_sessions': missing, 'daily_as_of': daily[-1]['date']}
        _require(invested + fees == cost, 'Position notionals, costs and fees do not reconcile')
        payload = {
            'status': 'AVAILABLE', 'as_of': as_of, 'research_only': True,
            'execution_blocked': True, 'execution_status': 'BLOCKED_RESEARCH_ONLY',
            'budget': float(budget), 'cash': float(cash), 'fees': float(fees), 'invested': float(invested),
            'cash_fraction': float(cash / budget), 'rule_id': selected['method_rule_id'],
            'stocks': stocks, 'price_basis': panel['price_basis'], 'forecast_return': None,
            'notes': ['已保存快照，仅供研究；不是今日可执行订单。',
                      '股数按该日收盘价估算；全部输入现金仍在组合内。',
                      '价格复权、名义股数及分红口径尚未认证。',
                      '较新参考报价独立展示，未通过最新价跨来源核验，不改变计算价或历史K线。'],
            'gaps': ['当前身份与风险标签仅为条件研究假设', 'PIT资格未认证', '真实下单与账户采纳未开放'],
            'coverage': deepcopy(result.get('coverage_counts', {})),
            'sources': {relative: digest for relative, digest in self.pins.items()},
        }
        return payload, series

    def preview(self):
        with self.lock:
            self._load()
            return deepcopy(self.payload)

    def bars(self, ticker, interval='day', bars=90):
        if interval not in ('day', 'week', 'month'):
            raise ValueError('interval must be day, week or month')
        if type(bars) is not int or not 1 <= bars <= 260:
            raise ValueError('bars must be an integer from 1 to 260')
        with self.lock:
            self._load()
            if ticker not in self.series:
                raise ValueError('ticker is not in the six-stock research preview')
            series = self.series[ticker]
            return {
                'status': 'AVAILABLE', 'ticker': ticker, 'interval': interval,
                'as_of': self.payload['as_of'], 'daily_as_of': series['daily_as_of'],
                'research_only': True, 'execution_blocked': True,
                'source': 'fingerprinted_saved_actual_ohlc', 'stale': None,
                'bars': deepcopy(series['periods'][interval][-bars:]),
                'missing_session_count': len(series['missing_sessions']),
                'missing_sessions': list(series['missing_sessions']),
                'no_missing_fill': True, 'last_period_may_be_partial': interval != 'day',
                'adjustment_basis': self.payload['price_basis'],
            }


_PREVIEW = CurrentPortfolioPreview()


def read_current_portfolio_preview():
    return _PREVIEW.preview()


def read_current_portfolio_bars(ticker, interval='day', bars=90):
    return _PREVIEW.bars(ticker, interval, bars)
