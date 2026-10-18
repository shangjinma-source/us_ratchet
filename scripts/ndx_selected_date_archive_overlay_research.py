"""Consume a complete selected date with explicit immutable archive source resolution."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_selected_date_overlay_research as merger
from backtest import ndx_exact_price_cache_drift_research as drift
from scripts import ndx_selected_completed_queue_independent_audit_20260919 as independent
from scripts import ndx_selected_archive_completed_independent_audit_20260919 as audited_archive
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_joint_weight_verify import _restore
from scripts.ndx_base_three_cell_window_delta_research import publish

INVENTORY = ROOT / 'data/cache/research/three_cell_corrected_paired_overlay_20260919_v2/all15_consumption_inventory_20260919.json'
INVENTORY_SHA = 'b1308d0a50cb3c3ab2a6b4b5720c170f0c05ce4419a47d4be2e3a13be260c3de'
PLAN, PLAN_SHA = drift.SELECTED_PLAN, drift.SELECTED_PLAN_SHA
MANIFEST, MANIFEST_SHA = independent.MANIFEST, independent.MANIFEST_SHA
LOADED = {str(p): drift.file_sha(p) for p in (Path(__file__).resolve(), Path(merger.__file__).resolve(),
    Path(merger.digest.__code__.co_filename).resolve(), drift.SOURCE, Path(independent.__file__).resolve(),
    Path(_restore.__code__.co_filename).resolve(), Path(publish.__code__.co_filename).resolve())}
LOADED.update(audited_archive.LOADED)
LOADED[str(archive.SOURCE)] = archive.LOADED
RESOLUTION_SCHEMA = 'IMMUTABLE_ROOT_PRICE_ARCHIVE_V1'
FLAGS = ('historical_full_source_closure_verified', 'original_historical_provenance_verified', 'point_in_time_verified', 'promotion_allowed')


def complete_date_rows(index, audit, manifest, date):
    """Global PARTIAL is acceptable; partial membership of this date is not."""
    ids = audited_archive.check_index(index, manifest, audit['manifest'])
    if (audit['schema'] != audited_archive.SCHEMA
            or type(audit['planned']) is not int or type(audit['completed']) is not int
            or audit['planned'] != len(manifest['tasks']) or audit['completed'] != len(ids)
            or audit['status'] != index['status'] or audit['completed_queue_all_tasks_audited'] is not True
            or [r['new_job_id'] for r in audit['tasks']] != ids):
        raise ValueError('Matching full completed-prefix independent audit required')
    expected = [r for r in manifest['tasks'] if r['task']['selection_date'] == date]
    if not expected or not {r['new_job_id'] for r in expected} <= set(ids):
        raise ValueError('Whole selected date is not completed; partial prefix cannot replace date')
    for row, saved in zip(manifest['tasks'], audit['tasks']):
        if not independent.exact(row['task'], saved['task']):
            raise ValueError('Audited full task differs')
        for key, maximum in (('scalar_max_error', 1e-12), ('all_windows_max_error', 1e-12), ('legacy_close_max_error', 1e-8)):
            if type(saved[key]) not in (int, float) or not math.isfinite(saved[key]) or not 0 <= saved[key] <= maximum:
                raise ValueError('Independent numerical error exceeds declared scope')
        independent.require_false(saved, ('saved_non20_fields_independently_recomputed', 'binary_float_ledger_hash_independently_verified'))
    return expected


def plan_gaps(plan):
    by_value = {json.dumps(g, sort_keys=True): g for v in plan['historical_context_gap_observations'].values() for g in v['gaps']}
    return [by_value[k] for k in sorted(by_value)]


def verify(value):
    required = dict(LOADED, **{str(INVENTORY): INVENTORY_SHA, str(PLAN): PLAN_SHA, str(MANIFEST): MANIFEST_SHA})
    sources = value['historical_expected_source_hashes']
    if any(sources.get(p) != h for p, h in required.items()):
        raise ValueError('Missing loaded source or hard input authority')
    if value.get('source_resolution_schema') != RESOLUTION_SCHEMA or 'verified_source_hashes' in value or 'historical_price_cache_gap_observations' in value:
        raise ValueError('Explicit archive partition required, not original live verification')
    independent.require_false(value, FLAGS + ('selection_performed', 'saved_non20_fields_independently_recomputed',
        'binary_float_ledger_hash_independently_verified', 'nominal_quote_authenticity_verified', 'dynamic_next_open_execution_validated',
        'original_live_price_paths_verified', 'original_strict_source_verification_passed'))
    checked = archive.verify_expected_sources(sources, archive.load_contract())
    if not independent.exact(checked, value['archive_resolution']):
        raise ValueError('Explicit archive source partitions differ')
    if len(checked['archive_resolutions']) != 85 or len(checked['historical_gap_observations']) != 26:
        raise ValueError('Exact archive 85/26 required')
    plan = json.loads(PLAN.read_bytes())
    if not independent.exact(plan_gaps(plan), value['historical_loader_gap_observations']):
        raise ValueError('Exact original loader gap metadata differs')
    independent.verify_gaps(value['historical_loader_gap_observations'])


def verify_parent_partition(parent, contract):
    expected = parent['historical_expected_source_hashes']
    old = drift.load_contract()
    gaps = [dict(old['exceptions'][p], path=p, historical_bytes_verified=False,
                 current_observation_unchanged=True) for p in expected if p in old['exceptions']]
    # These are original saved disclosures, never assertions about today's root CSV.
    if not independent.exact(gaps, parent['historical_price_cache_gap_observations']):
        raise ValueError('Original parent gap metadata differs from sealed authority')
    for p, h in expected.items():
        if p not in old['exceptions'] and parent['verified_source_hashes'].get(p) != h:
            raise ValueError('Parent omitted original verified dependency')
    combined = dict(expected)
    archive.merge(combined, parent['verified_source_hashes'])
    archive.verify_expected_sources(combined, contract)


def build(*, date, index_path, index_sha256, audit_path, audit_sha256):
    sources = dict(LOADED)
    def include(mapping):
        for p, h in mapping.items():
            p = str(Path(p).resolve())
            if p in sources and sources[p] != h:
                raise ValueError('Source conflict')
            sources[p] = h
    def read(p, h):
        p = str(Path(p).resolve())
        raw = Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest() != h:
            raise ValueError('External reviewed artifact SHA differs')
        include({p: h})
        return json.loads(raw)
    inventory = read(INVENTORY, INVENTORY_SHA)
    ref, = [r for r in inventory['dates'] if r['date'] == date.replace('-', '')]
    parent = read(ref['overlay_path'], ref['overlay_sha256'])
    if parent['coordinate']['selection_date'] != date or parent['records_sha256'] != merger.digest(parent['records']):
        raise ValueError('Hard parent date/records differ')
    plan = read(PLAN, PLAN_SHA)
    manifest = read(MANIFEST, MANIFEST_SHA)
    if (manifest['tasks'] != [r for d in plan['dates'] for r in d['tasks']] or manifest['planned'] != 11254
            or manifest['context_count'] != 161 or manifest['parent_plan_sha256'] != PLAN_SHA):
        raise ValueError('Hard selected manifest/plan differs')
    index = read(index_path, index_sha256)
    audit = read(audit_path, audit_sha256)
    if (audit['live_verified_source_hashes'].get(str(Path(index_path).resolve())) != index_sha256
            or audit['completed_index'] != dict(path=str(Path(index_path).resolve()), sha256=index_sha256)):
        raise ValueError('Independent audit does not bind this exact index')
    archive_manifest = read(audit['manifest']['path'], audit['manifest']['sha256'])
    if (archive_manifest.get('schema') != 'SELECTED_ARCHIVE_RESOLUTION_MANIFEST_V1'
            or archive_manifest['legacy_manifest'] != dict(path=str(MANIFEST), sha256=MANIFEST_SHA)
            or archive_manifest['parent_plan'] != dict(path=str(PLAN), sha256=PLAN_SHA)
            or archive_manifest['archive_manifest'] != dict(path=str(archive.ARCHIVE), sha256=archive.ARCHIVE_SHA)
            or not independent.exact(archive_manifest['tasks'], manifest['tasks'])
            or not independent.exact(archive_manifest['corrections'], manifest['corrections'])):
        raise ValueError('Archive manifest must retain exact original full plan')
    independent.require_false(archive_manifest, audited_archive.FLAGS)
    rows = complete_date_rows(index, audit, archive_manifest, date)
    audited_archive.verify_report(audit)
    for mapping in (plan['source_hashes'], manifest['historical_expected_source_hashes'],
            parent['historical_expected_source_hashes'], parent['verified_source_hashes'],
            index['finalization']['historical_expected_source_hashes'], index['finalization']['additional_provenance_hashes'],
            archive_manifest['implementation_source_hashes'], audit['historical_expected_source_hashes']):
        include(mapping)
    contract = archive.load_contract()
    verify_parent_partition(parent, contract)
    final = index['finalization']
    finalized = dict(final['historical_expected_source_hashes'])
    archive.merge(finalized, final['additional_provenance_hashes'])
    checked = archive.verify_expected_sources(finalized, contract)
    for key in ('live_verified_source_hashes', 'archive_resolutions', 'historical_gap_observations'):
        if not independent.exact(final[key], checked[key]):
            raise ValueError('Finalized archive partition differs')
    if any(final['historical_expected_source_hashes'].get(p) != h for p, h in manifest['historical_expected_source_hashes'].items()):
        raise ValueError('Finalization omitted original manifest dependency')
    archive.verify_expected_sources(sources, contract)
    old_ref = archive_manifest['legacy_completed_index']
    old_index = read(old_ref['path'], old_ref['sha256'])
    seed = read(independent.SEED, independent.SEED_SHA)
    old_ids = independent.check_index(old_index, manifest, [r['new_job_id'] for r in seed['tasks']])
    if archive_manifest['legacy_completed_count'] != len(old_ids):
        raise ValueError('Legacy import denominator differs')
    legacy_entries = dict(zip(old_ids, old_index['completed']))
    for identifier, entry in legacy_entries.items():
        if Path(entry['path']).resolve() != independent.FOLDER / 'tasks' / (identifier + '.json'):
            raise ValueError('Original legacy task address differs')
    pairs = list(zip(manifest['tasks'], index['completed']))
    entries = {r['new_job_id']: e for r, e in pairs}
    audited = {r['new_job_id']: r for r in audit['tasks']}
    replacements = []
    for row in rows:
        entry = entries[row['new_job_id']]
        if Path(entry['path']).resolve() != Path(index_path).resolve().parent / (row['new_job_id'] + '.json'):
            raise ValueError('External checkpoint coordinate differs')
        if audit['live_verified_source_hashes'].get(entry['path']) != entry['sha256']:
            raise ValueError('Independent audit omitted exact completed checkpoint')
        wrapper = read(entry['path'], entry['sha256'])
        if wrapper['mode'] != audited[row['new_job_id']]['archive_wrapper_mode']:
            raise ValueError('Audited wrapper mode differs')
        value = audited_archive.audit_view(wrapper, row, audit['manifest'], legacy_entries.get(row['new_job_id']), read)
        result = value['result']
        if (value['schema'] != 'ndx_selected_delta_exact_gap_task_v1' or value['new_job_id'] != row['new_job_id']
                or not independent.exact(value['original'], row) or value['manifest_path'] != str(MANIFEST)
                or value['manifest_sha256'] != MANIFEST_SHA or not independent.exact(result['original_task'], row['task'])):
            raise ValueError('Selected checkpoint complete task/source identity differs')
        independent.require_false(value, FLAGS + ('non20_risk_projection_fields_independently_recomputed',))
        independent.require_false(result, ('original_result_reproduced', 'window_fit_reuse_performed', 'old_window_targets_available',
            'original_historical_provenance_verified', 'point_in_time_verified', 'promotion_allowed', 'selection_performed', 'no_fit_reuse'))
        if (type(result['old_input_numerical_evaluation_count']) is not int or result['old_input_numerical_evaluation_count'] != 0
                or type(result['new_input_numerical_evaluation_count']) is not int or result['new_input_numerical_evaluation_count'] != 1
                or result['exact_three_return_cells_only'] is not True or value['saved_result_revalidation_scope'] != independent.SCOPE):
            raise ValueError('Full new-input-only evaluation scope differs')
        context = read(row['context_path'], row['context_sha256'])
        checkpoint = read(row['checkpoint_path'], row['checkpoint_sha256'])
        if (result['schema'] != 'ndx_delta_selected_input_research_v1'
                or result['nominal_execution_semantics'] != 'ORIGINAL_V3_UNCHANGED'
                or result['reconstruction_scope'] != 'NEW_INPUT_FULL_V3_WITH_HISTORICAL_LOADER_PROVENANCE_GAP'
                or result['actual_runtime_matches_original_context'] is not True
                or not independent.exact(result['observed_runtime'], row['runtime'])
                or not independent.exact(context['runtime'], row['runtime'])
                or not any(independent.exact(t, row['task']) for t in context['tasks'])):
            raise ValueError('Complete numerical runtime/context provenance differs')
        payload = dict(checkpoint)
        self_sha = payload.pop('checkpoint_sha256')
        if (independent.digest(payload) != self_sha or checkpoint['context_sha256'] != independent.digest(context)
                or not independent.exact(checkpoint['task'], row['task']) or checkpoint['status'] != 'EVALUATED'
                or result['original_result_lineage_sha256'] != independent.digest(checkpoint['result'])):
            raise ValueError('Original checkpoint content binding differs')
        if (value['input_digests']['original'] != independent.digest(context['prepared_inputs'])
                or value['input_digests']['corrected'] != audited[row['new_job_id']]['independent_three_cell_input_sha256']
                or result['new_input_sha256'] != value['input_digests']['corrected']
                or result['original_input_sha256'] != value['input_digests']['original']
                or result['historical_loader_provenance_gaps'] != plan['historical_context_gap_observations'][row['context_path']]['gaps']):
            raise ValueError('Audited new typed input or loader gap differs')
        replacements.append(dict(task=row['task'], original_result=_restore(checkpoint['result']), result=result['result'],
            lineage=dict(checkpoint_path=entry['path'], checkpoint_sha256=entry['sha256'], complete_prefix_index_path=str(Path(index_path).resolve()),
                complete_prefix_index_sha256=index_sha256, independent_audit_path=str(Path(audit_path).resolve()), independent_audit_sha256=audit_sha256)))
        del value, result, context, checkpoint, payload
    output = merger.extend_selected_date(parent=parent, replacements=replacements, expected_tasks=[r['task'] for r in rows])
    partition = archive.verify_expected_sources(sources, contract)
    for key in ('source_hashes', 'verified_source_hashes', 'historical_price_cache_gap_observations'):
        output.pop(key, None)
    output.update(historical_expected_source_hashes=sources, source_resolution_schema=RESOLUTION_SCHEMA, archive_resolution=partition,
        original_live_price_paths_verified=False, original_strict_source_verification_passed=False,
        historical_loader_gap_observations=plan_gaps(plan),
        input_artifact_binding_verified=True, parent_overlay_path=ref['overlay_path'], parent_overlay_sha256=ref['overlay_sha256'],
        numerical_audit_scope=independent.SCOPE, completed_selected_date_task_count=len(rows),
        global_selected_queue_complete=index['status'] == 'COMPLETE')
    verify(output)
    return output


def publish_verified(path, value):
    if Path(path).exists():
        raise FileExistsError('Verify existing date output instead of overwriting')
    verify(value)
    saved = publish(path, value)
    verify(value)
    return saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('date', 'index-path', 'index-sha256', 'audit-path', 'audit-sha256', 'output'):
        parser.add_argument('--' + key, required=True)
    options = vars(parser.parse_args())
    output = options.pop('output')
    value = build(**options)
    print(json.dumps(publish_verified(output, value)))
