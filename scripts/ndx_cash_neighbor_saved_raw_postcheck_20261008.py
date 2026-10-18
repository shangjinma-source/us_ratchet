"""Independent arithmetic sidecar for one durable raw return; no producer dispatch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from types import ModuleType

SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
ROOT = SOURCE.parents[1]
PARTITION = ROOT/'data/cache/research/cash_neighbor_interrupted_partition_20261008_v1/partition.json'
PARTITION_SHA = '3f88cd70bd62bcac4ccf9e756031e8353b788ef6575b23a4d6565d6a4a06f120'
OUTPUT = ROOT/'data/cache/research/cash_neighbor_saved_raw_postcheck_20261008_v1'
SHARD_READER = ROOT/'scripts/ndx_cash_topup_neighbor_shard_independent_readback_20261003.py'
SHARD_READER_SHA = '39a7194291584195eed09d2b1e2d83f97cd9b53a20bd4858e192fd4ba4d728ad'
ORACLE = ROOT/'scripts/ndx_cash_topup_neighbor_single_evaluation_independent_readback_20261003.py'
ORACLE_SHA = '0106433db9e123a3786a1656e495387b8c58a0c42019be50a113b4c311176140'
JOURNAL = ROOT/'backtest/ndx_cash_topup_neighbor_journal_research.py'
JOURNAL_SHA = 'd04eb2772432ed1fea291d699a25d4eeaac49b12aa228ee560d5d5613de8f637'
TASK_ID = 'ccab63ffac599bb4781b4dffa27b23ea8b6d99778e3b4dae8ef9b8b312b13bfc'
FLAGS = dict.fromkeys(('evaluator_called','dispatch_authorized','original_journal_modified','economic_winner_selected','account_executed','orders_executed','point_in_time_verified','promotion_allowed','automatic_retry_allowed'), False)

def require(ok, message):
    if not ok:
        raise ValueError(message)

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def exact(left, right, message):
    require(encode(left) == encode(right), message)

def inspect_saved_tail(*, journal_bytes, tasks, prepared, descriptor, context_sha256, journal, reader, oracle):
    ids = [task['task_id'] for task in tasks]
    scan = journal.inspect_journal(journal_bytes, context_sha256=context_sha256, ordered_task_ids=ids)
    require(scan['tail'] is None and scan['tasks'] and not scan['complete'], 'Intact saved partial shard')
    active = scan['tasks'][-1]
    require(active['status'] == 'RAW_SAVED_POSTCHECK_MISSING' and active['raw_stage'] == 'RAW_RETURNED', 'Saved successful return only')
    require(all(task['status'] in ('FEASIBLE','INFEASIBLE') for task in scan['tasks'][:-1]), 'Exact prior terminal prefix')
    position = active['task_position']
    require(active['task_id'] == TASK_ID and len(active['record_indexes']) == 2, 'Unique original pending task')
    require(active['record_indexes'] == [scan['record_count']-2, scan['record_count']-1], 'Only final two records')
    rows = [reader.decode(line) for line in journal_bytes.splitlines()]
    start, raw = rows[-2:]
    require([start['stage'],raw['stage']] == ['TASK_STARTED','RAW_RETURNED'], 'No invented original postcheck')
    arguments = reader.task_arguments(prepared, tasks[position], descriptor['shard']['start']+position)
    expected_start = dict(task_reference=dict(path=descriptor['shard']['path'],sha256=descriptor['shard']['sha256'],jsonl_line_index=position,scenario_candidate_ordinal=tasks[position]['scenario_candidate_ordinal']), global_task_position=descriptor['global_task_start']+position, evaluation_argument_sha256=sha(encode(arguments)))
    exact(start['payload'], expected_start, 'Saved dispatch arguments and task reference')
    payload = raw['payload']
    require(set(payload) == {'result','error','explicit_evaluator_call_attempt_count','returned_evaluation_count'}, 'Exact returned envelope')
    exact(payload['explicit_evaluator_call_attempt_count'], 1, 'One original call')
    exact(payload['returned_evaluation_count'], 1, 'One saved return')
    require(payload['error'] is None, 'No arithmetic invented for exception')
    independently_reconstructed = oracle.independent_result(arguments)
    exact(payload['result'], independently_reconstructed, 'Independent full financial and five risk result')
    detail = reader.expected_detail(prepared, independently_reconstructed)
    return dict(task_id=TASK_ID, task_position=position, global_task_position=descriptor['global_task_start']+position, context_sha256=context_sha256, journal_sha256=sha(journal_bytes), raw_record_reference=scan['records'][-1], dispatch_record_reference=scan['records'][-2], independent_postcheck=detail, saved_arithmetic_independently_verified=True, independently_checked_task_count=1, prior_terminal_prefix_arithmetic_checked=False, original_postcheck_existed=False, **FLAGS)

def publish(*, execute=False):
    require(execute is True, 'Explicit new sidecar action')
    require(type(PARTITION_SHA) is str and len(PARTITION_SHA)==64 and all(c in '0123456789abcdef' for c in PARTITION_SHA), 'Bind actual reviewed partition before IO')
    require(not OUTPUT.exists(), 'Create-only sidecar')
    require(sha(SOURCE.read_bytes()) == LOADED_SHA, 'Loaded sidecar source unchanged')
    bindings = {str(SOURCE): LOADED_SHA}
    def read(path, digest):
        path = Path(path).resolve()
        raw = path.read_bytes()
        require(sha(raw) == digest, 'Frozen source bytes: '+str(path))
        require(str(path) not in bindings or bindings[str(path)] == digest, 'Repeated source binding')
        bindings[str(path)] = digest
        return raw
    def load(path, digest):
        module = ModuleType('_saved_raw_'+path.stem)
        module.__file__ = str(path)
        exec(compile(read(path,digest),str(path),'exec'),module.__dict__)
        return module
    reader = load(SHARD_READER, SHARD_READER_SHA)
    oracle = load(ORACLE, ORACLE_SHA)
    journal = load(JOURNAL, JOURNAL_SHA)
    partition = reader.decode(read(PARTITION, PARTITION_SHA))
    require(partition['schema']=='CASH_NEIGHBOR_INTERRUPTED_PARTITION_V1' and partition['status']=='SAVED_STAGES_ONLY_NO_DISPATCH_AUTHORITY', 'Reviewed partition schema')
    exact(partition['task_ids_by_saved_status']['RAW_SAVED_POSTCHECK_MISSING'], [TASK_ID], 'Exactly one saved pending return')
    require(partition['dispatch_authorized'] is False and partition['automatic_retry_allowed'] is False, 'No dispatch authority')
    shard = partition['saved_shards'][-1]
    descriptor = shard['descriptor']
    require(descriptor['global_shard_index']==279 and shard['complete'] is False, 'Original interrupted shard')
    source_hashes = partition['source_hashes']
    def bound(path):
        return read(path,source_hashes[str(Path(path).resolve())])
    raw_path = Path(shard['journal_reference']['path'])
    raw = bound(raw_path)
    require(sha(raw)==shard['journal_reference']['sha256'], 'Partition raw link')
    start = reader.decode(bound(raw_path.parent/'started.json'))
    exact(start['descriptor'],descriptor,'Original descriptor')
    prepared = reader.decode(bound(descriptor['contract_reference']['path']))
    require(sha(encode(prepared['contract']))==prepared['contract_sha256']==start['contract_sha256'], 'Original full contract')
    tasks = [reader.decode(line) for line in bound(descriptor['shard']['path']).splitlines()]
    exact(start['ordered_task_ids'],[task['task_id'] for task in tasks],'Full source task order')
    require(len(tasks)==descriptor['global_task_stop']-descriptor['global_task_start'], 'Full source shard')
    result = inspect_saved_tail(journal_bytes=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,context_sha256=start['context_sha256'],journal=journal,reader=reader,oracle=oracle)
    exact([result['dispatch_record_reference'],result['raw_record_reference']],shard['raw_pending_record_indexes'],'Exact partition offsets')
    result.update(schema='CASH_NEIGHBOR_SAVED_RAW_INDEPENDENT_POSTCHECK_V1', status='PASS_SAVED_RAW_ARITHMETIC_ONLY', partition_reference=dict(path=str(PARTITION),sha256=PARTITION_SHA), source_hashes=bindings)
    for path,digest in bindings.items():
        require(sha(Path(path).read_bytes())==digest,'Final source guard')
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        encoded = encode(result)
        with (OUTPUT/'independent_postcheck.json').open('xb') as stream:
            stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        require((OUTPUT/'independent_postcheck.json').read_bytes()==encoded,'Durable exact sidecar')
        for path,digest in bindings.items():
            require(sha(Path(path).read_bytes())==digest,'Post-publication source guard')
        return dict(path=str(OUTPUT/'independent_postcheck.json'),sha256=sha(encoded))
    except BaseException as error:
        failure = dict(status='FAILED_SIDECAR_DO_NOT_CONSUME', error_type=type(error).__name__, **FLAGS)
        with (OUTPUT/'failure.json').open('xb') as stream:
            stream.write(encode(failure));stream.flush();os.fsync(stream.fileno())
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    print(json.dumps(publish(execute=parser.parse_args().execute)))
