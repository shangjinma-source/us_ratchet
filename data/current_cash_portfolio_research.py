"""Budget-triggered, read-only current research using sealed rule priority.

The old single-run registration supplies the accepted 84 metadata assumptions
only. Its one-call experiment authorization/receipt is never changed or reused
as a runtime authorization. No historical books, accounts or orders are called.
"""
from collections import Counter, OrderedDict
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import logging
import math
from pathlib import Path
import re
from threading import Lock

from data.current_portfolio_preview import PreviewSourceError, ROOT, QUOTES, PINS as PREVIEW_PINS, _group_bars, _signature
from scripts.return_priority_latest_saved_snapshot_research import (
    build_latest_saved_snapshot, SOURCE_PINS, PANEL_PATH, PROPOSAL_PATH, RESULT_PATH, FROZEN_PATH,
)
from backtest.return_priority_exact_floor_ceil_research import project_exact_floor_ceil, ProjectionInputError


LOGGER = logging.getLogger(__name__)
REGISTRATION = 'tmp/latest_saved_snapshot_actual_20261014_v1/registration.json'
BUILDER = 'scripts/return_priority_latest_saved_snapshot_research.py'
PROJECTOR = 'backtest/return_priority_exact_floor_ceil_research.py'
COMMISSION_CONFIRMATION = 'research_contracts/user_broker_commission_confirmation_20261014.json'
RESEARCH_VERSION = 'CURRENT_CASH_RESEARCH_V3_USER_CONFIRMED_ZERO_COMMISSION'
PINS = {**SOURCE_PINS,
        COMMISSION_CONFIRMATION: '0fb4622cac5dec9a60c0a6d351ee6f1df430dc5904442d5417fc9580fd5e3d6f',
        REGISTRATION: '05efcc02c4bc6da4f45783c536776cf721527fd3042e3b87374e981e4a2e0ba7',
        BUILDER: '1180c3dd863a5c682a0a1e55b93e51af00fdb61f90882ce1b1400f44b6ac965e',
        PROJECTOR: '96a69d7f7458d6d0fed1b67236312afcd443719bec897c0c38d7b70a4559ef5b'}
MAX_CACHED_BUDGETS = 8
MAX_NEIGHBORHOOD_EVALUATIONS = 65536


class ProjectionBudgetExceededError(PreviewSourceError):
    """A higher-priority rule remains unresolved; do not substitute a later rule."""
    def __init__(self, diagnostics):
        super().__init__('整股配置搜索尚未完成；已到本次搜索上限，不输出替代组合。')
        self.diagnostics = diagnostics


class ResearchExpiredError(ValueError):
    """The bounded process-local research result is no longer available."""


def normalize_cash(value):
    """Resource/input bounds, not portfolio risk limits; full cash is preserved."""
    if type(value) not in (str, int, float):
        raise ValueError('entered_cash must be a decimal USD amount')
    text = str(value).strip()
    if len(text) > 24 or not re.fullmatch(r'(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?', text):
        raise ValueError('entered_cash must have at most two decimal places')
    amount = Decimal(text)
    if not Decimal('0.01') <= amount <= Decimal('1000000000'):
        raise ValueError('entered_cash must be between 0.01 and 1000000000 USD')
    return format(amount, '.2f')


def _require(condition, message):
    if not condition:
        raise PreviewSourceError(message)


