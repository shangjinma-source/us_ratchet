"""Read saved cash journals into a new partition; never dispatch or postcheck economics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'data/cache/research/cash_topup_neighbor_shard_evaluation_20261003_v1'
OUTPUT = ROOT / 'data/cache/research/cash_neighbor_interrupted_partition_20261008_v1'
WORKER = ROOT / 'scripts/ndx_cash_topup_neighbor_shard_worker_20261003.py'
WORKER_SHA = 'f61148cb64e28460055b8284c8e4cc976637394228600783b9cc9fdfd7f2515e'
JOURNAL = ROOT / 'backtest/ndx_cash_topup_neighbor_journal_research.py'
JOURNAL_SHA = 'd04eb2772432ed1fea291d699a25d4eeaac49b12aa228ee560d5d5613de8f637'
ANCHORS = {
 'started.json': 'f0d8ab2f0a4fed809a026f2f993020f529487954e1525f5b137c45c18dda684a',
 'request-dc2686d5a18447f5837e70f5936731ee/result.json': '15d9742bec44074dc09d8c23fee12bff0b9a096618f86c9cf809abb96fc138ff',
 'request-e43f19b6743e4459a4f300250d8b9353/started.json': 'a7fcd98d9c2d49848ca2f2ed20b91a23cce6ae0eff3163b1c54f85b251a5f579',
 'scenario-37-shard-00046/started.json': '458d2332fc90f0bf37cb86645b2b411195a8b5edb0fcd37ea3c8682dc57a65be',
 'scenario-37-shard-00046/journal.jsonl': '3dacfd2b9387ae951f683cb70a0680b1288c961584f17483b7f4fc58beef9cd1',
}
FLAGS = dict.fromkeys(('dispatch_authorized', 'evaluator_called', 'economic_postcheck_performed',
 'economic_winner_selected', 'account_executed', 'orders_executed', 'point_in_time_verified',
 'promotion_allowed', 'automatic_retry_allowed', 'source_process_liveness_verified'), False)
TERMINAL = ('FEASIBLE', 'INFEASIBLE', 'EXTERNALLY_REFERENCED')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)

def classify(ids, scan):
    """No economic inference: preserve each saved stage, including unknown dispatch."""
    require(type(ids) is list and len(set(ids)) == len(ids), 'Unique task order')
    require(scan['tail'] is None, 'Partial bytes need separately reviewed recovery')
    tasks = scan['tasks']
    require(len(tasks) <= len(ids), 'Bounded original prefix')
    groups = {key: [] for key in (*TERMINAL, 'RAW_SAVED_POSTCHECK_MISSING', 'UNRESOLVED_DISPATCH', 'UNDISPATCHED')}
    for position, task in enumerate(tasks):
        require(task['task_id'] == ids[position] and type(task['task_position']) is int and task['task_position'] == position, 'Exact task prefix')
        status = task['status']
        require(status in groups and status != 'UNDISPATCHED', 'Known saved state')
        require(status in TERMINAL or position == len(tasks) - 1, 'Only final attempted task may be unresolved')
        groups[status].append(ids[position])
    require(scan['undispatched_task_ids'] == ids[len(tasks):], 'Exact untouched suffix')
    groups['UNDISPATCHED'] = ids[len(tasks):]
    return groups

def inspect():
    bindings = {str(Path(__file__).resolve()): digest(Path(__file__).read_bytes())}
    def read(path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        sha = digest(raw)
        require(expected is None or sha == expected, 'Source drift: ' + str(path))
        require(str(path) not in bindings or bindings[str(path)] == sha, 'Repeated source drift')
        bindings[str(path)] = sha
        return raw
    def load(path, sha):
        module = ModuleType('_frozen_' + path.stem)
        module.__file__ = str(path)
        exec(compile(read(path, sha), str(path), 'exec'), module.__dict__)
        return module
    worker = load(WORKER, WORKER_SHA)
    journal = load(JOURNAL, JOURNAL_SHA)
    before = sorted(p.relative_to(BATCH).as_posix() for p in BATCH.rglob('*') if p.is_file())
    for relative, sha in ANCHORS.items():
        read(BATCH / relative, sha)
    saved = decode(read(BATCH / 'started.json'))
    context = saved['context']
    require(digest(encode(context)) == saved['context_sha256'], 'Original saved context')
    for path, sha in context['source_hashes'].items():
        read(path, sha)
    prior_path = BATCH / 'request-dc2686d5a18447f5837e70f5936731ee/result.json'
    prior = decode(read(prior_path))
    require(prior['context_sha256'] == saved['context_sha256'], 'Prior request context')
    require(prior['batch_started_reference'] == dict(path=str(BATCH/'started.json'), sha256=ANCHORS['started.json']), 'Prior batch anchor')
    prior_start_ref = prior['request_started_reference']
    require(Path(prior_start_ref['path']) == prior_path.parent/'started.json', 'Prior request start path')
    prior_start = decode(read(prior_start_ref['path'], prior_start_ref['sha256']))
    require(prior_start['context_sha256'] == saved['context_sha256'] and prior_start['full_shard_count'] == 324 and prior_start['full_task_count'] == 301657, 'Prior request scope')
    prior_completions = prior['completed_shard_references']
    require(len(prior_completions) == 1 and Path(prior_completions[0]['path']) == BATCH/'scenario-00-shard-00000/completion.json', 'Prior externally anchored first shard')
    for ref in prior_completions:
        read(ref['path'], ref['sha256'])
    interrupted = decode(read(BATCH/'request-e43f19b6743e4459a4f300250d8b9353/started.json'))
    require(interrupted['context_sha256'] == saved['context_sha256'] and interrupted['full_shard_count'] == 324 and interrupted['full_task_count'] == 301657 and interrupted['max_new_shards'] is None, 'Interrupted full request scope')
    for doc in (prior, prior_start, interrupted):
        for key in worker.FLAGS:
            require(doc[key] is False, 'Request scope flags')
    refs = context['input_references']
    for ref in refs.values():
        read(ref['path'], ref['sha256'])
    prep = decode(read(refs['preparation']['path'], refs['preparation']['sha256']))
    require(len(prep['rows']) == 40, 'Full 40 scenarios')
    queue = []
    position = 0
    for scenario, row in enumerate(prep['rows']):
        offset = 0
        for shard_index, shard in enumerate(row['shards']):
            require(type(shard['start']) is int and type(shard['stop']) is int and shard['start'] == offset and 0 < shard['stop'] - offset <= 1000, 'Full contiguous shard domain')
            size = shard['stop'] - offset
            queue.append(dict(scenario_index=scenario, shard_index=shard_index, global_shard_index=len(queue), global_task_start=position, global_task_stop=position+size, shard=shard, contract_reference=row['contract_reference']))
            position += size
            offset = shard['stop']
        require(offset == row['statistics']['new_candidate_count'], 'Full scenario denominator')
    require(len(queue) == 324 and position == 301657, 'Full original domain')
    groups = {key: [] for key in (*TERMINAL, 'RAW_SAVED_POSTCHECK_MISSING', 'UNRESOLVED_DISPATCH', 'UNDISPATCHED')}
    shards = []
    expected_files = set(ANCHORS) | {'request-dc2686d5a18447f5837e70f5936731ee/started.json'}
    for descriptor in queue:
        index = descriptor['global_shard_index']
        ref = descriptor['shard']
        tasks = [decode(line) for line in read(ref['path'], ref['sha256']).splitlines()]
        ids = [task['task_id'] for task in tasks]
        require(len(ids) == descriptor['global_task_stop'] - descriptor['global_task_start'], 'Exact source task count')
        contract_ref = descriptor['contract_reference']
        contract = decode(read(contract_ref['path'], contract_ref['sha256']))
        folder = BATCH / ('scenario-%02d-shard-%05d' % (descriptor['scenario_index'], descriptor['shard_index']))
        if index < 280:
            filenames = {'started.json', 'journal.jsonl'} | ({'completion.json'} if index < 279 else set())
            require({p.name for p in folder.iterdir()} == filenames, 'Exact saved shard artifacts')
            for name in filenames:
                expected_files.add((folder/name).relative_to(BATCH).as_posix())
                read(folder/name)
            start = decode(read(folder/'started.json'))
            require(encode(start['descriptor']) == encode(descriptor) and start['ordered_task_ids'] == ids and start['context_sha256'] == saved['context_sha256'] and start['contract_sha256'] == contract['contract_sha256'], 'Original shard identity')
            for key in worker.FLAGS:
                require(start[key] is False, 'Saved scope flags')
            scan = journal.inspect_journal(read(folder/'journal.jsonl'), context_sha256=saved['context_sha256'], ordered_task_ids=ids)
            if index < 279:
                worker._verify_completed(folder, descriptor, saved['context_sha256'], ids, journal, {k: refs[k] for k in ('first_started','first_raw','first_postcheck','first_audit')}, contract['contract_sha256'])
            part = classify(ids, scan)
            shards.append(dict(descriptor=descriptor, journal_reference=dict(path=str(folder/'journal.jsonl'), sha256=scan['journal_sha256']), raw_pending_record_indexes=scan['records'][-2:] if index == 279 else [], complete=scan['complete']))
        else:
            require(not folder.exists(), 'Undispatched shard unexpectedly exists')
            part = {key: [] for key in groups}
            part['UNDISPATCHED'] = ids
        for key in groups:
            groups[key].extend(part[key])
    require(set(before) == expected_files, 'No unexplained parent artifacts')
    all_ids = [task_id for values in groups.values() for task_id in values]
    require(len(all_ids) == 301657 and len(set(all_ids)) == 301657, 'Exhaustive disjoint domain')
    counts = {key: len(values) for key, values in groups.items()}
    require(counts == dict(FEASIBLE=64739, INFEASIBLE=194615, EXTERNALLY_REFERENCED=1, RAW_SAVED_POSTCHECK_MISSING=1, UNRESOLVED_DISPATCH=0, UNDISPATCHED=42301), 'Pinned interrupted partition')
    for relative in before:
        read(BATCH/relative)
    for path, sha in list(bindings.items()):
        require(digest(Path(path).read_bytes()) == sha, 'End source guard')
    require(before == sorted(p.relative_to(BATCH).as_posix() for p in BATCH.rglob('*') if p.is_file()), 'Parent namespace drift')
    return dict(schema='CASH_NEIGHBOR_INTERRUPTED_PARTITION_V1', status='SAVED_STAGES_ONLY_NO_DISPATCH_AUTHORITY', source_hashes=bindings, counts=counts, task_ids_by_saved_status=groups, saved_shards=shards, shared_structural_verifier=str(WORKER), economics_independently_verified=False, preexisting_external_completion_references=prior_completions, other_completions_are_new_snapshots=True, **FLAGS)

def publish(*, execute=False):
    require(execute is True, 'Explicit new partition publication')
    require(not OUTPUT.exists(), 'Create-only new namespace')
    report = inspect()
    report['partition_script_reference'] = dict(path=str(Path(__file__).resolve()), sha256=digest(Path(__file__).read_bytes()))
    OUTPUT.mkdir(parents=True, exist_ok=False)
    raw = encode(report)
    with (OUTPUT/'partition.json').open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require((OUTPUT/'partition.json').read_bytes() == raw, 'Durable exact partition')
    return dict(path=str(OUTPUT/'partition.json'), sha256=digest(raw))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(publish(execute=parser.parse_args().execute)))
