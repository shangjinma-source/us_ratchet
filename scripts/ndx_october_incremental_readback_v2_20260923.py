"""October 425: authenticate explicit ancestry; audit only the 224 new fits."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_october_incremental_readback_20260923 as previous_reader

original = previous_reader.original
SOURCE = Path(__file__).resolve()
PREVIOUS_READER_SHA = 'd411af85b645f82d4b10a34a7a29263afef72d0148bb8c777e76252e96604b4e'
FINAL = dict(path=str(previous_reader.SEED.parent / '20231002/index_b1e420fdc7661fe9617699eb530b765b8fb472f33c3fa8677cfffe00bf4501e6.json'),
             sha256='a3bd033a029ced8ded481b3da3ca3fa3b9b096863ac0552e70f88b889d54cadb')
COUNTS = (425, 401, 301, 201, 101, 1)
SINGLE = ROOT / 'scripts/ndx_corrected_frontier_single_refit_archive_research.py'
LOADED = dict(previous_reader.LOADED)
original.archive.merge(LOADED, {str(Path(previous_reader.__file__).resolve()): PREVIOUS_READER_SHA,
                               str(SOURCE): hashlib.sha256(SOURCE.read_bytes()).hexdigest()})


def partition_metadata(expected, contract):
    """Metadata only; build authenticates the complete union of bytes separately."""
    live = dict(contract['authority_source_hashes'])
    resolved, gaps = [], []
    for path, checksum in expected.items():
        row = contract['rows'].get(path)
        if row is None:
            original.archive.merge(live, {path: checksum})
            continue
        if checksum != row['expected_historical_sha256']:
            raise ValueError('Historical archive identity differs')
        evidence = dict(original_path=path, expected_historical_sha256=checksum,
                        archived_path=row['archived_path'], archived_sha256=row['archived_sha256'],
                        original_live_path_verified=False)
        if row['historical_expected_bytes_preserved']:
            resolved.append(dict(evidence, historical_bytes_exact=True))
        else:
            gaps.append(dict(evidence, historical_bytes_recovered=False,
                             role='SEALED_CURRENT_OBSERVATION_NOT_HISTORICAL_BYTES'))
    return dict(live_verified_source_hashes=live, archive_resolutions=resolved,
                historical_gap_observations=gaps, historical_full_source_closure_recovered=False,
                point_in_time_verified=False, promotion_allowed=False)


def validate_lineage(final_reference, final, seed_reference, required_base, queue, read_reference, *, counts=COUNTS):
    """A narrow same-folder content-addressed chain, not an index-name exemption."""
    folder = Path(final_reference['path']).resolve().parent
    reference, value = final_reference, final
    seen, lineage, union = set(), [], {}
    seed_reached = False
    for ordinal, count in enumerate(counts):
        path = Path(reference['path'])
        if (not path.is_absolute() or str(path.resolve()) != reference['path'] or path.parent != folder
                or path.name != 'index_' + original.pure.digest(value) + '.json'
                or reference['path'] in seen):
            raise ValueError('Noncanonical, foreign, cyclic or false-address ancestry')
        seen.add(reference['path'])
        original.validate_index(value, queue)
        if len(value['completed']) != count or value['completed'] != final['completed'][:count]:
            raise ValueError('Exact decreasing October ancestor prefix required')
        if reference == seed_reference:
            if count != 201:
                raise ValueError('Seed authority appears at wrong prefix')
            seed_reached = True
        declared = value['finalization']['historical_expected_source_hashes']
        required = dict(required_base)
        for entry in value['completed']:
            if set(entry) != {'job_id', 'started', 'result'}:
                raise ValueError('Exact completed entry required')
            for key, suffix in (('started', '.started.json'), ('result', '.json')):
                artifact = entry[key]
                if set(artifact) != {'path', 'sha256'} or artifact['path'] != str(folder / (entry['job_id'] + suffix)):
                    raise ValueError('Ancestor artifact address differs')
                original.archive.merge(required, {artifact['path']: artifact['sha256']})
        if any(declared.get(path) != checksum for path, checksum in required.items()):
            raise ValueError('Required non-index source omitted or changed')
        extra = {path: checksum for path, checksum in declared.items() if path not in required}
        expected_edges = 0 if ordinal == len(counts)-1 else 1
        if len(extra) != expected_edges:
            raise ValueError('Exact immediate-parent source edge required')
        for path, checksum in required.items():
            if final['finalization']['historical_expected_source_hashes'].get(path) != checksum:
                raise ValueError('Ancestor non-index source absent from final direct closure')
        original.archive.merge(union, declared)
        original.archive.merge(union, {reference['path']: reference['sha256']})
        lineage.append(dict(reference=deepcopy(reference), completed=count,
                            archive_resolution=deepcopy(value['finalization']['archive_resolution'])))
        if extra:
            parent_path, checksum = next(iter(extra.items()))
            parent = Path(parent_path)
            if (not parent.is_absolute() or str(parent.resolve()) != parent_path or parent.parent != folder
                    or not parent.name.startswith('index_') or parent.suffix != '.json'):
                raise ValueError('Only same-folder producer index may be an ancestry edge')
            reference = dict(path=parent_path, sha256=checksum)
            value = read_reference(reference)
    if not seed_reached:
        raise ValueError('Exact externally audited 201 ancestor was not reached')
    return lineage, union


def build():
    sources = dict(LOADED)
    if original.archive.drift.file_sha(Path(original.__file__)) != previous_reader.READER_SHA:
        raise ValueError('Frozen October inspector differs')
    def read(reference):
        path = Path(reference['path']).resolve()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['sha256']:
            raise ValueError('External artifact SHA differs')
        original.archive.merge(sources, {str(path): reference['sha256']})
        return json.loads(raw)
    seed_reference = dict(path=str(previous_reader.SEED), sha256=previous_reader.SEED_SHA)
    seed = read(seed_reference)
    prior = read(seed['index'])
    queue = read(dict(path=str(original.QUEUE), sha256=original.QUEUE_SHA))
    context = read(dict(path=str(original.CONTEXT), sha256=original.CONTEXT_SHA))
    final = read(FINAL)
    candidates = original.validate_index(final, queue)
    previous_reader.check_prefix(seed, prior, final)
    if (queue['context'] != dict(path=str(original.CONTEXT), sha256=original.CONTEXT_SHA)
            or queue['original_runtime'] != context['runtime'] or queue['historical_cutoff'] != '2023-09-29'):
        raise ValueError('Original October cutoff/runtime differs')
    required_base = dict(queue['historical_expected_source_hashes'])
    original.archive.merge(required_base, {str(original.QUEUE): original.QUEUE_SHA,
        str(original.CORE): LOADED[str(original.CORE)], str(original.RUNNER): LOADED[str(original.RUNNER)],
        str(SINGLE): prior['finalization']['historical_expected_source_hashes'][str(SINGLE)]})
    lineage, union = validate_lineage(FINAL, final, seed['index'], required_base, queue, read)
    original.archive.merge(sources, union)
    original.archive.merge(sources, seed['historical_expected_source_hashes'])
    original.archive.merge(sources, queue['historical_expected_source_hashes'])
    contract = original.archive.load_contract()
    # Authenticate all immutable old bytes once, without any old numerical audit.
    original.archive.verify_expected_sources(sources, contract)
    for document in (seed, queue):
        if partition_metadata(document['historical_expected_source_hashes'], contract) != document['archive_resolution']:
            raise ValueError('Sealed source partition differs')
    for node in lineage:
        document = read(node['reference'])
        finalization = document['finalization']
        if (finalization['historical_loader_gap_observations'] != queue['historical_loader_gap_observations']
                or partition_metadata(finalization['historical_expected_source_hashes'], contract) != finalization['archive_resolution']):
            raise ValueError('Ancestor gap observations or source partition differ')
    original.verify_gaps(queue['historical_loader_gap_observations'])
    details = deepcopy(seed['details'])
    for entry in final['completed'][201:]:
        value, attempt = read(entry['result']), read(entry['started'])
        result = original.validate_task(value, attempt, queue, final, candidates)
        if value['job_id'] != entry['job_id']:
            raise ValueError('Index and result task differ')
        detail = dict(job_id=entry['job_id'], status=result['status'], result_reference=entry['result'], typed_decimal=None)
        if result['refit'] is not None:
            detail['typed_decimal'] = original.pure.inspect_context(context, queue, result)
            checks = detail['typed_decimal']['decimal_risks']['checks']
            if (original.pure.digest(checks) != original.pure.digest(result['independently_recomputed_five_checks'])
                    or result['status'] != ('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED')):
                raise ValueError('New independent October risks differ')
        else:
            detail.update(error_type=result['error_type'], error=result['error'], numerical_failure_is_economic_infeasibility=False)
        details.append(detail)
    if len(details) != 425:
        raise ValueError('Full 425-account denominator required')
    return dict(schema='OCTOBER_INCREMENTAL_INDEPENDENT_READBACK_V2', seed_audit_reference=seed_reference,
        index=FINAL, ancestor_index_references=[node['reference'] for node in lineage],
        ancestor_completed_counts=list(COUNTS), transitive_index_ancestry_verified=True,
        non_index_sources_directly_closed=True, reused_independently_audited_count=201,
        newly_numerically_audited_count=224, planned=425, completed=425, status='COMPLETE', details=details,
        fitted_count=sum(detail['typed_decimal'] is not None for detail in details),
        numerical_failure_count=sum(detail['typed_decimal'] is None for detail in details),
        historical_expected_source_hashes=sources, archive_resolution=original.archive.verify_expected_sources(sources, contract),
        fitter_called=False, owner_check_fitted_called=False, old_numerical_audits_repeated=False,
        historical_full_source_closure_verified=False, projection_metadata_independently_recomputed=False,
        optimizer_optimality_proved=False, point_in_time_verified=False, promotion_allowed=False,
        performance_or_dual_benchmark_pass_claimed=False)


def build_and_publish(path):
    value = build()
    contract = original.archive.load_contract()
    if original.archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) != value['archive_resolution']:
        raise ValueError('Sources changed before publication')
    reference = original.publish(path, value)
    raw = Path(reference['path']).read_bytes()
    if (hashlib.sha256(raw).hexdigest() != reference['sha256'] or json.loads(raw) != value
            or original.archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) != value['archive_resolution']):
        raise ValueError('Published bytes or sources changed')
    return reference


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(build_and_publish(parser.parse_args().output)))
