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
    if capped is None:
        return review_original(capture)
    if daily.get('policy_id') != 'MONTHLY_CAP50_EXIT20':
        raise ValueError('UNREVIEWED_MONTHLY_DISPLAY_POLICY')
    original = {row['security_id']: row['quantity']
                for row in state['target'].get('targets', [])}
    if not isinstance(capped, dict) or set(capped) != set(original):
        raise ValueError('CAPPED_MONTHLY_DOMAIN_MISMATCH')
    if any(type(quantity) is not int or not 0 <= quantity <= original[sid]
           for sid, quantity in capped.items()):
        raise ValueError('CAPPED_MONTHLY_QUANTITY_INVALID')
    # Only the displayed monthly column differs. Original account, daily gate,
    # effective targets, cash constraint, quote lifetime and DOM remain checked.
    normalized = deepcopy(capture)
    for row in normalized['state']['target']['targets']:
        row['quantity'] = capped[row['security_id']]
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