def apply_exact_integer_projection(result, *, max_evaluations=MAX_NEIGHBORHOOD_EVALUATIONS):
    """Apply existing priority to floor, then bounded exact repair of each rule.

Mutates only the newly generated, unpublished result. Original generated floor
records remain unchanged for per-k coverage; only the selected copy and trace
are replaced. Historical return evidence is not inherited by the new mechanism.
"""
    _require(type(max_evaluations) is int and 1 <= max_evaluations <= MAX_NEIGHBORHOOD_EVALUATIONS,
             'Explicit bounded per-request integer neighborhood budget')
    generated = result['candidate_generation']
    records = {row['method_rule_id']: row for row in generated['records']}
    coverage = {row['security_id']: row for row in result['all_observed_stock_coverage'] if 'security_id' in row}
    prices = {security: row['current_close'] for security, row in coverage.items()}
    selected, used, attempts, selected_projection = None, 0, 0, None
    trace = []
    for original in result['sealed_rule_application_trace']:
        entry = deepcopy(original)
        entry.update(selected=False, original_floor_status=original['current_status'],
                     original_floor_blocked_reasons=deepcopy(original['current_blocked_reasons']),
                     integer_projection_status='NOT_NEEDED_OR_NOT_ELIGIBLE', integer_projection_evaluations=0)
        candidate = records.get(entry['method_rule_id'])
        if selected is not None:
            entry['integer_projection_status'] = 'NOT_EVALUATED_AFTER_HIGHER_PRIORITY_SELECTION'
        elif candidate is not None and candidate['status'] in ('LEGAL_INDICATIVE_ONLY', 'REFERENCE_ALL_CASH'):
            selected = deepcopy(candidate)
            entry['selected'] = True
            entry['integer_projection_status'] = 'ORIGINAL_FLOOR_OR_CASH_REFERENCE'
        elif candidate is not None and candidate['status'] == 'BLOCKED':
            reasons = set(candidate['blocked_reasons'])
            eligible = (bool(reasons) and reasons <= {'ZERO_QUANTITY_REQUESTED_MEMBER', 'INDICATIVE_WHOLE_LOT_RISK_FAILED'}
                        and candidate.get('profile_risk', {}).get('all_passed') is True
                        and Fraction(result['fresh_cash_pool']) >= Fraction(generated['minimum_cash_buffer']))
            if eligible:
                if used >= max_evaluations:
                    raise ProjectionBudgetExceededError({'max_evaluations': max_evaluations, 'completed_evaluations': used,
                                                         'unresolved_rule': candidate['method_rule_id']})
                try:
                    projected = project_exact_floor_ceil(
                        candidate=candidate, prices=prices, metadata=candidate['metadata'],
                        risk_parameters=generated['risk_parameters'], entered_cash=result['fresh_cash_pool'],
                        fee_bps=generated['fee_bps'], minimum_cash_buffer=generated['minimum_cash_buffer'],
                        max_evaluations=max_evaluations-used)
                except ProjectionInputError as error:
                    raise PreviewSourceError('Generated candidate does not satisfy exact projection input contract') from error
                attempts += 1
                used += projected['neighborhood_evaluations']
                entry.update(integer_projection_status=projected['status'],
                             integer_projection_evaluations=projected['neighborhood_evaluations'],
                             integer_projection_neighborhood_size=projected['search_space_size'])
                if projected['status'] == 'SEARCH_BUDGET_EXHAUSTED':
                    raise ProjectionBudgetExceededError({'max_evaluations': max_evaluations, 'completed_evaluations': used,
                                                         'unresolved_rule': candidate['method_rule_id'],
                                                         'unresolved_neighborhood_size': projected['search_space_size']})
                if projected['status'] == 'FEASIBLE':
                    selected = deepcopy(candidate)
                    witness = projected['projection']
                    selected.update(status='LEGAL_AFTER_EXACT_FLOOR_CEIL_RESEARCH_PROJECTION', blocked_reasons=[],
                                    indicative_quantities=witness['quantities'], actual_k=witness['actual_k'],
                                    indicative_buy_notional=witness['buy_notional'], indicative_buy_fee=witness['buy_fee'],
                                    indicative_total_cost=witness['total_cost'], indicative_residual_cash=witness['residual_cash'],
                                    risk=deepcopy(witness['risk']))
                    selected_projection = projected
                    entry.update(selected=True, current_status=selected['status'], current_blocked_reasons=[])
        trace.append(entry)
    result['selected_candidate'] = selected
    result['selected_positions'] = []
    if selected:
        for security in selected['security_ids']:
            metadata = selected['metadata'][security]
            result['selected_positions'].append({
                'security_id': security, 'ticker': metadata['ticker'], 'issuer_id': metadata['issuer_id'],
                'stock_internal_weight': selected['stock_internal_profile_weights'][security],
                'target_weight': selected['target_weights'][security],
                'indicative_units': selected['indicative_quantities'][security], 'saved_close': prices[security],
                'metadata_source_refs': deepcopy(metadata['source_refs']),
            })
    result['status'] = 'SELECTED_CURRENT_INDICATIVE_RESEARCH_CANDIDATE' if selected else 'NO_CURRENT_LEGAL_SEALED_RULE'
    result['sealed_rule_application_trace'] = trace
    result['integer_projection_search'] = {
        'max_neighborhood_evaluations': max_evaluations, 'completed_neighborhood_evaluations': used,
        'attempted_rules': attempts, 'selected_rule_repaired': selected_projection is not None,
        'selected_projection': selected_projection,
        'original_per_k_coverage_scope': 'ORIGINAL_FLOOR_ONLY_NOT_REPAIRED_SEARCH_COVERAGE',
        'historical_performance_inherited': False,
    }
    return result


