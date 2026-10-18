"""One additional no-prior anchored fit; reuse, never refit, its canonical result."""
import argparse
import copy
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_latest_conditional_all_k_refit_20260919 as owner

ANCHORED = 'constrained_fixed_shrinkage_turnover_anchor'
LOADED = dict(owner.LOADED)
LOADED[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
COMPARE = ('schema', 'cutoff', 'fit_start', 'fit_end', 'fit_row_count', 'fit_data_sha256',
    'targets', 'risk_chains_by_security', 'previous_target_weights', 'surviving_anchor_mass',
    'anchor_by_security', 'effective_anchor_strength', 'anchor_policy', 'declared_parameters',
    'declared_constraint_checks', 'declared_constraints_passed', 'risk_chain_projection_relaxed',
    'single_name_projection_relaxed', 'top3_projection_semantics_relaxed', 'source_hashes',
    'numerical_projection')


def compare(canonical, anchored):
    if canonical['weight_spec'] != 'constrained_fixed_shrinkage' or anchored['weight_spec'] != ANCHORED:
        raise ValueError('Explicit canonical and anchored specifications required')
    for result in (canonical, anchored):
        if result['previous_target_weights'] != {} or type(result['surviving_anchor_mass']) not in (int, float) or result['surviving_anchor_mass'] != 0:
            raise ValueError('No prior target mass required')
        if type(result['effective_anchor_strength']) not in (int, float) or result['effective_anchor_strength'] != 0:
            raise ValueError('Effective anchor must be numeric zero')
    differences = [key for key in COMPARE if owner.digest(canonical[key]) != owner.digest(anchored[key])]
    return dict(compared_fields=list(COMPARE), differing_fields=differences,
        selected_task_exact_equivalence_verified=not differences,
        all_aliases_equivalence_verified=False, with_prior_equivalence_verified=False)


def prepare(plan_path, plan_sha, canonical_path, canonical_sha):
    sources = dict(LOADED)
    plan = owner.read(plan_path, plan_sha, sources)
    ref, audit = plan['panel_reference'], plan['independent_panel_audit_reference']
    if owner.digest(plan) != owner.digest(owner.prepare(ref['path'], ref['sha256'], audit['path'], audit['sha256'])):
        raise ValueError('Complete externally bound plan differs')
    saved = owner.read(canonical_path, canonical_sha, sources)
    task, = [t for t in plan['canonical_tasks'] if t['task_id'] == saved['task']['task_id']]
    if task['weight_spec'] != 'constrained_fixed_shrinkage' or task['previous_target_weights'] is not None:
        raise ValueError('Only saved first-decision constrained task allowed')
    reference = dict(path=str(Path(plan_path).resolve()), sha256=plan_sha)
    if (saved['schema'] != 'LATEST_CONDITIONAL_ALL_K_SINGLE_REFIT_V1'
            or owner.digest(saved['task']) != owner.digest(task)
            or owner.digest(saved['plan_reference']) != owner.digest(reference)
            or type(saved['attempt_count']) is not int or saved['attempt_count'] != 1
            or any(saved[k] is not False for k in owner.FALSE)):
        raise ValueError('Canonical saved task contract differs')
    marker_path = Path(str(Path(canonical_path).resolve()) + '.started.json')
    expected = saved['historical_expected_source_hashes']
    marker = owner.read(marker_path, expected[str(marker_path)], sources)
    if owner.digest(marker) != owner.digest(dict(schema='LATEST_ALL_K_SINGLE_ATTEMPT_V1', plan_sha256=plan_sha, task_id=task['task_id'], attempt_count=1)):
        raise ValueError('Canonical attempt differs')
    required = dict(plan['historical_expected_source_hashes'])
    owner.archive.merge(required, {reference['path']: plan_sha, str(marker_path): expected[str(marker_path)]})
    if any(expected.get(p) != h for p, h in required.items()):
        raise ValueError('Canonical source closure omitted')
    if owner.digest(saved['archive_resolution']) != owner.digest(owner.declared_partition(expected, owner.archive.load_contract())):
        raise ValueError('Canonical archive metadata differs')
    owner.archive.merge(sources, expected)
    document = owner.read(ref['path'], ref['sha256'], sources)
    panel = owner.panel_io.typed_decode(document['panel'])
    selected = owner.panel_core.selected_mapping(panel, list(task['selected']))
    if owner.digest(selected) != owner.digest(task['selected']):
        raise ValueError('Selected coordinates differ')
    owner.check_result(saved['result'], task, panel)
    if owner.digest(saved['result']['source_hashes']) != owner.digest(owner.fitter._sources()):
        raise ValueError('Canonical numerical code closure differs')
    passed = saved['result']['declared_constraints_passed']
    if saved['status'] != ('FITTED_ORIGINAL_FIVE_RISKS_PASSED' if passed else 'FITTED_ORIGINAL_FIVE_RISKS_FAILED'):
        raise ValueError('Canonical risk status differs')
    owner.verify_sources(sources)
    return plan, panel, task, saved, sources


def run(plan_path, plan_sha, canonical_path, canonical_sha, output):
    output = Path(output).resolve()
    started, raw_path, failure = [Path(str(output) + suffix) for suffix in ('.started.json', '.raw.json', '.failure.json')]
    if any(p.exists() for p in (output, started, raw_path, failure)):
        raise ValueError('Existing attempt refuses another anchored fit')
    plan, panel, task, saved, sources = prepare(plan_path, plan_sha, canonical_path, canonical_sha)
    memory = owner.digest(owner.panel_io.typed_encode(panel))
    task_digest = owner.digest(task)
    saved_digest, plan_digest = owner.digest(saved), owner.digest(plan)
    marker = dict(schema='LATEST_FIRST_ANCHOR_ATTEMPT_V1', canonical_reference=dict(path=str(Path(canonical_path).resolve()), sha256=canonical_sha),
        plan_reference=dict(path=str(Path(plan_path).resolve()), sha256=plan_sha), task_id=task['task_id'], additional_fitter_calls=1)
    published = owner.exclusive_publish(started, marker)
    owner.archive.merge(sources, {published['path']: published['sha256']})
    def verify():
        if (memory != owner.digest(owner.panel_io.typed_encode(panel)) or task_digest != owner.digest(task)
                or saved_digest != owner.digest(saved) or plan_digest != owner.digest(plan)):
            raise ValueError('Probe RAM inputs changed')
        owner.verify_sources(sources)
    try:
        result = owner.fitter.refit_dynamic_cutoff_weights(returns=panel['returns'], cutoff=task['cutoff'], selected=task['selected'],
            weight_spec=ANCHORED, previous_target_weights=None, **task['parameters'])
        raw = owner.exclusive_publish(raw_path, dict(schema='LATEST_FIRST_ANCHOR_RAW_RECEIPT_V1', attempt=marker, result=result))
        owner.archive.merge(sources, {raw['path']: raw['sha256']})
        verify()
        anchored_task = copy.deepcopy(task); anchored_task['weight_spec'] = ANCHORED
        owner.check_result(result, anchored_task, panel)
        evidence = compare(saved['result'], result)
        value = dict(schema='LATEST_FIRST_ANCHOR_EQUIVALENCE_PROBE_V1', attempt=marker, raw_reference=raw,
            evidence=evidence, canonical_refitted=False, additional_fitter_calls=1,
            current_python_runtime=platform.python_version(), canonical_runtime_independently_verified=False,
            scope='ONE_SELECTED_NO_PRIOR_TASK_ONLY_NOT_ALL_ALIASES_OR_HISTORICAL_EQUIVALENCE',
            historical_expected_source_hashes=sources, archive_resolution=verify_partition(sources), **dict.fromkeys(owner.FALSE, False))
        verify(); published = owner.exclusive_publish(output, value); verify(); return published
    except BaseException as exc:
        if not failure.exists():
            owner.exclusive_publish(failure, dict(schema='LATEST_FIRST_ANCHOR_FAILED_ATTEMPT_V1', error_type=type(exc).__name__, automatic_retry_allowed=False, raw_receipt_preserved=raw_path.exists()))
        raise
    finally:
        verify()


def verify_partition(sources):
    return owner.verify_sources(sources)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('plan', 'plan-sha', 'canonical', 'canonical-sha', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.plan_sha, args.canonical, args.canonical_sha, args.output)))
