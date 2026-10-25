"""Current cap-policy UI review; retain the original V1 evidence semantics."""
from copy import deepcopy
import argparse
import json
from pathlib import Path

from scripts.review_daily_ui_capture_v1 import review as review_original


def review(capture):
    state = capture['state']
    daily = state.get('daily') or {}
    capped = daily.get('risk_monthly_targets')
    policy = daily.get('policy_id')
    # Archived V1 fixtures need an explicit display contract. A missing current
    # policy/map is not evidence that the uncapped selector quantities are valid.
    if policy is None and capture.get('monthly_display_policy') == 'LEGACY_UNCAPPED_V1':
        if capped is not None:
            raise ValueError('LEGACY_DISPLAY_WITH_CAPPED_TARGETS')
        return review_original(capture)
    if policy != 'MONTHLY_CAP50_EXIT20':
        raise ValueError('UNREVIEWED_MONTHLY_DISPLAY_POLICY')
    if capped is None:
        raise ValueError('CAPPED_MONTHLY_TARGET_UNVERIFIED')
    target_rows = state['target'].get('targets')
    if not isinstance(target_rows, list):
        raise ValueError('CAPPED_MONTHLY_DOMAIN_MISMATCH')
    original = {row['security_id']: row['quantity']
                for row in target_rows}
    if (len(original) != len(target_rows) or not isinstance(capped, dict)
            or set(capped) != set(original)):
        raise ValueError('CAPPED_MONTHLY_DOMAIN_MISMATCH')
    if any(type(quantity) is not int or not 0 <= quantity <= original[sid]
           for sid, quantity in capped.items()):
        raise ValueError('CAPPED_MONTHLY_QUANTITY_INVALID')
    # Only the displayed monthly column differs. Original account, daily gate,
    # effective targets, cash constraint, quote lifetime and DOM remain checked.
    normalized = deepcopy(capture)
    for row in normalized['state']['target']['targets']:
        row['quantity'] = capped[row['security_id']]
    # A complete, bound map proves a zero monthly target for remaining holdings
    # outside this month's selector domain. V1 still verifies the binding, full
    # gate, live quotes, orders and account before accepting this display copy.
    old_holdings = {row['security_id'] for row in state['account']['holdings']} - set(original)
    normalized['state']['target']['targets'].extend(
        dict(security_id=sid, quantity=0) for sid in sorted(old_holdings))
    # V1's HOLD branch returns before its final extra-row order check. No
    # current order anywhere on the captured table may accompany HOLD.
    if daily.get('status') == 'HOLD' and any(row.get('orders') for row in capture['visible_rows']):
        raise ValueError('UNEXPECTED_VISIBLE_ORDER')
    result = review_original(normalized)
    return dict(result, monthly_display_policy=daily['policy_id'],
                raw_monthly_targets=original, displayed_monthly_targets=deepcopy(capped),
                cap_calculation_independently_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_path', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(review(json.loads(arguments.capture_path.read_bytes())),
                     ensure_ascii=False, indent=2))
