"""Read-only sealed TOP1 ranking with cash-only integer sizing. No selector import."""
from collections import OrderedDict
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from threading import RLock

from data.current_cash_portfolio_research import normalize_cash, ResearchExpiredError
from data.current_portfolio_preview import ROOT, PreviewSourceError, _group_bars
from data.current_research_ohlc_panel import parse_provider_ohlc

BASE = 'tmp/current_top1_snapshot_20261015_v1/'
REGISTRATION, RESULT, REVIEW = [BASE + name + '.json' for name in ('registration', 'result', 'independent_readback')]
INPUT = 'tmp/current_expanded_rebased_training_20261015_v1/prepared.json'
RESEARCH_VERSION = 'CURRENT_SEALED_TOP1_V1_CASH_FLOOR_NO_RESELECTION'
METHOD = 'MONTHLY_ACTUAL_EQUITY_EXACT_PRODUCT_TOP1_V1'
PINS = {
    REGISTRATION: '099a33383990ca1b6329594f8b2e41362614aa7e3ec61edf076d1f18e40c67ed',
    RESULT: 'fffc9f527bf8dca7b0769d2b13908736cff75192c21d851e3bd37c5c82171283',
    REVIEW: 'e3fae713f0bb6aea194c1c364233baeb16bf1c2c7537c168dcce3c91460c536b',
    INPUT: '185e3d6aa804892b3092d224c39ceff28ce3ab3e8e56e2e6664f68d90d376669',
}


def require(condition, message):
    if not condition:
        raise PreviewSourceError(message)


