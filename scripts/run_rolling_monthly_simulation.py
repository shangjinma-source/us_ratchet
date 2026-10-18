"""Pinned rolling monthly dispatch; at most one due pipeline per invocation."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from data.current_quantity_v2_difference_plan import require, stamp
from scripts.coordinate_monthly_simulation import now, safe_reason, run as coordinate
from scripts.materialize_monthly_successor import run as materialize
from scripts.run_monthly_simulation_pipeline import run as pipeline


def run(*, config_path, config_sha256, execute=False, clock=now):
    raw = Path(config_path).read_bytes()
    require(sha256(raw).hexdigest() == config_sha256, 'ROLLING_CONFIG_CHANGED')
    config = json.loads(raw)
    require(set(config) == {'schema','root','first_coordinator','bootstrap','policy','rolling_output_directory','first_evidence_directory'}
            and config['schema'] == 'ROLLING_MONTHLY_SIMULATION_V1', 'ROLLING_CONFIG_FIELDS')
    root = Path(config['root']).resolve()

    def checked(binding):
        require(set(binding) == {'path','sha256'}, 'ROLLING_SOURCE_BINDING_REQUIRED')
        path = Path(binding['path']); path = path if path.is_absolute() else root/path
        require(path.resolve().is_relative_to(root) and not path.is_symlink() and path.is_file()
                and path.stat().st_size <= 32*1024*1024, 'ROLLING_SOURCE_UNAVAILABLE')
        raw = path.read_bytes()
        require(sha256(raw).hexdigest() == binding['sha256'], 'ROLLING_SOURCE_CHANGED')
        return path.resolve(), json.loads(raw)

    bootstrap_path, _ = checked(config['bootstrap']); policy_path, _ = checked(config['policy'])
    directory = Path(config['rolling_output_directory'])
    require(not directory.is_absolute() and '..' not in directory.parts and directory.as_posix() not in ('','.')
            and (root/directory).resolve().is_relative_to(root), 'ROLLING_OUTPUT_INVALID')
    first_evidence = Path(config['first_evidence_directory'])
    require(not first_evidence.is_absolute() and '..' not in first_evidence.parts
            and first_evidence.as_posix() not in ('','.') and (root/first_evidence).resolve().is_relative_to(root),
            'ROLLING_FIRST_EVIDENCE_INVALID')
    selected = dict(config['first_coordinator']); visited = set(); completed = []
    observed = stamp(clock())
    for _ in range(24):
        coordinator_path, current = checked(selected)
        require(Path(current['root']).resolve() == root, 'ROLLING_ROOT_MISMATCH')
        month = current['session'][:7]
        require(month not in visited, 'ROLLING_CYCLE'); visited.add(month)
        require(not completed or month > completed[-1], 'ROLLING_MONTH_NOT_ADVANCING')
        _, settings = checked(dict(path=current['settings_path'],sha256=current['settings_sha256']))
        _, boundary = checked(dict(path=settings['calendar_path'],sha256=settings['fixed_source_hashes'][settings['calendar_path']]))
        require(boundary['target_month'] == month and boundary['active_date'] == current['session'], 'ROLLING_BOUNDARY_MISMATCH')
        stage = root/current['stage_directory']
        require(stage.resolve().is_relative_to(root), 'ROLLING_STAGE_OUTSIDE_ROOT')
        next_directory = (directory/'plans'/('after-'+month)).as_posix()
        if (stage/'bind.complete.json').exists():
            # Fully validate receipts and immutable output closure; never recapture a completed month.
            successor = materialize(previous_coordinator=coordinator_path, previous_sha256=selected['sha256'],
                output_directory=next_directory, execute=execute, clock=clock)
            completed.append(month)
            if successor['status'] == 'SUCCESSOR_COORDINATOR_PREFLIGHT':
                return dict(status='NEXT_PLAN_MATERIALIZATION_REQUIRED', completed_months=completed,
                            successor=successor, account_writes=False, pipeline_calls=0)
            registry_path = root/next_directory/'registry.json'
            registry = json.loads(registry_path.read_bytes())
            require(registry == dict(schema='LOCAL_MONTHLY_COORDINATOR_PLAN_V1',
                coordinator_path=successor['coordinator_path'], coordinator_sha256=successor['coordinator_sha256'],
                target_month=successor['target_month'], session=successor['session'],
                previous_coordinator_sha256=selected['sha256']), 'ROLLING_REGISTRY_MISMATCH')
            selected = dict(path=successor['coordinator_path'],sha256=successor['coordinator_sha256'])
            continue
        preparation = coordinate(config_path=coordinator_path, config_sha256=selected['sha256'], clock=clock)
        require(preparation['status'] == 'PREFLIGHT_ONLY', 'ROLLING_PREFLIGHT_FAILED')
        close_at = stamp(boundary['decision_close_at']); active_at = stamp(boundary['active_open_at'])
        require(close_at < active_at, 'ROLLING_BOUNDARY_INVALID')
        common = dict(target_month=month, coordinator_path=str(coordinator_path),
                      coordinator_sha256=selected['sha256'], completed_months=completed,
                      decision_close_at=close_at.isoformat(), deadline=active_at.isoformat(),
                      observed_at=observed.isoformat(), account_writes=False)
        if observed < close_at or not preparation['ready_after_close']:
            return dict(common, status='WAITING_SESSION_CLOSE', pipeline_calls=0)
        if observed >= active_at:
            return dict(common, status='RECOVERY_REQUIRED', reason='MISSED_MONTHLY_PREPARATION_WINDOW', pipeline_calls=0)
        if not execute: return dict(common, status='DUE_READ_ONLY', pipeline_calls=0)
        # Check the real clock again immediately before dispatch, without substituting a historical clock.
        require(close_at <= stamp(clock()) < active_at, 'ROLLING_WINDOW_ELAPSED')
        def bounded_clock():
            current_time = clock()
            require(close_at <= stamp(current_time) < active_at, 'ROLLING_WINDOW_ELAPSED')
            return current_time
        result = pipeline(coordinator_config=coordinator_path, coordinator_sha256=selected['sha256'],
            bootstrap_config=bootstrap_path, bootstrap_sha256=config['bootstrap']['sha256'],
            policy_path=policy_path.relative_to(root).as_posix(), policy_sha256=config['policy']['sha256'],
            output_directory=first_evidence.as_posix() if not completed else (directory/'evidence'/month).as_posix(),
            execute=True, clock=bounded_clock)
        if result['status'] != 'MONTHLY_RUNTIME_PUBLISHED':
            return dict(common, status=result['status'], result=result, pipeline_calls=1)
        try:
            successor = materialize(previous_coordinator=coordinator_path, previous_sha256=selected['sha256'],
                output_directory=next_directory, execute=True, clock=clock)
        except Exception as error:
            return dict(common, status='MONTHLY_COMPLETE_NEXT_PLAN_BLOCKED', result=result,
                        reason=safe_reason(error), pipeline_calls=1)
        return dict(common, status='MONTHLY_COMPLETE_NEXT_PLAN_READY', result=result,
                    successor=successor, pipeline_calls=1)
    raise ValueError('ROLLING_CHAIN_DEPTH_LIMIT')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path', required=True); parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    try: result = run(**vars(parser.parse_args(argv)))
    except Exception as error: result = dict(status='BLOCKED',reason=safe_reason(error),account_writes=False)
    print(json.dumps(result)); return 2 if result['status'] in ('BLOCKED','RECOVERY_REQUIRED','MONTHLY_COMPLETE_NEXT_PLAN_BLOCKED') else 0


if __name__ == '__main__':
    raise SystemExit(main())
