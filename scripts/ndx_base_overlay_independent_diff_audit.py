"""Independently compare a sealed BASE overlay with its complete parent."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/cache/research/three_cell_corrected_cohort_overlay_20260912_v2'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(path, expected):
    sources = {}

    def read(path, expected):
        path = str(Path(path).resolve())
        raw = Path(path).read_bytes()
        assert sha(raw) == expected, path
        assert path not in sources or sources[path] == expected
        sources[path] = expected
        return json.loads(raw)

    def include(value):
        for path, expected in value['source_hashes'].items():
            path = str(Path(path).resolve())
            assert path not in sources or sources[path] == expected
            sources[path] = expected

    def verify():
        for path, expected in sources.items():
            assert sha(Path(path).read_bytes()) == expected, path

    new = read(path, expected)
    old = read(new['parent_overlay_path'], new['parent_overlay_sha256'])
    include(old)
    include(new)
    verify()
    assert new['coordinate'] == old['coordinate']
    assert len(old['records']) == len(new['records']) == 26188
    unchanged = changed = 0
    identifiers = set()
    for before, after in zip(old['records'], new['records']):
        job = before['task']['job_id']
        assert job not in identifiers
        identifiers.add(job)
        if before == after:
            unchanged += 1
            continue
        assert before['task'] == after['task']
        assert before['origin'] == after['origin'] == 'NON_EQUAL_BASE'
        assert before['status'] == 'PENDING_NUMERICAL_DELTA' and before['result'] is None
        assert after['status'] == 'AVAILABLE'
        assert after['overlay_mode'] == 'BASE_WINDOW_DELTA_COMPLETE_DATE'
        lineage = after['lineage']['completed_base_delta']
        completed = read(lineage['checkpoint_path'], lineage['checkpoint_sha256'])
        assert after['result'] == completed['result']['evaluation']['result']
        assert completed['result']['cache_checkpoint_sha256'] == before['lineage']['original_checkpoint_sha256']
        restored = dict(after)
        restored['result'] = before['result']
        restored['status'] = before['status']
        restored['overlay_mode'] = before['overlay_mode']
        restored['lineage'] = dict(after['lineage'])
        del restored['lineage']['completed_base_delta']
        assert restored == before
        changed += 1
    assert (changed, unchanged) == (966, 25222)
    assert new['available_count'] == 25810 == old['available_count'] + changed
    assert new['pending_count'] == 378 == old['pending_count'] - changed
    assert all(row['result'] is None for row in new['records'] if row['status'] == 'PENDING_NUMERICAL_DELTA')
    for flag in ('point_in_time_verified', 'promotion_allowed', 'selection_performed', 'whole_lot_executed'):
        assert new[flag] is False
    assert new['winner'] is None and new['economic_inputs_complete'] is False
    sources[str(Path(__file__).resolve())] = sha(Path(__file__).read_bytes())
    verify()
    return dict(schema='ndx_base_overlay_independent_diff_audit_v1', source_hashes=sources,
                original_count=26188, replaced_base_pending=changed, other_records_exact=unchanged,
                available_count=25810, pending_count=378, pending_results_all_none=True,
                complete_ordered_record_diff_verified=True, training_performed=False,
                point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    report = audit(FOLDER / 'overlay_20230403.json', '7da405dc341268873c1e8a9aabc45027081e46f6ef1a9b0a68a208557203b0f0')
    output = FOLDER / 'independent_diff_audit_20230403.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), sha256=sha(output.read_bytes()), sources=len(report['source_hashes']))))
