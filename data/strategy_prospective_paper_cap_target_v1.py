"""Read-only capped view of a verified prospective paper selection.

This is the monthly sizing stage only, not daily risk admission or permission
to accept orders. The original registered experiment remains unchanged.
"""
from fractions import Fraction
import json

from core.monthly_risk_sizing import capped_monthly_quantities
from data.strategy_prospective_paper_selection_v1 import verify_prospective_target


CODE_PATHS = {
    'core/monthly_risk_sizing.py',
    'data/strategy_prospective_paper_cap_target_v1.py',
}


def capped_paper_target(*, selection_result, selection_arguments):
    verified = verify_prospective_target(selection_result, **selection_arguments)
    # The verifier authenticates these descriptor bytes and their code hashes.
    descriptor = json.loads(selection_arguments['authority']['descriptor_arguments']['descriptor_bytes'])
    if not CODE_PATHS <= set(descriptor['code_sha256']):
        raise ValueError('PAPER_CAP_CODE_SCOPE')
    original = verified['target_quantities']
    if original is None:
        raise ValueError('PAPER_CAP_SELECTION_INCOMPLETE')
    binding = selection_result['payload']['input_binding']
    equity = Fraction(binding['strategy_equity'])
    arguments = binding['search_arguments']
    if equity <= 0 or Fraction(arguments['entered_cash']) != equity:
        raise ValueError('PAPER_CAP_EQUITY_MISMATCH')
    if any(type(quantity) is not int or quantity < 0 for quantity in original.values()):
        raise ValueError('PAPER_CAP_WHOLE_QUANTITIES_REQUIRED')
    prices = {sid: arguments['prices'][sid] for sid in original}
    weights = {sid: str(quantity * Fraction(prices[sid]) / equity)
               for sid, quantity in original.items()}
    capped = capped_monthly_quantities(equity=str(equity), weights=weights,
                                       decision_prices=prices)
    return dict(capped, status='VERIFIED_PAPER_MONTHLY_CAP_VIEW',
                account_id=verified['account_id'],
                account_revision=verified['account_revision'],
                registration_sha256=binding['registration_sha256'],
                descriptor_sha256=binding['paper_application_sha256'],
                base_target_id=verified['target_id'],
                target_month=verified['target_month'],
                original_quantities=dict(original), strategy_equity=str(equity),
                decision_prices=dict(prices), account_mutated=False,
                target_mutated=False, orders_created=False,
                daily_exit_applied=False, automatic_acceptance_allowed=False)