def project_research_result(result, quotes):
    """Compact API projection; never sends full candidates/source metadata."""
    budget = Fraction(result['fresh_cash_pool'])
    selected = result['selected_candidate']
    cash = Fraction(selected['indicative_residual_cash']) if selected else budget
    fees = Fraction(selected['indicative_buy_fee']) if selected else Fraction(0)
    cost = Fraction(selected['indicative_total_cost']) if selected else Fraction(0)
    stocks, invested = [], Fraction(0)
    for row in result['selected_positions']:
        units, close = row['indicative_units'], Fraction(str(row['saved_close']))
        _require(type(units) is int and units > 0 and close > 0, 'Positive whole indicative units and saved Close required')
        notional = units * close
        invested += notional
        quote = quotes.get(row['ticker'])
        quote_valid = quote is not None and quote.get('reference_snapshot_date') == result['saved_observation_date']
        if quote_valid:
            quote_valid = Fraction(str(quote['reference_snapshot_close'])) == close
        stocks.append({
            'ticker': row['ticker'], 'security_id': row['security_id'], 'issuer_id': row['issuer_id'],
            'target_weight': float(Fraction(row['target_weight'])),
            'stock_internal_weight': float(Fraction(row['stock_internal_weight'])),
            'units': units, 'close': float(close), 'notional': float(notional),
            'actual_weight': float(notional / budget),
            'latest_reference_quote': float(Fraction(quote['display_price'])) if quote_valid else None,
            'quote_asof': quote['display_market_date'] if quote_valid else None,
            'quote_source': quote['source'] if quote_valid else None,
            'latest_price_cross_source_verified': False,
        })
    _require(budget > 0 and cash >= 0 and fees >= 0 and invested + fees == cost and cost + cash == budget,
             'Full entered cash must equal stocks plus fees plus residual cash')
    _require(len({row['ticker'] for row in stocks}) == len(stocks) and
             len({row['issuer_id'] for row in stocks}) == len(stocks), 'Unique selected securities and issuers required')
    if selected:
        _require(len(stocks) == selected['actual_k'] == selected['requested_k'], 'Frozen selected count must match whole units')
    generated = result['candidate_generation']
    by_k = {}
    for row in generated['records']:
        count = row['requested_k']
        summary = by_k.setdefault(count, {'k': count, 'records': 0, 'legal': 0, 'blocked': 0, 'structural_reasons': []})
        summary['records'] += 1
        if row['status'] in ('LEGAL_INDICATIVE_ONLY', 'REFERENCE_ALL_CASH'):
            summary['legal'] += 1
        else:
            summary['blocked'] += 1
        if row['status'] == 'BLOCKED_STRUCTURAL':
            summary['structural_reasons'] = list(row['blocked_reasons'])
    trace = result['sealed_rule_application_trace']
    selected_rank = next((row['historical_rank'] for row in trace if row['selected']), None)
    status = 'NO_LEGAL' if selected is None else 'AVAILABLE' if stocks else 'ALL_CASH'
    reason = {'AVAILABLE': 'FIRST_FEASIBLE_RULE_IN_FIXED_HISTORICAL_PRIORITY',
              'ALL_CASH': 'SEALED_CASH_REFERENCE_SELECTED_NOT_A_BEARISH_FORECAST',
              'NO_LEGAL': 'NO_FEASIBLE_SEALED_RULE_UNALLOCATED_CASH_NOT_INVESTMENT_ADVICE'}[status]
    return {
        'status': status, 'outcome_reason': reason, 'as_of': result['saved_observation_date'],
        'research_only': True, 'execution_blocked': True, 'execution_status': 'BLOCKED_RESEARCH_ONLY',
        'research_role': 'BUDGET_TRIGGERED_READ_ONLY_RESEARCH',
        'method_scope': 'FULL_BUDGET_BOUNDED_ALL_K_FIXED_46_PRIORITY_WITH_EXACT_FLOOR_CEIL_PROJECTION_NO_RETRAINING_NO_INHERITED_HISTORICAL_PERFORMANCE',
        'execution_method_version': 'EXACT_FLOOR_CEIL_V2_FROZEN_STOCK_BUDGET',
        'historical_performance_inherited': False,
        'budget': float(budget), 'cash': float(cash), 'fees': float(fees), 'invested': float(invested),
        'cash_fraction': float(cash / budget), 'rule_id': selected['method_rule_id'] if selected else None,
        'stocks': stocks, 'forecast_return': None,
        'budget_identity_exact': {'entered_cash': str(budget), 'stock_notional': str(invested), 'fees': str(fees), 'residual_cash': str(cash)},
        'coverage': deepcopy(result['coverage_counts']),
        'search_coverage': {
            'per_k_scope': 'ORIGINAL_FLOOR_ONLY_NOT_REPAIRED_SEARCH_COVERAGE',
            'security_count': generated['security_count'], 'issuer_count': generated['issuer_count'],
            'considered_k_count': len(generated['all_k_considered']), 'record_limit': generated['record_limit'],
            'candidate_count': len(generated['records']), 'by_k': [by_k[count] for count in sorted(by_k)],
            'historical_rule_count': len(trace), 'selected_historical_rank': selected_rank,
            'rule_application_trace': deepcopy(trace),
        },
        'integer_projection_search': deepcopy(result.get('integer_projection_search')),
        'notes': ['完整输入现金参与研究计算；各金额重新生成候选，不是缩放原六股。',
                  '按固定历史规则顺序筛当前可行组合，不是重新训练收益最优组合。',
                  '逐规则先检查原向下取整，必要时完整检验受预算约束的上下取整邻域；不继承原向下取整历史收益。',
                  '计算与K线截至已保存快照；全现金结果不代表主动看空或保证最优。',
                  '仅研究，未采纳到账户；较新参考报价独立展示，可缺失。'],
        'gaps': ['当前元数据为条件研究假设，PIT资格未认证', '名义股数、复权与分红口径未认证', '实际下一开盘可执行性未验证'],
    }


