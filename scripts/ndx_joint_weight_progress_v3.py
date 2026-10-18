"""Read-only v3 progress using the authoritative versioned batch namespace."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_joint_weight_batch_v3 as batch
from scripts import ndx_joint_weight_progress as original
from scripts.ndx_joint_weight_verify import _restore
from backtest import ndx_joint_weight_runner as old_runner
from backtest import ndx_joint_weight_runner_v3 as runner
from backtest.ndx_joint_weight_evaluation_v2 import _bind


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect_versioned_plan(versioned):
    plan = versioned['plan']
    bundle = versioned['frozen_bundle']
    dependencies = versioned['dependencies']
    namespace = batch.namespace_hash(plan['experiment_sha256'], bundle['manifest_sha256'], dependencies)
    destination = Path(versioned['capture_destination'])
    _require(namespace == versioned['namespace_sha256']
             and destination.resolve() == (batch.BATCH_ROOT / namespace).resolve(),
             'Versioned capture namespace differs')
    _require(dependencies == batch.dependency_hashes(), 'V3 batch dependencies differ')
    snapshot = original.Snapshot()
    names = snapshot.directory(destination)
    for coordinate in plan['plans']:
        name = coordinate['child_sha256'] + '.json'
        if name not in names:
            continue
        captured = snapshot.read(destination / name)
        evidence = _restore(captured['source_evidence'])
        provenance = evidence['loader_provenance']
        _require(provenance.get('frozen_input_manifest_sha256') == bundle['manifest_sha256']
                 and old_runner._json_bytes(provenance.get('v3_batch_dependency_sources')) == old_runner._json_bytes(dependencies)
                 and provenance.get('old_results_reused') is False, 'V3 capture provenance binding differs')
        frozen = bundle['frozen'].get(coordinate['child_sha256'])
        if frozen is None:
            _require('frozen_capture' not in provenance, 'Unexpected frozen coordinate provenance')
        else:
            for field in ('frozen_capture', 'frozen_capture_internal_sha256', 'original_capture_source_evidence'):
                _require(old_runner._json_bytes(provenance.get(field)) ==
                         old_runner._json_bytes(frozen['provenance'][field]), 'Frozen coordinate provenance differs')
    namespace_values = dict(vars(old_runner))
    namespace_values.update(_source_hashes=runner.source_hashes,
                            _LOADED_SOURCE_HASHES=runner._LOADED_SOURCE_HASHES,
                            CHECKPOINT_ROOT=runner.CHECKPOINT_ROOT)
    inspect = _bind(original.inspect_plan, runner=SimpleNamespace(**namespace_values))
    report = inspect(plan, cli_hash=dependencies['scripts/ndx_joint_weight_batch_v3.py'],
                     capture_destination=destination)
    snapshot.verify()
    _require(dependencies == batch.dependency_hashes(), 'V3 batch dependencies changed during observation')
    return dict(report, namespace_sha256=namespace, checkpoint_version='v3', old_results_reused=False,
                frozen_input_manifest_sha256=bundle['manifest_sha256'])


def run(experiment_path, frozen_input_manifest_path):
    watched = [Path(__file__), Path(original.__file__)] + [ROOT / path for path in batch.original.PROTECTED]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}
    versioned = None
    try:
        versioned = batch.build_versioned_plan(experiment_path, frozen_input_manifest_path)
        return inspect_versioned_plan(versioned)
    finally:
        if versioned is not None:
            versioned['plan']['sources'].validate_unchanged()
            versioned['frozen_bundle']['sources'].validate_unchanged()
        _require(before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched},
                 'Progress source/live files changed during observation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--frozen-input-manifest', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.experiment, args.frozen_input_manifest), ensure_ascii=False, indent=2))
