"""Validate a monthly package; optionally publish a local scheduled release."""
import argparse
from copy import deepcopy
from contextlib import contextmanager
from backtest.current_quantity_v2_simulation_store import SimulationStore
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from backtest.current_quantity_v2_close_capture_simulation import _read
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.current_quantity_v2_monthly_origins import MonthlyOriginReader
from scripts.run_current_quantity_v2_simulation import preflight


@contextmanager
def publication_guard(config, expected_revision):
    """Hold SQLite's writer reservation through filesystem publication; no DB mutation."""
    store=SimulationStore(config['database_path'])
    with store._transaction() as connection:
        require(store._load(connection,config['simulation_id'])['revision']==expected_revision,
                'SIMULATION_CHANGED_DURING_BINDING')
        yield


def bind(*, daily_config, daily_sha256, monthly_path, monthly_sha256,
         session, monthly_blob_root, output, monthly_runtime_directory=None, expected_revision=None, publication_time_guard=None):
    original=Path(daily_config).resolve();destination=Path(output).resolve()
    require(original!=destination and not destination.exists(),'CREATE_ONLY_OUTPUT_EXISTS')
    config=json.loads(_read(original.parent,original.name,{original.name:daily_sha256}))
    root=Path(config['root']).resolve()
    # This clock selects the declared month only. No observation, acceptance or
    # price is generated and no actual timestamp is backfilled by this probe.
    route_clock=lambda:datetime.fromisoformat(session+'T10:00:00').replace(tzinfo=ZoneInfo('America/New_York'))
    published=MonthlyFileConfiguration(root=root,path=monthly_path,sha256_value=monthly_sha256,clock=route_clock)
    market=published.market_reader(None)
    compiled=compile_saved_training(market['source_package'],market['manifest_path'])
    require(compiled['status']=='READY_CONDITIONAL','MONTHLY_TRAINING_NOT_READY')
    candidate=deepcopy(config)
    candidate['monthly']=dict(path=monthly_path,sha256=monthly_sha256,review_mode='DERIVED_PAPER_BOUNDED')
    require(Path(monthly_blob_root).is_absolute(),'EXPLICIT_ABSOLUTE_RUNTIME_PATH_REQUIRED')
    candidate['monthly_blob_root']=str(Path(monthly_blob_root).resolve())
    raw=canonical(candidate);digest=sha256(raw).hexdigest()
    # Real preflight uses a disposable file; no rejected candidate is published.
    with TemporaryDirectory(prefix='monthly-runtime-preflight-') as temporary:
        path=Path(temporary)/'daily.json';path.write_bytes(raw)
        checked=preflight(config_path=path,config_sha256=digest,session=session)
        MonthlyOriginReader(monthly_blob_root=checked['monthly_blob_root'])({'state':checked['state']['chain']})
        revision=checked['summary']['revision']
        require(expected_revision is None or revision==expected_revision,'AUTO_REVIEW_ACCOUNT_CHANGED')
        require(checked['store'].read(config['simulation_id'])['revision']==revision,'SIMULATION_CHANGED_DURING_BINDING')
    # Recheck immutable inputs after validation, before create-only publication.
    _read(original.parent,original.name,{original.name:daily_sha256})
    published.market_reader(None)
    with publication_guard(config,revision):
        if publication_time_guard is not None: publication_time_guard()
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('xb') as stream:stream.write(raw)
        release=None
        if monthly_runtime_directory is not None:
            from scripts.monthly_runtime_routes import publish
            if publication_time_guard is not None: publication_time_guard()
            release=publish(directory=monthly_runtime_directory,session=session,base_path=original,base_hash=daily_sha256,
                            candidate_path=destination,candidate_hash=digest)
    return dict(status='VALIDATED_MONTHLY_RUNTIME_RELEASE_PUBLISHED' if release else 'VALIDATED_MONTHLY_RUNTIME_CANDIDATE_NOT_ACTIVATED',config_path=str(destination),
        config_sha256=digest,session=session,simulation_id=config['simulation_id'],validated_revision=revision,
        monthly_path=monthly_path,monthly_sha256=monthly_sha256,compiler_status=compiled['status'],
        routing_clock_basis='TARGET_SESSION_ROUTING_ONLY',account_writes=False,
        scheduler_activated=False,monthly_release=release,network_calls=0,search_calls=0)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('daily-config','daily-sha256','monthly-path','monthly-sha256','session','monthly-blob-root','output'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--monthly-runtime-directory')
    parser.add_argument('--expected-revision')
    try:result=bind(**vars(parser.parse_args(argv)))
    except Exception as error:
        reason=str(error) if type(error)is ValueError and str(error).replace('_','').isalnum() else type(error).__name__
        print(json.dumps(dict(status='BLOCKED',reason=reason,account_writes=False,scheduler_activated=False)));return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
