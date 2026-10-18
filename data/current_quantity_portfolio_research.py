"""Read-only bounded quantity research; isolated from old 46-rule calculation."""
from collections import OrderedDict
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from threading import Lock

from backtest.return_priority_fresh_cash_quantity_search import search_fresh_cash_quantities
from data.current_cash_portfolio_research import normalize_cash, ResearchExpiredError
from data.current_portfolio_preview import PreviewSourceError, ROOT, _group_bars, _signature

INPUT = 'tmp/fresh_quantity_input_asof_20261013_v1/inputs.json'
CORE = 'backtest/return_priority_fresh_cash_quantity_search.py'
START = 'tmp/fresh_quantity_actual_asof_20261013_v1/start.json'
RECEIPT = 'tmp/fresh_quantity_actual_asof_20261013_v1/receipt.json'
READBACK = 'tmp/fresh_quantity_actual_asof_20261013_v1/root_readback.json'
RESULT = 'tmp/fresh_quantity_actual_asof_20261013_v1/result.json'
PANEL = 'tmp/current_ohlc_actual_projection_20261014_v1/panel.json'
RESEARCH_VERSION = 'CURRENT_FRESH_QUANTITY_V1_BOUNDED_8192_NO_46_RULES'
PINS = {
    INPUT: '04d83a897601d3cb921e0efeaa5ef27104db6bd1c801728e2e9289beb6958935',
    CORE: '756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588',
    START: '3b80a27f5edfd51ecf9150dda2009b787fdf93c4bd56eb03f92892a0f11cf50f',
    RECEIPT: '7945bd6412e025ef7324e301dc79a1974395461d9bea05d99f2b19fe206dbf93',
    READBACK: '6fe6ffb54a575ae435e19cd78b93821da6dcc1a6614d1a5aab7fd8e5ee6bee82',
    RESULT: '28a32090eca0f08eb94131fdf96bcf8d5c6a0e28fb2e58aaa8dee0d375b5f2e1',
    PANEL: 'c765f124401129fd913d2733fcc68c6a0512f29d0424fb8c70a2752d51e08426',
}


def require(condition, message):
    if not condition:
        raise PreviewSourceError(message)


def project(result, arguments):
    budget = Fraction(arguments['entered_cash'])
    selected = result.get('selected')
    require(Fraction(result['entered_cash']) == budget and result['decision_date'] == arguments['decision_date'], 'Result input binding mismatch')
    stocks, invested = [], Fraction(0)
    fees = Fraction(selected['fees']) if selected is not None else Fraction(0)
    cash = Fraction(selected['residual_cash']) if selected is not None else budget
    if selected is not None:
        for sid, q in selected['quantities'].items():
            require(type(q) is int and q > 0, 'Positive whole shares required')
            price, meta = Fraction(arguments['prices'][sid]), arguments['metadata'][sid]
            require(price > 0, 'Positive saved close required')
            notional = q * price
            invested += notional
            require(Fraction(selected['actual_weights'][sid]) == notional / budget, 'Actual weight mismatch')
            stocks.append(dict(ticker=meta['ticker'], security_id=sid, issuer_id=meta['issuer_id'], units=q,
                               close=float(price), notional=float(notional), target_weight=float(notional / budget),
                               actual_weight=float(notional / budget), latest_reference_quote=None, quote_asof=None))
        require(invested == Fraction(selected['notional']) and len(stocks) == selected['actual_k'], 'Selected totals mismatch')
        require(len({s['issuer_id'] for s in stocks}) == len(stocks), 'Duplicate issuer')
    require(cash >= 0 and fees == 0 and invested + fees + cash == budget, 'Cash identity failed')
    status = 'INCOMPLETE' if selected is None else 'AVAILABLE' if stocks else 'ALL_CASH'
    return dict(status=status, as_of=arguments['decision_date'], research_only=True, execution_blocked=True,
                budget=float(budget), invested=float(invested), fees=float(fees), cash=float(cash), stocks=stocks,
                cash_fraction=float(cash / budget), search_status=result['status'], global_optimum_established=False,
                forecast_return=None, historical_performance_inherited=False,
                method_scope='BOUNDED_FRESH_CASH_QUANTITY_SEARCH_PRICE_SCENARIOS_NOT_FORECAST_NO_46_RULES',
                price_basis='CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN',
                budget_identity_exact=dict(entered_cash=str(budget), stock_notional=str(invested), fees=str(fees), residual_cash=str(cash)),
                search_coverage=dict(objective_evaluations=result.get('objective_evaluations'),
                                     all_affordable_k_initialized=result.get('all_affordable_k_initialized'),
                                     per_k=deepcopy(result.get('per_k', []))),
                notes=['固定保存日研究预览，禁止订单或正式采纳。', '新金额重新搜索整股数量与组成；有限预算不保证全局最优。',
                       '训练价格情景不预测未来收益，不继承旧46规则或波段回测表现。', '佣金为用户确认的0；其他收费未确认。'])


