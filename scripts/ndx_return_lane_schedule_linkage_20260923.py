"""Bind the saved six-target schedule to the independently audited target prefix."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/cache/research/return_lane_targets_20260923_v1'
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
AUDIT = dict(path=str(FOLDER / 'completed6_independent_readback.json'),
             sha256='ca8bf38f5090c9703da2ed8094421d3abae4324fd7837097f82ef0546b94778f')
SCHEDULE = dict(path=str(FOLDER / 'schedule.json'),
                sha256='f5ee54df3651882791e4e6ecac548d0ec7847c44a9c551938d20c17c2cb23c70')


def exact(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def build():
    sources = {str(SOURCE): LOADED_SHA}

    def merge(mapping):
        for path, checksum in mapping.items():
            if path in sources and sources[path] != checksum:
                raise ValueError('Conflicting source SHA')
            sources[path] = checksum

    def read(reference):
        raw = Path(reference['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise ValueError('Bound artifact changed')
        merge({reference['path']: reference['sha256']})
        return json.loads(raw)

    audit = read(AUDIT)
    if (audit['schema'] != 'RETURN_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1'
            or audit['status'] != 'PASSED' or audit['completed_prefix_count'] != 6
            or len(audit['details']) != 6):
        raise ValueError('Complete independently audited six-period prefix required')
    merge(audit['source_hashes'])
    plan = read(audit['plan_reference'])
    lane = read(plan['lane_prepare'])
    calendar = [row['session'] for row in read(plan['calendar'])['execution']['daily']]
    risk_chains = {}
    rows = []
    for detail, decision in zip(audit['details'], lane['decisions'], strict=True):
        choices = [item for item in decision['lanes']['RETURN'] if item['job_id'] == detail['job_id']]
        if (len(choices) != 1 or decision['cutoff'] != detail['cutoff']
                or decision['execution_date'] != detail['execution_date']):
            raise ValueError('Independent decision lineage differs')
        risk_chains[detail['cutoff']] = {sid: item['risk_chain'] for sid, item in choices[0]['selected'].items()}
        rows.append(dict(decision_date=detail['cutoff'], execution_date=detail['execution_date'], targets=detail['targets']))
    expected = dict(schema='RETURN_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',
        plan_reference=audit['plan_reference'], calendar=calendar, schedule=rows,
        risk_chains_by_decision=risk_chains,
        completed_finalization_references=audit['finalization_references'],
        final_target_reference=audit['details'][-1]['raw_reference'], all_six_targets_passed=True,
        target_anchor_uses_actual_holdings=False, whole_lot_execution_performed=False,
        member_point_in_time_verified=False, promotion_allowed=False)
    if not exact(read(SCHEDULE), expected):
        raise ValueError('Saved schedule differs from independently audited targets and risk identities')
    verify(sources)
    return dict(schema='RETURN_SIX_PERIOD_SCHEDULE_INDEPENDENT_LINKAGE_V1',
        schedule_reference=SCHEDULE, independent_target_audit_reference=AUDIT,
        exact_schedule_reconstruction=True, decision_count=6,
        target_numerical_audit_repeated=False, fitter_called=False, account_engine_called=False,
        source_hashes=sources, point_in_time_verified=False, promotion_allowed=False)


def verify(sources):
    for path, checksum in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != checksum:
            raise ValueError('Source changed: ' + path)


if __name__ == '__main__':
    value = build()
    output = FOLDER / 'schedule_independent_linkage.json'
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    verify(value['source_hashes'])
    with output.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    verify(value['source_hashes'])
    if output.read_bytes() != raw:
        raise ValueError('Published linkage changed')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(raw).hexdigest())))
