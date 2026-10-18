"""After-close monthly pipeline; no orders or simulation-account initialization."""
import argparse
import json

from scripts.coordinate_monthly_simulation import run as coordinate, now, safe_reason
from scripts.collect_monthly_automatic_review_evidence import collect


def run(*, coordinator_config, coordinator_sha256, bootstrap_config, bootstrap_sha256,
        policy_path, policy_sha256, output_directory, execute=False, clock=now):
    coordination = dict(config_path=coordinator_config, config_sha256=coordinator_sha256,
                        clock=clock)
    collection = dict(coordinator_config=coordinator_config, coordinator_sha256=coordinator_sha256,
                      bootstrap_config=bootstrap_config, bootstrap_sha256=bootstrap_sha256,
                      policy_path=policy_path, policy_sha256=policy_sha256,
                      output_directory=output_directory, clock=clock)
    plan = coordinate(**coordination)
    evidence = collect(**collection)
    if not execute:
        return dict(status='PREFLIGHT_ONLY', preparation=plan, collection=evidence,
                    account_writes=False, http_calls=0, search_calls=0)
    # An unclosed session or missing account must not trigger training capture.
    if evidence['status'] != 'PREFLIGHT_ONLY':
        return dict(evidence, phase='COLLECTION_PREFLIGHT')
    prepared = coordinate(**coordination, execute=True)
    if prepared['status'] != 'WAITING_REVIEW':
        return dict(prepared, phase='TRAINING_PREPARATION')
    evidence = collect(**collection, execute=True)
    if evidence['status'] != 'EVIDENCE_READY':
        return dict(evidence, phase='EVIDENCE_COLLECTION')
    published = coordinate(**coordination, execute=True,
                           auto_review_inputs=evidence['inputs_path'],
                           auto_review_inputs_sha256=evidence['inputs_sha256'])
    return dict(published, phase='MONTHLY_PUBLICATION')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('coordinator-config', 'coordinator-sha256', 'bootstrap-config',
                  'bootstrap-sha256', 'policy-path', 'policy-sha256', 'output-directory'):
        parser.add_argument('--'+field, required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        result = run(**vars(parser.parse_args(argv)))
    except Exception as error:
        result = dict(status='BLOCKED', reason=safe_reason(error), account_writes=False,
                      automatic_retry=False)
    print(json.dumps(result))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