class CurrentQuantityPortfolioResearch:
    def __init__(self, root=ROOT, pins=None, search=None):
        self.root, self.pins = Path(root), dict(PINS if pins is None else pins)
        self.search = search or search_fresh_cash_quantities
        self.lock = Lock()
        self.results = OrderedDict()
        self.signatures, self.decoded, self.closure = None, None, None
        self.series = {}

    def _clear(self):
        self.signatures = self.decoded = self.closure = None
        self.results.clear()
        self.series.clear()

    def _load(self):
        try:
            if self.signatures is not None and all(_signature(self.root / path) == sig for path, sig in self.signatures.items()):
                return
            self._clear()
            decoded, signatures, closure = {}, {}, dict(self.pins)

            def read(path, expected):
                file = self.root / path
                signature = _signature(file)
                require(signature[2] <= 32 * 1024 * 1024, 'Research source too large')
                raw = file.read_bytes()
                require(hashlib.sha256(raw).hexdigest() == expected and _signature(file) == signature, 'Research source fingerprint mismatch')
                signatures[path] = signature
                if path.endswith('.json'):
                    decoded[path] = json.loads(raw)

            for path, expected in list(closure.items()):
                read(path, expected)
            for path, expected in decoded[RECEIPT]['source_registration']['source_pins'].items():
                require(path not in closure or closure[path] == expected, 'Conflicting source pin')
                closure[path] = expected
                if path not in signatures:
                    read(path, expected)
            require(decoded[START]['core_sha256'] == closure[CORE] and decoded[START]['inputs_sha256'] == closure[INPUT], 'Start binding mismatch')
            require(decoded[RECEIPT]['result_sha256'] == closure[RESULT], 'Receipt result binding mismatch')
            require(decoded[READBACK]['status'] == 'PASS_ALL_SAVED_BEST_WITNESSES_AND_SOURCE_ACCOUNTING', 'Independent seed readback required')
            args = decoded[INPUT]
            require(Fraction(args['entered_cash']) == 20000 and Fraction(args['fee_bps']) == 0 and Fraction(args['minimum_cash_buffer']) == 0, 'Seed cash/fees mismatch')
            require(args['max_objective_evaluations'] == 8192 and args['prices'] and set(args['prices']) == set(args['metadata']), 'Incomplete bounded inputs')
            require(len(args['training_scenarios']) == len(args['scenario_dates']) == 12 and args['scenario_dates'] == sorted(set(args['scenario_dates'])) and max(args['scenario_dates']) <= args['decision_date'], 'Mature distinct scenarios required')
            require(all(set(s) == set(args['prices']) for s in args['training_scenarios']), 'Incomplete scenario pool')
            require(decoded[PANEL]['calendar'][-1] == args['decision_date'], 'Panel observation date differs')
            channels = {r['ticker']: r for r in decoded[PANEL]['stocks']}
            for sid, price in args['prices'].items():
                ticker = args['metadata'][sid]['ticker']
                require(Fraction(str(channels[ticker]['values'][-1][3])) == Fraction(price), 'Panel/input close differs')
            require(all(_signature(self.root / path) == sig for path, sig in signatures.items()), 'Sources changed during initialization')
            project(decoded[RESULT], args)
            seed_quantities = {args['metadata'][sid]['ticker']: q for sid, q in decoded[RESULT]['selected']['quantities'].items()}
            require(seed_quantities == decoded[READBACK]['selected_ticker_quantities'], 'Seed differs from independent readback')
            self.decoded, self.signatures, self.closure = decoded, signatures, closure
        except (OSError, ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as error:
            self._clear()
            raise PreviewSourceError('数量研究来源不可用或指纹不匹配') from error

    def calculate(self, entered_cash):
        amount = normalize_cash(entered_cash)
        with self.lock:
            self._load()
            identifier = hashlib.sha256(json.dumps([RESEARCH_VERSION, amount, self.closure], sort_keys=True).encode()).hexdigest()[:24]
            if identifier in self.results:
                self.results.move_to_end(identifier)
                result = deepcopy(self.results[identifier])
                result.update(origin='MEMORY_CACHE', cache_hit=True, generator_calls_this_request=0)
                return result
            arguments = deepcopy(self.decoded[INPUT])
            arguments['entered_cash'] = amount
            seed = amount == '20000.00'
            searched = deepcopy(self.decoded[RESULT]) if seed else self.search(**arguments)
            require(all(_signature(self.root / path) == sig for path, sig in self.signatures.items()), 'Sources changed during research calculation')
            result = project(searched, arguments)
            result.update(research_id=identifier, research_version=RESEARCH_VERSION, origin='SEALED_SEED' if seed else 'FRESH_SEARCH',
                          cache_hit=False, generator_calls_this_request=0 if seed else 1, sources=dict(self.closure))
            if result['status'] != 'INCOMPLETE':
                self.results[identifier] = deepcopy(result)
                while len(self.results) > 8:
                    self.results.popitem(last=False)
            return deepcopy(result)

    def snapshot(self, research_id):
        """Read a still-cached result without calculation or cache creation."""
        if not isinstance(research_id, str) or not re.fullmatch('[0-9a-f]{24}', research_id):
            raise ValueError('研究编号格式无效')
        with self.lock:
            self._load()
            if research_id not in self.results:
                raise ResearchExpiredError('研究结果已过期，请重新计算')
            return deepcopy(self.results[research_id])

    def bars(self, research_id, ticker, interval='day', bars=90):
        if not isinstance(research_id, str) or not re.fullmatch('[0-9a-f]{24}', research_id):
            raise ValueError('Invalid research_id')
        if type(ticker) is not str or interval not in ('day', 'week', 'month') or type(bars) is not int or not 1 <= bars <= 260:
            raise ValueError('Invalid bar request')
        with self.lock:
            self._load()
            if research_id not in self.results:
                raise ResearchExpiredError('研究结果已过期，请重新计算')
            selected = self.results[research_id]
            require(ticker in {row['ticker'] for row in selected['stocks']}, 'Ticker not selected by this research_id')
            if ticker not in self.series:
                panel = self.decoded[PANEL]
                channel = next(row for row in panel['stocks'] if row['ticker'] == ticker)
                require(len(channel['values']) == len(panel['calendar']), 'Misaligned OHLC')
                daily, missing = [], []
                for day, values in zip(panel['calendar'], channel['values']):
                    if any(v is None for v in values[:4]):
                        missing.append(day)
                        continue
                    require(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values[:4]), 'Invalid OHLC')
                    o, h, l, c, v = values
                    require(l <= min(o, c) <= max(o, c) <= h, 'Invalid OHLC range')
                    require(v is None or type(v) in (int, float) and math.isfinite(v) and v >= 0, 'Invalid volume')
                    daily.append(dict(date=day, open=o, high=h, low=l, close=c, volume=v))
                self.series[ticker] = (daily, missing)
            daily, missing = self.series[ticker]
            stock = next(row for row in selected['stocks'] if row['ticker'] == ticker)
            require(daily and daily[-1]['date'] == selected['as_of'] and daily[-1]['close'] == stock['close'], 'Saved Close/chart mismatch')
            return dict(status='AVAILABLE', research_id=research_id, ticker=ticker, interval=interval,
                        as_of=selected['as_of'], daily_as_of=selected['as_of'], research_only=True, execution_blocked=True,
                        bars=deepcopy(_group_bars(daily, interval)[-bars:]), last_period_may_be_partial=interval != 'day',
                        missing_session_count=len(missing), missing_sessions=list(missing), no_missing_fill=True,
                        adjustment_basis=selected['price_basis'], source='fingerprinted_saved_actual_ohlc')


_RESEARCH = CurrentQuantityPortfolioResearch()


def calculate_current_quantity_research(entered_cash):
    return _RESEARCH.calculate(entered_cash)


def read_current_quantity_research_bars(research_id, ticker, interval='day', bars=90):
    return _RESEARCH.bars(research_id, ticker, interval, bars)


def read_current_quantity_research_snapshot(research_id):
    return _RESEARCH.snapshot(research_id)
