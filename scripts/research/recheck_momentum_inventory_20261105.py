"""Recheck the fixed potential exposure grid after dividend/absence evidence.

Does not authorize split/merger execution or run any economic account.
"""
import json
from pathlib import Path
from scripts.research import inventory_momentum_actions_20261105 as inventory
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact
from docs.candidates.momentum_absence_20261105 import append_review

ROOT = Path(__file__).resolve().parents[2]


def main():
    original = inventory.read('tmp/momentum_action_inventory_20261105/inventory.json')
    inventory.bind(original['source_hashes'])
    freeze = inventory.read('research_contracts/downside_max10_resume_v9_20261105/freeze.json')
    results = []
    for window in ('2021_2023', '2024_2026'):
        document, prices, review, legacy, proof = inventory.inputs(window, freeze)
        if window == '2021_2023':
            document['prepared_input_candidate'] = document['prepared']
            names = ['tmp/momentum_early_dividends_20261105/supplement.json']
        else:
            names = ['tmp/momentum_late_dividends_20261105/supplement.json',
                     'tmp/amat_202408_t1_resolution_20261105/supplement.json']
        for name in names:
            artifact = inventory.read(name)
            inventory.bind(artifact['source_hashes'])
            append_ordinary_artifact(document, review, artifact)
        if window == '2024_2026':
            absence = append_review(document, review)
            inventory.bind(absence['source_hashes'])
        for row in original['rows']:
            if row['window'] != window:
                continue
            args = dict(decision_date=row['decision_date'], account_state=dict(
                shares={sid: 1 for sid in row['previous_potential_sids']}))
            selected = dict(target_quantities={sid: 1 for sid in row['new_potential_sids']})
            if window == '2021_2023':
                gate = inventory.exposed_action_blockers(
                    args, selected, row['through'], prices, review,
                    row['active_date'], document['dividend_events'])
            else:
                gate = inventory.exposure_gate(document, args, selected, row['through'], row['active_date'])
                gate = inventory.admit_reviewed_dividends(gate, review, document['dividend_events'])
                gate = inventory.admit_period_absence(gate, review)
                gate = legacy.admit(gate, proof)
            results.append(dict(window=window, decision_date=row['decision_date'], gate=gate))
    for name in ('scripts/research/recheck_momentum_inventory_20261105.py',
                 'docs/candidates/momentum_absence_20261105.py',
                 'docs/candidates/downside_resume_chain_20261105.py'):
        path = ROOT / name
        inventory.bind({name: inventory.sha256(path.read_bytes()).hexdigest()})
    inventory.bind(dict(inventory.PINS))
    summary = {}
    for window in ('2021_2023', '2024_2026'):
        rows = [r for r in results if r['window'] == window]
        remaining = {}
        for row in rows:
            for category in ('unmapped_events', 'missing_action_streams'):
                for event in row['gate'][category]:
                    remaining[json.dumps([category, event], sort_keys=True)] = dict(category=category, event=event)
        summary[window] = dict(months=len(rows), months_without_inventory_blockers=sum(
            r['gate']['admitted'] for r in rows), unique_remaining=list(remaining.values()))
    report = dict(status='UPDATED_POTENTIAL_EXPOSURE_NOT_ECONOMIC_ADMISSION',
                  rows=results, summary=summary, source_hashes=inventory.PINS)
    output = ROOT / 'tmp/momentum_inventory_recheck_20261105'
    output.mkdir(exist_ok=False)
    (output / 'review.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(dict(status=report['status'], summary=summary)))


if __name__ == '__main__':
    main()