def project_top1(arguments, winner, entered_cash):
    """Ranking is frozen; affordability never substitutes the runner-up."""
    cash = Fraction(entered_cash)
    price = Fraction(arguments['prices'][winner])
    require(cash > 0 and price > 0, '资金或参考价格无效')
    require(Fraction(arguments['fee_bps']) == Fraction(arguments['minimum_cash_buffer']) == 0, '封存费用口径不匹配')
    quantity = int(cash // price)
    invested = quantity * price
    residual = cash - invested
    meta = arguments['metadata'][winner]
    stocks = [] if quantity == 0 else [dict(ticker=meta['ticker'], security_id=winner,
        issuer_id=meta['issuer_id'], units=quantity, close=float(price), notional=float(invested),
        target_weight=float(invested / cash), actual_weight=float(invested / cash),
        latest_reference_quote=None, quote_asof=None)]
    return dict(status='AVAILABLE' if stocks else 'ALL_CASH', as_of=arguments['decision_date'],
        research_only=True, execution_blocked=True, budget=float(cash), invested=float(invested),
        fees=0.0, cash=float(residual), cash_fraction=float(residual / cash), stocks=stocks,
        budget_identity_exact=dict(entered_cash=str(cash), stock_notional=str(invested), fees='0', residual_cash=str(residual)),
        search_status='SEALED_TOP1_CASH_FLOOR', method=METHOD, method_scope=RESEARCH_VERSION,
        price_basis='CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN',
        global_optimum_established=False, forecast_return=None, historical_performance_inherited=False,
        selected_ranking_security_id=winner, selected_security=dict(security_id=winner,ticker=meta['ticker']), candidate_count=len(arguments['prices']),
        search_coverage=dict(objective_evaluations=0, all_affordable_k_initialized=False, per_k=[]),
        notes=['封存排名冠军不随金额改变；这里只按参考价取整股，不重新选股。',
               '不足一股时全现金，不改买第二名；不是看空信号。',
               '10月13日保存价格不是实时可成交报价；训练排名不预测未来收益。',
               '佣金为用户确认的0，其他收费未确认；仅研究，不接真实订单。'])


class CurrentTop1PortfolioResearch:
    def __init__(self, root=ROOT, pins=None):
        self.root = Path(root).resolve()
        self.pins = dict(PINS if pins is None else pins)
        self.results = OrderedDict()
        self.lock = RLock()

    def _path(self, relative):
        require(isinstance(relative, str) and '\\' not in relative and
                not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts,
                '来源必须为仓库内相对路径')
        path = (self.root / relative).resolve()
        require(path.is_relative_to(self.root), '来源路径越界')
        return path

    def _load(self):
        try:
            closure, data, raw_bytes = dict(self.pins), {}, {}
            def verify(path, digest):
                raw = self._path(path).read_bytes()
                require(hashlib.sha256(raw).hexdigest() == digest, 'TOP1 来源指纹不匹配')
                raw_bytes[path] = raw
                if path in (REGISTRATION, RESULT, REVIEW, INPUT):
                    data[path] = json.loads(raw)
            for path, digest in self.pins.items():
                verify(path, digest)
            for obj in (data[REGISTRATION], data[RESULT], data[INPUT]):
                for path, digest in obj['source_hashes'].items():
                    require(path not in closure or closure[path] == digest, '来源指纹冲突')
                    closure[path] = digest
            independent = data[REVIEW]['data_independent_review']
            path = independent['path'].replace('\\', '/')
            require(path not in closure or closure[path] == independent['sha256'], '独审来源冲突')
            closure[path] = independent['sha256']
            for path, digest in closure.items():
                if path not in raw_bytes:
                    verify(path, digest)
            registration, result, review = data[REGISTRATION], data[RESULT], data[REVIEW]
            args = data[INPUT]['search_arguments']
            selected = result['selector_result']
            winner = selected['ranked_security_id']
            require(registration['input_path'] == INPUT and registration['input_sha256'] == closure[INPUT], '输入绑定不匹配')
            require(result['registration_sha256'] == review['registration_sha256'] == closure[REGISTRATION]
                    and review['result_sha256'] == closure[RESULT], '独审结果绑定不匹配')
            require(review['status'] == 'PASS_INDEPENDENT_EXACT_TOP1_READBACK', '缺少通过的独审')
            require(result['method'] == selected['method'] == METHOD and selected['status'] == 'SELECTOR_COMPLETE', '研究方法不匹配')
            require(len(args['prices']) == len(args['metadata']) == selected['candidate_count'] == 99
                    and set(args['prices']) == set(args['metadata']), '完整99候选域不匹配')
            require(len(review['all_99_exact_rankings']) == 99 and review['all_99_exact_rankings'][0]['security_id'] == winner,
                    '冠军与独审不一致')
            require(args['decision_date'] == selected['decision_date'] == result['as_of'] == '2026-10-13'
                    and Fraction(args['entered_cash']) == Fraction(selected['entered_cash']) == 20000, '日期或封存资金不匹配')
            seed = project_top1(args, winner, '20000')
            stock = seed['stocks'][0]
            witness = selected['selected']
            require(witness['quantities'] == {winner: stock['units']} and witness['actual_k'] == 1
                    and review['selected_ticker_quantities'] == {stock['ticker']: stock['units']}, '20k整股独算不匹配')
            for field, key in [('notional', 'stock_notional'), ('fees', 'fees'), ('residual_cash', 'residual_cash')]:
                require(Fraction(witness[field]) == Fraction(seed['budget_identity_exact'][key]), '20k资金独算不匹配')
            require(Fraction(review['price_fraction']) == Fraction(args['prices'][winner])
                    and Fraction(review['cash_fraction']) == Fraction(witness['residual_cash'])
                    and Fraction(review['invested_fraction']) == Fraction(witness['notional'])
                    and Fraction(witness['actual_weights'][winner]) == Fraction(witness['notional']) / 20000,
                    '独审价格或权重不匹配')
            source = review['sndk_raw_source']
            require(source in closure and stock['ticker'] == 'SNDK', 'K线源未绑定')
            channel = parse_provider_ohlc(raw_bytes[source], stock['ticker'])
            require(channel['dates'][-1] == args['decision_date'] and
                    channel['values'][-1][3] == stock['close'], 'K线最后收盘与输入不一致')
            return args, winner, closure, channel
        except (OSError, ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as error:
            self.results.clear()
            raise PreviewSourceError('TOP1研究来源不可用或指纹不匹配') from error

    def calculate(self, entered_cash):
        amount = normalize_cash(entered_cash)
        with self.lock:
            args, winner, closure, _ = self._load()
            identifier = hashlib.sha256(json.dumps([RESEARCH_VERSION, amount, closure], sort_keys=True).encode()).hexdigest()[:24]
            hit = identifier in self.results
            result = project_top1(args, winner, amount)
            result.update(research_id=identifier, research_version=RESEARCH_VERSION, origin='SEALED_RANKING_CASH_FLOOR',
                          cache_hit=hit, generator_calls_this_request=0, selector_calls_this_request=0,
                          sources=closure)
            self.results[identifier] = deepcopy(result)
            self.results.move_to_end(identifier)
            while len(self.results) > 8:
                self.results.popitem(last=False)
            return deepcopy(result)

    def _snapshot(self, research_id):
        if not isinstance(research_id, str) or not re.fullmatch('[0-9a-f]{24}', research_id):
            raise ValueError('研究编号格式无效')
        if research_id not in self.results:
            raise ResearchExpiredError('研究结果已过期，请重新读取')
        return deepcopy(self.results[research_id])

    def snapshot(self, research_id):
        with self.lock:
            self._load()
            return self._snapshot(research_id)

    def bars(self, research_id, ticker, interval='day', bars=90):
        if type(ticker) is not str or interval not in ('day', 'week', 'month') or type(bars) is not int or not 1 <= bars <= 260:
            raise ValueError('K线请求参数无效')
        with self.lock:
            _, _, _, channel = self._load()
            snapshot = self._snapshot(research_id)
            require(ticker in {r['ticker'] for r in snapshot['stocks']}, '股票不属于该研究计划')
            daily, missing = [], []
            for day, values in zip(channel['dates'], channel['values']):
                if day > snapshot['as_of']:
                    continue
                if any(v is None for v in values[:4]):
                    missing.append(day)
                else:
                    daily.append(dict(zip(('date', 'open', 'high', 'low', 'close', 'volume'), [day] + values)))
            return dict(status='AVAILABLE', research_id=research_id, ticker=ticker, interval=interval,
                        as_of=snapshot['as_of'], daily_as_of=snapshot['as_of'], currency='USD',
                        research_only=True, execution_blocked=True, bars=_group_bars(daily, interval)[-bars:],
                        last_period_may_be_partial=interval != 'day', missing_session_count=len(missing),
                        missing_sessions=missing, no_missing_fill=True, adjustment_basis=snapshot['price_basis'],
                        source='fingerprinted_saved_actual_ohlc')


_RESEARCH = CurrentTop1PortfolioResearch()


def calculate_current_top1_research(entered_cash):
    return _RESEARCH.calculate(entered_cash)


def read_current_top1_research_snapshot(research_id):
    return _RESEARCH.snapshot(research_id)


def read_current_top1_research_bars(research_id, ticker, interval='day', bars=90):
    return _RESEARCH.bars(research_id, ticker, interval, bars)
