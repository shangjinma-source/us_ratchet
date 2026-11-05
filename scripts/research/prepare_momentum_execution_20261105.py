"""Freeze fixed account inputs only after all 67 potential exposure gates pass."""
import json
import sys
from hashlib import sha256
from pathlib import Path
from scripts.research import inventory_momentum_actions_20261105 as inventory
from scripts.research import run_momentum_account_20261105 as runner
from docs.candidates import qqq_risk_budget_account_runner
from docs.candidates.momentum_split_admission_20261105 import FixedSplitAdmission
from docs.candidates.momentum_sgen_admission_20261105 import load_artifact, ARTIFACT, ARTIFACT_SHA256
from docs.candidates.momentum_absence_20261105 import normalize

ROOT = Path(__file__).resolve().parents[2]
BASE = 'research_contracts/downside_max10_resume_v9_20261105/freeze.json'
OUTPUT = 'research_contracts/momentum_account_execution_20261105'


def main():
    pins = {}
    def bind(extra):
        for name, digest in extra.items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('SOURCE_CHANGED:' + name)
            if name in pins and pins[name] != digest:
                raise ValueError('PIN_CONFLICT:' + name)
            pins[name] = digest

    def read(name):
        raw = (ROOT / name).read_bytes()
        bind({name: sha256(raw).hexdigest()})
        return json.loads(raw)

    base = read(BASE)
    bind(base['source_hashes'])
    previous = read('tmp/momentum_action_inventory_20261105/inventory.json')
    bind(previous['source_hashes'])
    roster = read(runner.ROSTER_PATH)
    if pins[runner.ROSTER_PATH] != runner.ROSTER_SHA:
        raise ValueError('FIXED_ROSTER_CHANGED')
    bind(roster['prior_expected_hashes_verified'])
    bind(roster['selection_artifact_hashes'])
    for name in ('tmp/momentum_early_dividends_20261105/supplement.json',
                 'tmp/momentum_late_dividends_20261105/supplement.json',
                 'tmp/amat_202408_t1_resolution_20261105/supplement.json'):
        bind(read(name)['source_hashes'])
    bind(FixedSplitAdmission().source_hashes)
    bind(load_artifact()['source_hashes'])
    bind({ARTIFACT: ARTIFACT_SHA256})
    inputs = {}
    for window in ('2021_2023', '2024_2026'):
        inputs[window] = inventory.inputs(window, base)
        bind(inventory.PINS)
    bind(normalize(inputs['2024_2026'][0])['source_hashes'])
    freeze = dict(schema='FIXED_MOMENTUM_EXECUTION_V1', status='READY_FOR_REVIEWED_EXECUTION',
                  inventory_base_freeze=BASE, source_hashes=pins, early_delays=[0, 1, 5], late_delays=[0],
                  seconds_per_scenario=3600, windows={'2021_2023': 36, '2024_2026': 31},
                  no_parameter_search=True, production_mutation=False,
                  conditional_evidence_not_full_pit=True)
    gates = []
    for window, (document, prices, review, legacy, proof) in inputs.items():
        document, review = runner.prepare_actions(window=window, document=document, prices=prices,
                                                  review=review, pins=pins, freeze=freeze)
        for row in previous['rows']:
            if row['window'] != window:
                continue
            arguments = dict(decision_date=row['decision_date'], account_state=dict(
                shares={s: 1 for s in row['previous_potential_sids']}))
            selected = dict(target_quantities={s: 1 for s in row['new_potential_sids']})
            gate = runner.action_gate(window=window, arguments=arguments, selected=selected,
                                      until=row['through'], active=row['active_date'], document=document,
                                      prices=prices, review=review, legacy=legacy, proof=proof)
            if not gate['admitted']:
                raise ValueError('POTENTIAL_EXPOSURE_STILL_BLOCKED:' + window + ':' + row['decision_date'])
            gates.append(dict(window=window, decision_date=row['decision_date'], gate=gate))
    if len(gates) != 67:
        raise ValueError('67_GATE_REVIEWS_REQUIRED')
    # Include the full loaded local import closure, including unchanged book code.
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(ROOT) and path.suffix == '.py':
            bind({path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()})
    contract = 'docs/candidates/momentum_full_account_execution_contract_20261105.md'
    bind({contract: sha256((ROOT / contract).read_bytes()).hexdigest()})
    bind(dict(pins))
    output = ROOT / OUTPUT
    output.mkdir(exist_ok=False)
    (output / 'freeze.json').write_text(json.dumps(freeze, indent=2), encoding='utf8')
    local = ROOT / 'tmp/momentum_final_gate_preflight_20261105'
    local.mkdir(exist_ok=False)
    (local / 'review.json').write_text(json.dumps(dict(status='67_POTENTIAL_GATES_PASS_NOT_ACCOUNT_RUN', rows=gates), indent=2), encoding='utf8')
    print(json.dumps(dict(status=freeze['status'], source_files=len(pins), potential_gates=len(gates))))


if __name__ == '__main__':
    main()
