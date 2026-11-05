"""67 saved account snapshots, not a continuous momentum performance replay."""
import json
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from docs.candidates.momentum_account_decision_20261105 import make_decider, ROSTER_PATH, ROSTER_SHA, CORE

ROOT = Path(__file__).resolve().parents[2]


def main():
    roster = json.loads((ROOT / ROSTER_PATH).read_bytes())
    core_sha = sha256((ROOT / CORE).read_bytes()).hexdigest()
    records, pins = [], {ROSTER_PATH: ROSTER_SHA, CORE: core_sha}
    for window, directory in (
        ('2021_2023', 'recent_continuous_baseline_20261026_v7'),
        ('2024_2026', 'old_continuous_baseline_20261026_v9')):
        decide = make_decider(root=ROOT, window=window)
        for row in roster['rows']:
            if row['window'] != window:
                continue
            day = row['decision_date']
            path = ROOT / 'tmp' / directory / (day + '.selection.json')
            raw = path.read_bytes()
            name = path.relative_to(ROOT).as_posix()
            expected = roster['selection_artifact_hashes'][name]
            if sha256(raw).hexdigest() != expected:
                raise ValueError('SAVED_ACCOUNT_CHANGED:' + name)
            pins[name] = expected
            arguments = json.loads(raw)['arguments']
            arguments['source_hashes'].update({ROSTER_PATH: ROSTER_SHA, CORE: core_sha})
            result = decide(**arguments)
            marks = {r['security_id']: F(str(r['price'])) for r in arguments['valuation_quotes']}
            account = arguments['account_state']
            equity = F(str(account['cash'])) + sum(
                (q * marks[s] for s, q in account['shares'].items() if q), F(0))
            expected_target = {r['security_id']: int(equity / (10 * marks[r['security_id']]))
                               for r in row['selected']} if row['gate']['risk_on'] else {}
            if (F(result['investable_equity']) != equity or result['target_quantities'] != expected_target
                    or result['search_calls'] != 0):
                raise ValueError('INDEPENDENT_CAPITAL_FORMULA_MISMATCH:' + day)
            records.append(dict(window=window, decision_date=day, status='PASS',
                                risk_on=row['gate']['risk_on'],
                                positive_positions=sum(q > 0 for q in expected_target.values())))
    if len(records) != 67:
        raise ValueError('67_ACCOUNT_SNAPSHOTS_REQUIRED')
    for name in ('scripts/research/check_momentum_capital_grid_20261105.py',
                 'docs/candidates/momentum_account_decision_20261105.py',
                 'data/current_research_capital_decision.py'):
        pins[name] = sha256((ROOT / name).read_bytes()).hexdigest()
    output = ROOT / 'tmp/momentum_capital_grid_20261105'
    output.mkdir(exist_ok=False)
    report = dict(status='67_SAVED_CAPITAL_SNAPSHOTS_PASS_NOT_CONTINUOUS_BACKTEST',
                  records=records, source_hashes=pins,
                  limitation='Saved baseline account snapshots validate integration only; holdings are not the new strategy trajectory.')
    (output / 'review.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(status=report['status'], snapshots=len(records), search_calls=0)))


if __name__ == '__main__':
    main()
