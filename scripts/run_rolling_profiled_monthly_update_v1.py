"""Bounded profiled successor chain, retaining all immutable monthly evidence."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import os
from core.strategy_account_ledger import canonical, require
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES
from data.strategy_continuous32_target_decision import PROFILE_ID
from scripts.prepare_real_monthly_release import _read, _safe
from scripts.run_profiled_monthly_update_v1 import run as scheduled_run, SOURCES as SCHEDULE_SOURCES
from scripts.materialize_profiled_monthly_successor_v1 import run as successor
from scripts.build_real_monthly_release_entry import build

SOURCES = SCHEDULE_SOURCES | {'scripts/run_rolling_profiled_monthly_update_v1.py',
    'scripts/materialize_profiled_monthly_successor_v1.py', 'scripts/build_monthly_successor_plan.py'}


def run(*, root, config_path, config_sha256, execute=False, clock=None):
    root=Path(root).absolute();clock=clock or (lambda:datetime.now(timezone.utc))
    config=_read(root,config_path,config_sha256)
    require(set(config)=={'schema','first_schedule','output_directory','source_pins'} and
            config['schema']=='ROLLING_PROFILED_MONTHLY_UPDATE_V1','PROFILE_ROLLING_FIELDS')
    require(SOURCES<=set(config['source_pins']),'PROFILE_ROLLING_SOURCE_SCOPE')
    gate=BoundedSourceGateV1(root=root,source_pins=config['source_pins'],
        configuration_pins={config_path:config_sha256})
    gate(); reference=config['first_schedule'];visited=[]
    destination=_safe(root,config['output_directory'])
    def load(ref):return _read(root,ref['path'],ref['sha256'])
    def save(path,value):
        raw=canonical(value)
        if path.exists():require(path.read_bytes()==raw,'PROFILE_ROLLING_OUTPUT_CHANGED')
        elif execute:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return dict(path=path.relative_to(root).as_posix(),sha256=sha256(raw).hexdigest())
    for _ in range(24):
        gate();child=load(reference);source=load(child['source_schedule'])
        require(all(config['source_pins'].get(p)==h for p,h in child['source_pins'].items()),'PROFILE_ROLLING_CHILD_PINS')
        preparation=load(child['preparation'])
        activation=ProfiledMonthlyReleaseActivation(root=root,initial_snapshot=preparation['initial_snapshot'],
            legacy_anchor=preparation['legacy_anchor'],validate_code=gate,clock=clock)
        targets=StrategyMonthlyTargetStore(root/'data/strategy_account/monthly_targets.sqlite3')
        snapshot_provider=upgrade_handoff_snapshot_provider(root=root,package_path=child['upgrade']['path'],
            package_sha256=child['upgrade']['sha256'],base_provider=activation.snapshot,
            target_provider=targets.current,validate_code=gate)
        complete=_safe(root,source['market_output_directory']+'/complete.json')
        def adopted():
            if not complete.is_file():return None
            digest=sha256(complete.read_bytes()).hexdigest()
            entry=build(root=root,complete_path=complete.relative_to(root).as_posix(),complete_sha256=digest,
                descriptor_path=source['descriptor_path'],descriptor_sha256=source['descriptor_sha256'])
            for name in RUNTIME_PATHS|PROFILE_ADMISSION_SOURCES:entry['runtime_pins'][name]=child['source_pins'][name]
            snap=snapshot_provider();registry=load(dict(path=snap['registry_path'],sha256=snap['registry_sha256']))
            if registry.get('schema')!='PROFILED_MONTHLY_RELEASES_V1':return None
            profiles=registry['profiles'];registry=load(registry['original_registry'])
            matches=[r for r in registry['entries'] if r['target_month']==entry['target_month']]
            if not matches:return None
            require(matches==[entry] and dict(target_month=entry['target_month'],selector_profile=PROFILE_ID) in profiles,
                    'PROFILE_ROLLING_ADOPTED_MISMATCH')
            require(snap['revision']>0 and snapshot_provider()==snap,'PROFILE_ROLLING_SNAPSHOT_CHANGED')
            return entry['target_month'],digest
        evidence=adopted()
        if evidence is None:
            result=scheduled_run(root=root,config_path=reference['path'],config_sha256=reference['sha256'],execute=execute,clock=clock)
            if result['status']!='PROFILED_MONTHLY_DATA_ADOPTED':return dict(result,completed_months=visited)
            evidence=adopted();require(evidence is not None,'PROFILE_ROLLING_ADOPTION_MISSING')
        month,digest=evidence
        require(not visited or month>visited[-1],'PROFILE_ROLLING_MONTH_ORDER');visited.append(month)
        plan=(destination/month/'plan').relative_to(root).as_posix()
        generated=successor(root=root,complete_path=complete.relative_to(root).as_posix(),complete_sha256=digest,
            descriptor_path=source['descriptor_path'],descriptor_sha256=source['descriptor_sha256'],
            output_directory=plan,snapshot_provider=snapshot_provider,validate_code=gate,
            runtime_pins=child['source_pins'],execute=execute,clock=clock)
        directory=destination/month
        source_next=dict(source,coordinator_config=generated['coordinator_path'],coordinator_sha256=generated['coordinator_sha256'],
            market_output_directory=(directory/'market').relative_to(root).as_posix(),
            update_output_directory=(directory/'unused-legacy-update').relative_to(root).as_posix(),
            run_directory=(directory/'source-runs').relative_to(root).as_posix())
        source_ref=save(directory/'source-schedule.json',source_next)
        child_next=dict(child,source_schedule=source_ref,output_directory=(directory/'profile-update').relative_to(root).as_posix())
        reference=save(directory/'profile-schedule.json',child_next);gate()
        if not execute:return dict(status='NEXT_MONTH_READY',completed_months=visited,next_schedule=reference,account_writes=False)
    raise ValueError('PROFILE_ROLLING_DEPTH_LIMIT')
