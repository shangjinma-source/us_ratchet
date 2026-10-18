"""Read-only capacity scenarios, not a resource proof or execution entry point.

No producer imports, task projection, evaluator, inspector or namespace creation.
Normal RAW bounds are transcribed from the pinned prior structural-bound report.
The metadata allowance is explicitly hypothetical until constructors are bounded.
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNT = 52_406_569
PINS = {
    'scripts/ndx_double_replacement_stream_worker_20261008.py': 'cf6eacfd44756486216c6cf1d65fd512cd2198dcc1b164b41baba3e78c8bb002',
    'scripts/ndx_double_replacement_stream_independent_readback_20261008.py': '1b2694d67b0680528c8d7db33b6e5a4fc3846a736978079fda28e0db52ef4358',
    'DYNAMIC_DOUBLE_REPLACEMENT_NORMAL_RESOURCE_BOUND_20261008.md': '793c5e8194155b5b37397c72567aa6bbf9f11c2f316b4c84520514ff866eefb4',
}
NORMAL = {
    1000: (4_509_633, 4_511_039, 229_176_864_148),
    5000: (22_521_633, 22_528_536, 228_897_391_075),
    10000: (45_036_633, 45_050_408, 228_862_454_440),
}


def scenario(batch_size, free_bytes):
    assert type(batch_size) is int and batch_size in NORMAL
    assert type(free_bytes) is int and free_bytes >= 0
    raw, compressed, full_gzip = NORMAL[batch_size]
    batches = (COUNT + batch_size - 1) // batch_size
    # Each normal point can have its own run. The longest canonical object is
    # {"start":52406568,"status":"inspected_infeasible","stop":52406569}.
    run = {'start': COUNT - 1, 'stop': COUNT, 'status': 'inspected_infeasible'}
    per_run = len(json.dumps(run, sort_keys=True, separators=(',', ':')).encode()) + 1
    run_bytes = COUNT * per_run
    margin = 5 * 1024**3
    # Not proved: all other normal metadata, both manifests, allocation slack,
    # directories and request-wide/source-map metadata amortized across batches.
    hypothetical_other_per_batch = 1024**2
    uniform_per_batch = compressed + batch_size * per_run + hypothetical_other_per_batch
    initial = full_gzip + run_bytes + batches * hypothetical_other_per_batch
    uniform_remaining = batches * uniform_per_batch
    return dict(batch_size=batch_size, batch_count=batches, tail_count=COUNT-(batches-1)*batch_size,
                normal_raw_batch_upper=raw, normal_gzip_batch_upper=compressed,
                normal_gzip_total_upper=full_gzip, normal_run_bytes_per_point_upper=per_run,
                normal_run_total_upper=run_bytes,
                metadata_headroom_after_gzip_runs_and_5gib=free_bytes-margin-full_gzip-run_bytes,
                hypothetical_other_bytes_per_batch=hypothetical_other_per_batch,
                conditional_initial_bytes=initial, conditional_uniform_remaining_bytes=uniform_remaining,
                conditional_free_after_both_gates_and_5gib=free_bytes-margin-max(initial,uniform_remaining),
                reader_existing_engineering_memory_gate_bytes=margin+32*raw,
                metadata_bound_proved=False, memory_bound_proved=False, execution_authorized=False)


def run():
    for name, expected in PINS.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    free = {drive: shutil.disk_usage(drive+':/').free for drive in ('C', 'D', 'E', 'G')}
    return dict(schema='DOUBLE_STREAM_C_CAPACITY_SCENARIOS_RESEARCH_V1',
                observed_utc=datetime.now(timezone.utc).isoformat(), source_hashes=PINS,
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                domain_count=COUNT, free_bytes=free,
                configurations=[scenario(size,free['C']) for size in NORMAL],
                suggested_namespace_only='C:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714/double_replacement_stream_evaluation_c_20261008_v1',
                namespace_created=False, evaluator_calls=0, inspector_calls=0,
                resource_proof_sha256=None, resource_envelope=None,
                metadata_bound_proved=False, memory_bound_proved=False, execution_authorized=False)


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