class CurrentCashPortfolioResearch:
    def __init__(self, root=ROOT, source_pins=None, max_cached_budgets=MAX_CACHED_BUDGETS):
        self.root = Path(root)
        self.pins = dict(PINS if source_pins is None else source_pins)
        _require(set(self.pins) == set(PINS), 'Fixed sources and methods required')
        _require(type(max_cached_budgets) is int and 1 <= max_cached_budgets <= 8, 'Bounded research cache')
        self.max_cached_budgets = max_cached_budgets
        self.lock = Lock()
        self.signatures = None
        self.inputs = None
        self.quotes = {}
        self.results = OrderedDict()
        self.series = {}
        self.quote_status = 'UNAVAILABLE'
        self.commission_confirmation = None

    def _clear(self):
        self.signatures = self.inputs = None
        self.results.clear()
        self.series.clear()
        self.quotes = {}
        self.commission_confirmation = None

    def _load(self):
        try:
            signatures = {path: _signature(self.root / path) for path in self.pins}
            quote_path = self.root / QUOTES
            try:
                signatures[QUOTES] = _signature(quote_path)
            except FileNotFoundError:
                signatures[QUOTES] = None
            if self.inputs is not None and signatures == self.signatures:
                return
            self._clear()
            decoded = {}
            for relative, digest in self.pins.items():
                _require(signatures[relative][2] <= 16 * 1024 * 1024, 'Source size limit')
                raw = (self.root / relative).read_bytes()
                _require(_signature(self.root / relative) == signatures[relative] and hashlib.sha256(raw).hexdigest() == digest,
                         'Changed or fingerprint-mismatched research source')
                if relative.endswith('.json'):
                    decoded[relative] = json.loads(raw)
            registration = decoded[REGISTRATION]
            accepted = registration['accepted_current_conditional_tickers']
            _require(len(accepted) == len(set(accepted)) == 84, 'Original accepted84 research metadata list required')
            proposal = decoded[PROPOSAL_PATH]
            accepted_rows = [row for row in proposal['proposed_metadata'] if row['ticker'] in accepted]
            _require(len(accepted_rows) == 84 and len({row['issuer_id'] for row in accepted_rows}) == 83,
                     'Original accepted84/83 current conditional domain required')
            historical = decoded[RESULT_PATH]
            _require(len(historical['rankings']) == 46 and historical['frozen_candidates_sha256'] == self.pins[FROZEN_PATH],
                     'Fixed 46 historical rule order/method binding required')
            method = decoded[FROZEN_PATH][-1]
            _require(method['decision_date'] == '2026-09-21', 'Original frozen method snapshot required')
            confirmation = decoded[COMMISSION_CONFIRMATION]
            _require(confirmation['schema'] == 'USER_BROKER_COMMISSION_CONFIRMATION_V1' and
                     confirmation['confirmation_status'] == 'USER_CONFIRMED' and
                     confirmation['currency'] == 'USD' and
                     type(confirmation['commission_fee_bps']) is int and confirmation['commission_fee_bps'] == 0 and
                     type(confirmation['minimum_commission_usd']) is int and confirmation['minimum_commission_usd'] == 0 and
                     confirmation['other_charges_confirmed'] is False and
                     confirmation['changes_historical_results'] is False and
                     confirmation['authorizes_broker_orders'] is False and
                     confirmation['historical_research_fee_bps'] == Fraction(method['fee_bps']) == 10,
                     'Pinned user-confirmed current commission and unchanged historical fee required')
            panel = decoded[PANEL_PATH]
            _require(panel['calendar'][-1] == '2026-10-12' and len(panel['stocks']) == 101, 'Fixed saved snapshot101 domain required')
            self.quote_status = 'UNAVAILABLE'
            if signatures[QUOTES] is not None:
                try:
                    _require(signatures[QUOTES][2] <= 1024 * 1024, 'Reference quote size limit')
                    raw = quote_path.read_bytes()
                    _require(hashlib.sha256(raw).hexdigest() == PREVIEW_PINS[QUOTES] and _signature(quote_path) == signatures[QUOTES],
                             'Unverified optional quote source')
                    rows = json.loads(raw)['rows']
                    _require(len({row['ticker'] for row in rows}) == len(rows), 'Unique optional quotes')
                    for row in rows:
                        price = float(Fraction(row['display_price']))
                        _require(math.isfinite(price) and price > 0 and row['weight_recalculation_allowed'] is False and
                                 row['execution_authorized'] is False, 'Display-only positive reference quotes required')
                    self.quotes = {row['ticker']: row for row in rows}
                    self.quote_status = 'VERIFIED_OPTIONAL_SOURCE'
                except (OSError, ValueError, TypeError, KeyError, OverflowError):
                    self.quotes = {}
                    self.quote_status = 'UNAVAILABLE_OR_UNVERIFIED_IGNORED'
            _require(all(_signature(self.root / path) == signatures[path] for path in self.pins), 'Sources changed during loading')
            self.inputs = {
                'panel': panel, 'current_proposal': proposal,
                'historical_result': {'status': historical['status'], 'rankings': [{'rule': row['rule']} for row in historical['rankings']]},
                'frozen_method_snapshot': {key: deepcopy(method[key]) for key in ('fee_bps', 'minimum_cash_buffer', 'risk_parameters', 'fixed_seed')},
                'accepted_tickers': list(accepted),
                'source_refs': [{'path': path, 'sha256': digest} for path, digest in self.pins.items()],
            }
            self.signatures = signatures
            self.commission_confirmation = confirmation
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
            self._clear()
            if isinstance(error, PreviewSourceError):
                raise
            raise PreviewSourceError('Current cash research sources unavailable or invalid') from error

    def calculate(self, entered_cash):
        amount = normalize_cash(entered_cash)
        with self.lock:
            self._load()
            research_id = hashlib.sha256(json.dumps([RESEARCH_VERSION, amount, self.pins], sort_keys=True).encode()).hexdigest()[:24]
            if research_id in self.results:
                self.results.move_to_end(research_id)
                payload = deepcopy(self.results[research_id])
                payload.update(cache_hit=True, generator_calls_this_request=0)
                return payload
            _require(self.commission_confirmation is not None, 'Validated current commission confirmation required')
            current_inputs = dict(self.inputs)
            current_method = deepcopy(self.inputs['frozen_method_snapshot'])
            current_method['fee_bps'] = self.commission_confirmation['commission_fee_bps']
            current_inputs['frozen_method_snapshot'] = current_method
            result = build_latest_saved_snapshot(entered_cash=amount, **current_inputs)
            result = apply_exact_integer_projection(result)
            payload = project_research_result(result, self.quotes)
            payload['commission_policy'] = {
                'current_fee_bps': current_method['fee_bps'],
                'current_minimum_commission_usd': self.commission_confirmation['minimum_commission_usd'],
                'confirmation_status': 'USER_CONFIRMED',
                'historical_research_fee_bps': self.commission_confirmation['historical_research_fee_bps'],
                'historical_results_changed': False,
                'other_charges_confirmed': False,
                'other_charges_included': False,
                'fees_field_scope': 'CURRENT_CONFIRMED_COMMISSION_ONLY',
                'source': {'path': COMMISSION_CONFIRMATION, 'sha256': self.pins[COMMISSION_CONFIRMATION]},
            }
            payload['notes'].append('当前研究采用用户确认的零佣金、每笔最低佣金为零；历史比较仍为10 bps。其他费用尚未确认、未计入，不推定全部交易成本为零。')
            payload.update(research_id=research_id, cache_hit=False, generator_calls_this_request=1,
                           research_version=RESEARCH_VERSION,
                           historical_replays=0, book_calls=0, initial_positions={},
                           entered_cash=amount, price_basis=self.inputs['panel']['price_basis'],
                           reference_quote_status=self.quote_status,
                           sources=dict(self.pins), input_limits={'minimum_usd': '0.01', 'maximum_usd': '1000000000.00', 'decimal_places': 2})
            self.results[research_id] = payload
            while len(self.results) > self.max_cached_budgets:
                self.results.popitem(last=False)
            LOGGER.info('Current cash research generated: budget=%s, outcome=%s, selected_count=%s', amount, payload['status'], len(payload['stocks']))
            return deepcopy(payload)

    def bars(self, research_id, ticker, interval='day', bars=90):
        if not isinstance(research_id, str) or not re.fullmatch('[0-9a-f]{24}', research_id):
            raise ValueError('Invalid research_id')
        if type(ticker) is not str or interval not in ('day', 'week', 'month') or type(bars) is not int or not 1 <= bars <= 260:
            raise ValueError('Invalid ticker, interval or bar count')
        with self.lock:
            self._load()
            if research_id not in self.results:
                raise ResearchExpiredError('研究结果已过期，请按当前金额重新计算')
            selected = self.results[research_id]
            if ticker not in {row['ticker'] for row in selected['stocks']}:
                raise ValueError('ticker is not selected by this budget research result')
            if ticker not in self.series:
                panel = self.inputs['panel']
                channel = next(row for row in panel['stocks'] if row['ticker'] == ticker)
                _require(len(channel['values']) == len(panel['calendar']), 'Aligned actual OHLC required')
                daily, missing = [], []
                for day, values in zip(panel['calendar'], channel['values']):
                    _require(type(values) is list and len(values) == 5, 'Actual provider OHLCV rows required')
                    if any(value is None for value in values[:4]):
                        missing.append(day)
                        continue
                    _require(all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in values[:4]), 'Invalid actual OHLC')
                    opened, high, low, closed, volume = values
                    _require(low <= min(opened, closed) <= max(opened, closed) <= high, 'Inconsistent actual OHLC range')
                    _require(volume is None or type(volume) in (int, float) and math.isfinite(volume) and volume >= 0, 'Invalid actual volume')
                    daily.append(dict(date=day, open=opened, high=high, low=low, close=closed, volume=volume))
                stock = next(row for row in selected['stocks'] if row['ticker'] == ticker)
                _require(daily and daily[-1]['date'] == selected['as_of'] and daily[-1]['close'] == stock['close'], 'Saved chart Close/selection mismatch')
                self.series[ticker] = {'periods': {period: _group_bars(daily, period) for period in ('day', 'week', 'month')}, 'missing': missing}
            series = self.series[ticker]
            return {'status': 'AVAILABLE', 'research_id': research_id, 'ticker': ticker, 'interval': interval,
                    'as_of': selected['as_of'], 'daily_as_of': selected['as_of'], 'research_only': True, 'execution_blocked': True,
                    'source': 'fingerprinted_saved_actual_ohlc', 'stale': None,
                    'bars': deepcopy(series['periods'][interval][-bars:]), 'last_period_may_be_partial': interval != 'day',
                    'missing_session_count': len(series['missing']), 'missing_sessions': list(series['missing']),
                    'no_missing_fill': True, 'adjustment_basis': selected['price_basis']}


_RESEARCH = CurrentCashPortfolioResearch()


def calculate_current_cash_research(entered_cash):
    return _RESEARCH.calculate(entered_cash)


def read_current_cash_research_bars(research_id, ticker, interval='day', bars=90):
    return _RESEARCH.bars(research_id, ticker, interval, bars)
