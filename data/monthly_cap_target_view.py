"""Derive a capped target from an already admitted original monthly decision.

Keeps the original signed target unchanged. Owning admission must validate the
selector result/source pins first; content hashes alone are not authorization.
"""
from fractions import Fraction
from hashlib import sha256

from core.monthly_risk_sizing import capped_monthly_quantities
from core.strategy_account_ledger import canonical


def capped_target_view(target):
    payload = target['payload']
    decision = payload['decision']
    selected = decision['payload']
    binding = selected['input_binding']
    for value, digest in ((payload, target['target_id']),
                          (selected, decision['decision_id']),
                          (binding, selected['input_id'])):
        if sha256(canonical(value)).hexdigest() != digest:
            raise ValueError('CAP_ORIGINAL_TARGET_CHANGED')
    original = payload['target_quantities']
    if original != selected['target_quantities']:
        raise ValueError('CAP_SELECTION_TARGET_MISMATCH')
    equity = Fraction(binding['strategy_equity'])
    arguments = binding['search_arguments']
    if equity <= 0 or Fraction(arguments['entered_cash']) != equity:
        raise ValueError('CAP_SELECTION_EQUITY_MISMATCH')
    if any(type(quantity) is not int or quantity < 0 for quantity in original.values()):
        raise ValueError('CAP_WHOLE_QUANTITIES_REQUIRED')
    prices = {sid: arguments['prices'][sid] for sid in original}
    weights = {sid: str(quantity * Fraction(prices[sid]) / equity)
               for sid, quantity in original.items()}
    result = capped_monthly_quantities(equity=str(equity), weights=weights,
                                      decision_prices=prices)
    return dict(result, base_target_id=target['target_id'],
                original_quantities=dict(original),
                strategy_equity=str(equity), decision_prices=dict(prices),
                target_mutated=False, account_mutated=False)
