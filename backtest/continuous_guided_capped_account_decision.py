"""Actual-equity continuous32 selection followed by a distinct monthly risk cap.

No saved portfolio weights are accepted. The raw search decision remains intact
under raw_selection, rather than being relabelled as a cap-constrained optimum.
"""
from fractions import Fraction
from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account


def decide_capped_account(**arguments):
    raw = decide_continuous_guided_for_account(**arguments)
    if raw.get('target_quantities') is None:
        return dict(target_quantities=None, raw_selection=raw,
                    investable_equity=raw.get('investable_equity'), research_only=True)
    equity = Fraction(raw['investable_equity'])
    marks = {row['security_id']: Fraction(row['price']) for row in arguments['valuation_quotes']}
    target = {sid: min(quantity, int(equity / (2 * marks[sid])))
              for sid, quantity in raw['target_quantities'].items()}
    return dict(method='CONTINUOUS32_THEN_MONTHLY_CAP50_RESEARCH',
                target_quantities=target, investable_equity=str(equity),
                raw_selection=raw, monthly_cap_fraction='1/2',
                capital_source='CURRENT_BRANCH_ACCOUNT_STATE',
                cap_is_post_selection_overlay=True, research_only=True,
                global_optimum_established=False)
