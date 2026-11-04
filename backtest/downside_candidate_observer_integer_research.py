# Independent integer-arithmetic candidate; source backtest/downside_candidate_observer_research.py SHA256 fb56c85b7f9855d8b6fa165bc51fa4fd792045e1a714623ffa99de1b8ea77909
"""Research-only observer; never generates candidates or changes search state."""
from copy import deepcopy
from backtest.downside_daily_integer_candidate import ExactDailyReturnIntegers
from datetime import date
from fractions import Fraction as F
from math import prod
from scripts.audit_capped_training_frontier import capped, evaluate
from scripts.research.preflight_downside_frontier_20261105 import bounds, classify


class DownsideCandidateObserver:
    def __init__(self, *, max_holdings, search_arguments, stock_returns,
                 qqq_reference, max_risk_evaluations):
        if type(max_holdings) is not int or max_holdings < 1:
            raise ValueError('EXPLICIT_POSITIVE_HOLDING_LIMIT_REQUIRED')
        if type(max_risk_evaluations) is not int or max_risk_evaluations < 1:
            raise ValueError('EXPLICIT_POSITIVE_RISK_BUDGET_REQUIRED')
        self.arguments = deepcopy(search_arguments)
        self.max_holdings = max_holdings
        self.budget = max_risk_evaluations
        self.reference = {d: F(v) for d, v in qqq_reference.items()}
        days = list(self.reference)
        if len(days) != 252 or days != sorted(set(days)) or any(date.fromisoformat(d).isoformat() != d for d in days):
            raise ValueError('252_ORDERED_COMMON_DATES_REQUIRED')
        if days[-1] != self.arguments['decision_date']:
            raise ValueError('DECISION_DATE_MISMATCH')
        if set(stock_returns) != set(self.arguments['prices']):
            raise ValueError('COMPLETE_SECURITY_DOMAIN_REQUIRED')
        self.returns = {}
        for sid, rows in stock_returns.items():
            if list(rows) != days:
                raise ValueError('COMMON_RETURN_DATES_REQUIRED')
            self.returns[sid] = [F(rows[d]) for d in days]
        reference = list(self.reference.values())
        if any(v <= -1 for row in [reference, *self.returns.values()] for v in row):
            raise ValueError('POSITIVE_GROSS_RETURNS_REQUIRED')
        scenarios = self.arguments['training_scenarios']
        if len(scenarios) != 12 or self.arguments['scenario_dates'] != days[20::21]:
            raise ValueError('ORIGINAL_12_SCENARIO_DATES_REQUIRED')
        for sid, values in self.returns.items():
            if any(prod(1 + v for v in values[i*21:(i+1)*21]) != F(scenarios[i][sid]) for i in range(12)):
                raise ValueError('DAILY_SCENARIO_COORDINATE_MISMATCH')
        evaluate({}, self.arguments)
        self.integer_returns = ExactDailyReturnIntegers(
            prices=self.arguments['prices'], equity=self.arguments['entered_cash'], stock_returns=self.returns)
        self.reference_values = reference
        self.reference_bounds = bounds(reference)
        self.raw_seen = set()
        self.cap_seen = set()
        self.best = {}
        cash_score = evaluate({}, self.arguments)
        self.cash = dict(target_quantities={}, actual_k=0, notional=F(0),
                         residual_cash=cash_score['residual_cash'], exact_product=cash_score['product'],
                         downside_interval=['0', '0'], exact_boundary_comparison=False,
                         source_phase='EXPLICIT_CASH_FALLBACK_NOT_SEARCH_OBSERVATION',
                         source_evaluation_index=None, raw_signature=())
        self.failed = False
        self.complete = True
        self.ended = False
        self.counts = dict(raw_unique_observed=0, capped_unique=0, over_holdings_limit=0,
                           risk_evaluated=0, risk_pass_positive=0, risk_pass_cash=0,
                           exact_boundary_count=0)

    def observe(self, quantities, *, phase, evaluation_index):
        if self.failed:
            raise ValueError('OBSERVATION_PREVIOUSLY_FAILED')
        try:
            return self._observe(quantities, phase=phase, evaluation_index=evaluation_index)
        except Exception:
            self.failed = True
            self.complete = False
            raise

    def _observe(self, quantities, *, phase, evaluation_index):
        if self.ended:
            raise ValueError('OBSERVATION_ALREADY_ENDED')
        if not isinstance(phase, str) or not phase or type(evaluation_index) is not int or evaluation_index < 0:
            raise ValueError('EXPLICIT_CANDIDATE_PROVENANCE_REQUIRED')
        # Validate raw feasibility before cap; cap must not launder invalid baskets.
        if type(quantities) is not dict or any(s not in self.arguments['prices'] or type(q) is not int or q < 0 for s, q in quantities.items()):
            raise ValueError('INVALID_RAW_QUANTITIES')
        raw = {s: q for s, q in quantities.items() if q}
        signature = tuple(sorted(raw.items()))
        if signature in self.raw_seen:
            return
        evaluate(raw, self.arguments)
        self.raw_seen.add(signature)
        self.counts['raw_unique_observed'] += 1
        basket = capped(raw, self.arguments)
        cap_signature = tuple(sorted(basket.items()))
        if cap_signature in self.cap_seen:
            return
        self.cap_seen.add(cap_signature)
        self.counts['capped_unique'] += 1
        k = len(basket)
        if k > self.max_holdings:
            self.counts['over_holdings_limit'] += 1
            return
        if self.counts['risk_evaluated'] >= self.budget:
            self.complete = False
            return
        self.counts['risk_evaluated'] += 1
        score = evaluate(basket, self.arguments)
        values = self.integer_returns.portfolio_returns(basket)
        passed, exact, interval = classify(values, self.reference_values, self.reference_bounds)
        self.counts['exact_boundary_count'] += exact
        if not passed:
            return
        self.counts['risk_pass_positive' if k else 'risk_pass_cash'] += 1
        rank = (score['product'], -score['notional'], cap_signature)
        record = dict(target_quantities=basket, actual_k=k, notional=score['notional'],
                      residual_cash=score['residual_cash'], exact_product=score['product'],
                      downside_interval=interval, exact_boundary_comparison=exact,
                      source_phase=phase, source_evaluation_index=evaluation_index,
                      raw_signature=signature)
        if not k:
            self.cash = record
        elif k not in self.best or rank > self.best[k][0]:
            self.best[k] = (rank, record)

    def end_observation(self):
        # Caller signals stream termination, not exhaustive search coverage.
        self.ended = True

    def finalize(self):
        if self.failed:
            raise ValueError('OBSERVATION_FAILED')
        if not self.ended:
            raise ValueError('OBSERVATION_STREAM_NOT_ENDED')
        if not self.complete:
            raise ValueError('INCOMPLETE_RISK_OBSERVATION_BUDGET')
        return deepcopy(dict(complete=True, coverage=self.counts, max_holdings=self.max_holdings,
                             eligible_best_by_k={str(k): v[1] for k, v in sorted(self.best.items())},
                             cash=self.cash, cash_fallback_seeded=True, source_authenticated=False,
                             search_coverage_verified=False,
                             scope='OBSERVED_CANDIDATES_ONLY_NOT_SEARCH_COMPLETENESS'))
