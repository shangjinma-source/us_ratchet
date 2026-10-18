"""Explicit, durable one-shot execution of a two-period strategic target probe."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_corrected_explicit_path_research as core

SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def run(*, path_path, path_sha256, calendar_path, calendar_sha256, output, execute=False):
    if type(execute) is not bool:
        raise ValueError('Explicit boolean execution switch required')
    destination = Path(output).resolve()
    started_path = Path(str(destination) + '.started.json')
    failure_path = Path(str(destination) + '.failure.json')
    if any(path.exists() for path in (destination, started_path, failure_path)):
        raise FileExistsError('Existing target or attempt; reconcile without automatic refitting')
    path_reference = dict(path=str(Path(path_path).resolve()), sha256=path_sha256)
    calendar_reference = dict(path=str(Path(calendar_path).resolve()), sha256=calendar_sha256)
    sources = {str(SOURCE): LOADED, str(core.SOURCE): core.LOADED[str(core.SOURCE)]}
    core.adapter.archive.merge(sources, {
        path_reference['path']: path_sha256,
        calendar_reference['path']: calendar_sha256,
    })

    def verify():
        core.adapter.archive.strict(sources)

    verify()
    prepared = core.prepare_explicit_path(
        path_path=path_reference['path'], path_sha256=path_sha256,
        calendar_path=calendar_reference['path'], calendar_sha256=calendar_sha256)
    verify()
    if not execute:
        return dict(schema='EXPLICIT_STRATEGIC_TARGET_PATH_PREFLIGHT_V1',
                    path=path_reference, calendar=calendar_reference, prepare_completed=True,
                    fit_performed=False, execution_performed=False, promotion_allowed=False)
    attempt = dict(schema='EXPLICIT_STRATEGIC_TARGET_PATH_ATTEMPT_V1',
                   path=path_reference, calendar=calendar_reference, output=str(destination),
                   runner_source_hashes=sources, status='STARTED_NOT_COMPLETED')
    started = core.snapshot.single.publish(started_path, attempt)

    def verify_attempt():
        verify()
        core.snapshot.read(started['path'], started['sha256'])

    verify_attempt()
    try:
        result = core.build_path_targets(prepared)
    except Exception as error:
        # The durable started marker also covers KeyboardInterrupt/SystemExit,
        # which intentionally bypass this ordinary failure-report branch.
        verify_attempt()
        failure = dict(schema='EXPLICIT_STRATEGIC_TARGET_PATH_FAILURE_V1',
                       started_attempt=started, path=path_reference, calendar=calendar_reference,
                       error_type=type(error).__name__, error=str(error),
                       failure_audit=getattr(error, 'audit', None),
                       partial_schedule_returned=False, automatic_retry_allowed=False,
                       numerical_failure_is_economic_infeasibility=False,
                       execution_performed=False, promotion_allowed=False)
        core.snapshot.single.publish(failure_path, failure)
        verify_attempt()
        raise
    verify_attempt()
    def verify_result():
        if (result.get('schema') != 'CORRECTED_EXPLICIT_STRATEGIC_TARGET_PATH_V1'
                or result.get('first_seed_imported_without_refit') is not True
                or type(result.get('new_fit_count')) is not int or result['new_fit_count'] != 1
                or len(result['schedule']) != 2):
            raise ValueError('Complete two-period result with one new fit required')
        checked = core.adapter.archive.verify_expected_sources(
            result['historical_expected_source_hashes'], core.adapter.archive.load_contract())
        if checked != result['archive_resolution']:
            raise ValueError('Final path source partition changed')
        core.adapter.audit.original.verify_gaps(result['historical_loader_gap_observations'])

    verify_result()
    value = dict(schema='EXPLICIT_STRATEGIC_TARGET_PATH_EXECUTION_V1',
                 path=path_reference, calendar=calendar_reference, started_attempt=started,
                 runner_source_hashes=sources, result=result,
                 target_schedule_built=True, whole_lot_execution_performed=False,
                 independently_selected_winner=False, point_in_time_verified=False,
                 promotion_allowed=False)
    saved = core.snapshot.single.publish(destination, value)
    verify_attempt()
    verify_result()
    return dict(saved, first_seed_imported_without_refit=result['first_seed_imported_without_refit'],
                new_fit_count=result['new_fit_count'], target_schedule_built=True,
                whole_lot_execution_performed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('path-path', 'path-sha256', 'calendar-path', 'calendar-sha256', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(run(**vars(parser.parse_args()))))
