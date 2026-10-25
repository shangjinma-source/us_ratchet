"""Review V27 proposal display bindings, retaining legacy UI acceptance checks."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

from scripts.review_daily_ui_capture_v2 import review as review_previous


POLICY = 'SAVED_FRONTIER_CAP50_EXIT20_V1'


def review(capture):
    state = capture['state']
    target = state['target']
    daily = state.get('daily') or {}
    if daily.get('policy_id') != POLICY:
        if target.get('proposal_id') or daily.get('proposal_id'):
            raise ValueError('FRONTIER_POLICY_MISMATCH')
        return review_previous(capture)
    proposal_id = target.get('proposal_id')
    if (not isinstance(proposal_id, str) or
            not re.fullmatch('[0-9a-f]{64}', proposal_id) or
            daily.get('proposal_id') != proposal_id):
        raise ValueError('FRONTIER_PROPOSAL_BINDING')
    rows = target.get('proposal_targets')
    if not isinstance(rows, list) or not rows:
        raise ValueError('FRONTIER_PROPOSAL_TARGETS_REQUIRED')
    quantities = {}
    for row in rows:
        security_id = row.get('security_id')
        quantity = row.get('quantity')
        if (not isinstance(security_id, str) or not security_id or
                security_id in quantities or type(quantity) is not int or quantity < 0):
            raise ValueError('FRONTIER_PROPOSAL_TARGETS_INVALID')
        quantities[security_id] = quantity
    for source in (target, daily):
        values = source.get('risk_monthly_targets')
        if (not isinstance(values, dict) or values != quantities or
                any(type(value) is not int for value in values.values())):
            raise ValueError('FRONTIER_QUANTITIES_BINDING')
    if daily.get('status') not in ('READY', 'CONDITIONAL_PREVIEW_READY'):
        if any(row.get('orders') for row in capture['visible_rows']):
            raise ValueError('UNEXPECTED_VISIBLE_ORDER')
    normalized = deepcopy(capture)
    normalized['state']['target']['targets'] = deepcopy(rows)
    normalized['state']['daily']['policy_id'] = 'MONTHLY_CAP50_EXIT20'
    result = review_previous(normalized)
    result.pop('raw_monthly_targets', None)
    return dict(result, monthly_display_policy=POLICY, proposal_id=proposal_id,
                proposal_calculation_independently_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_path', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(review(json.loads(arguments.capture_path.read_bytes())),
                     ensure_ascii=False, indent=2))
