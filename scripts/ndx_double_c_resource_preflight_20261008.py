"""Read-only C contract/cap census; does not call execute or any economic code."""
import hashlib
import json
import platform
import shutil
import sys
import zlib
from pathlib import Path
from scripts import ndx_double_replacement_c_stream_worker_20261008 as worker
from scripts import ndx_double_replacement_c_stream_independent_readback_20261008 as reader


def run(registration_path=None):
    source_hash=worker.filehash(worker.SOURCE)
    reader_hash=reader.filehash(reader.SOURCE)
    contract_hash=worker.filehash(worker.RESOURCE_CONTRACT_PATH)
    contract=worker.expected_resource_contract()
    assert json.loads(worker.RESOURCE_CONTRACT_PATH.read_bytes())==contract
    reference=contract['normal_bound_reference'];raw=Path(reference['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==reference['sha256']
    prior=json.loads(raw)
    acceptance_path=worker.ROOT/'research_contracts/double_stream_c_resource_acceptance_20261008_v1.json'
    acceptance_ref=worker.ref(acceptance_path,worker.filehash(acceptance_path))
    reader.check_acceptance(json.loads(acceptance_path.read_bytes()),worker.ref(worker.RESOURCE_CONTRACT_PATH,contract_hash),contract)
    references={role:worker.ref(worker.ROOT/path,sha)for role,(path,sha)in worker.BOUND.items()}
    for role,name in (('lifecycle','ndx_double_replacement_batch_lifecycle_research.py'),('stream','ndx_double_replacement_stream_request_research.py')):
        path=worker.ROOT/'backtest'/name;references[role]=worker.ref(path,worker.filehash(path))
    witness=dict(schema='DOUBLE_REPLACEMENT_C_STREAM_BATCH_REGISTRATION_V1',input_references=references,
                 worker_reference=worker.ref(worker.SOURCE,source_hash),domain_counts=worker.COUNTS,flags=worker.FLAGS,
                 output_directory=str(worker.OUTPUT),resource_envelope=worker.ENGINEERING_ENVELOPE,
                 resource_proof_reference=acceptance_ref,resource_contract_reference=worker.ref(worker.RESOURCE_CONTRACT_PATH,contract_hash),
                 resource_claims=worker.RESOURCE_CLAIMS,request_index=0,prior_request_reference=None,batch_size=10000,request_batch_limit=5241)
    actual_registration=registration_path is not None
    registration_path=Path(registration_path)if actual_registration else worker.ROOT/'research_contracts/double_stream_c_registration_20261008_v1.json'
    registration_raw=registration_path.read_bytes()if actual_registration else worker.encode(witness)
    if actual_registration:assert json.loads(registration_raw)==witness
    assert len(worker.encode(str(registration_path.resolve())))<=worker.METADATA_LIMITS['registration_path_json_bytes']
    assert len(registration_raw)<=reader.METADATA_LIMITS['request_file_bytes']
    assert reader.METADATA_LIMITS==worker.METADATA_LIMITS and reader.ENGINEERING_ENVELOPE==worker.ENGINEERING_ENVELOPE
    assert reader.RESOURCE_CONTRACT_PATH==worker.RESOURCE_CONTRACT_PATH and reader.PARENT==worker.OUTPUT
    # V3 witnesses use the exact same proposed C output folder. The only batch
    # input path that remains caller selected is the registration path, capped
    # before IO at <=1024 encoded bytes. Adding that entire cap overcounts its
    # old length and bounds all unchanged fixed per-batch constructors.
    batch_upper=max(prior['batch_fixed_metadata'].values())+worker.METADATA_LIMITS['registration_path_json_bytes']
    added=dict(resource_contract_reference=worker.ref(worker.RESOURCE_CONTRACT_PATH,'f'*64),resource_claims=worker.RESOURCE_CLAIMS)
    added_bytes=len(worker.encode(added))
    # Count the old complete document AND the complete new source-map/runtime
    # allowances, rather than subtracting known shorter old fields.
    request_upper=max(prior['request_metadata'].values())+worker.METADATA_LIMITS['source_map_json_bytes']+3*worker.METADATA_LIMITS['runtime_string_json_bytes']+added_bytes+1024
    assert batch_upper<=worker.METADATA_LIMITS['batch_fixed_json_bytes']
    assert request_upper<=worker.METADATA_LIMITS['request_file_bytes']
    assert prior['manifest_line_upper']<=worker.METADATA_LIMITS['manifest_line_bytes']
    assert prior['audit_line_upper']<=worker.METADATA_LIMITS['independent_audit_line_bytes']
    runtime={key:dict(value=value,json_bytes=len(worker.encode(value)))for key,value in dict(python=sys.version,platform=platform.platform(),zlib=zlib.ZLIB_VERSION).items()}
    assert all(v['json_bytes']<=worker.METADATA_LIMITS['runtime_string_json_bytes']for v in runtime.values())
    free=shutil.disk_usage('C:/').free
    wanted={phase:worker.resource_requirements(worker.ENGINEERING_ENVELOPE,phase=phase,remaining_batches=5241 if phase=='remaining'else None)for phase in ('initial','remaining','batch')}
    assert worker.filehash(worker.SOURCE)==source_hash
    assert reader.filehash(reader.SOURCE)==reader_hash
    assert worker.filehash(worker.RESOURCE_CONTRACT_PATH)==contract_hash
    assert worker.filehash(acceptance_path)==acceptance_ref['sha256']
    assert worker.filehash(reference['path'])==reference['sha256']
    return dict(schema='DOUBLE_C_STREAM_READONLY_RESOURCE_PREFLIGHT_V1',worker_sha256=source_hash,
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                reader_reference=reader.ref(reader.SOURCE,reader_hash),reader_output_directory=str(reader.OUTPUT),
                acceptance_reference=acceptance_ref,
                registration_census=dict(path=str(registration_path.resolve()),actual_file_authenticated=actual_registration,
                                         json_byte_count=len(registration_raw),sha256=hashlib.sha256(registration_raw).hexdigest(),
                                         document=witness,scope='ACTUAL_CURRENT_REGISTRATION'if actual_registration else'UNBOUND_LENGTH_WITNESS_ONLY_RERUN_AFTER_FINAL_BINDING'),
                contract_reference=worker.ref(worker.RESOURCE_CONTRACT_PATH,contract_hash),
                normal_bound_reference=reference,runtime=runtime,
                derived_fixed_batch_json_upper=batch_upper,derived_request_json_upper=request_upper,
                new_request_resource_fields_json_bytes=added_bytes,normal_data_budget=worker.normal_metadata_budget(),
                resource_requirements=wanted,observed_free_c_bytes=free,
                observed_capacity_pass=free>=max(v['disk_bytes']for v in wanted.values()),
                actual_namespace_created=False,evaluator_calls=0,inspector_calls=0,
                actual_pins={name:getattr(worker,name) for name in ('LIFECYCLE_SHA','STREAM_SHA','RESOURCE_PROOF_SHA','RESOURCE_CONTRACT_SHA','RESOURCE_ENVELOPE')},
                resource_claims=worker.RESOURCE_CLAIMS,execution_authorized=False)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--registration');args=parser.parse_args()
    print(json.dumps(run(args.registration),indent=2))
