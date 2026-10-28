"""Prepare an isolated activation package; never activate the production store."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from core.strategy_account_store import StrategyAccountStore
from data.monthly_peak_exit_reentry_store_v1 import MonthlyPeakExitReentryStore


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_risk(path, account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        row = connection.execute('SELECT state FROM risk_state WHERE account_id=?', (account_id,)).fetchone()
        require(row is not None, 'ACTIVATION_RISK_STATE_REQUIRED')
        return json.loads(row[0])


def prepare(*, output_directory, risk_path, account_store, configuration_path,
            expected_account_revision, expected_risk_sha256, expected_configuration_sha256,
            clock=lambda: datetime.now(timezone.utc)):
    output = Path(output_directory).resolve()
    risk_path, configuration_path = Path(risk_path).resolve(), Path(configuration_path).resolve()
    require(not output.exists(), 'ACTIVATION_OUTPUT_ALREADY_EXISTS')
    require(risk_path != Path(account_store.path).resolve(), 'ACTIVATION_ACCOUNT_IS_NOT_RISK')
    account = account_store.read()
    require(account['revision'] == expected_account_revision, 'ACTIVATION_ACCOUNT_CHANGED')
    configuration = configuration_path.read_bytes()
    require(sha256(configuration).hexdigest() == expected_configuration_sha256, 'ACTIVATION_CONFIGURATION_CHANGED')
    risk = read_risk(risk_path, account['account_id'])
    require(digest(risk) == expected_risk_sha256, 'ACTIVATION_RISK_CHANGED')
    output.mkdir(parents=True, exist_ok=False)
    try:
        snapshot = output / 'isolated_risk.sqlite3'
        with closing(sqlite3.connect(risk_path.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination)
        require(digest(read_risk(snapshot, account['account_id'])) == expected_risk_sha256,
                'ACTIVATION_SNAPSHOT_CHANGED')
        initial_snapshot_sha256 = sha256(snapshot.read_bytes()).hexdigest()
        observed = clock()
        require(observed.tzinfo is not None and observed.utcoffset() is not None, 'ACTIVATION_AWARE_CLOCK_REQUIRED')
        activation_at = observed.astimezone(timezone.utc).isoformat()
        binding = dict(account_id=account['account_id'], account_revision=expected_account_revision,
                       original_risk_sha256=expected_risk_sha256,
                       source_configuration_sha256=expected_configuration_sha256,
                       activation_at=activation_at,
                       activation_session=observed.astimezone(ZoneInfo('America/New_York')).date().isoformat())
        reference = MonthlyPeakExitReentryStore(snapshot).activate_reference(
            account_id=account['account_id'], activation_id=digest(binding),
            activation_at=activation_at, activation_session=binding['activation_session'],
            account_revision=expected_account_revision,
            source_configuration_sha256=expected_configuration_sha256)
        require(account_store.read()['revision'] == expected_account_revision, 'ACTIVATION_ACCOUNT_CHANGED')
        require(digest(read_risk(risk_path, account['account_id'])) == expected_risk_sha256, 'ACTIVATION_RISK_CHANGED')
        require(configuration_path.read_bytes() == configuration, 'ACTIVATION_CONFIGURATION_CHANGED')
        (output / 'base_configuration.json').write_bytes(configuration)
        result = dict(schema='ISOLATED_REENTRY_ACTIVATION_PACKAGE_V1', status='PREPARED_NOT_PRODUCTION_ACTIVATED',
                      binding=binding, activation_id=digest(binding), reference=reference,
                      source_risk_path=str(risk_path), source_configuration_path=str(configuration_path),
                      initial_snapshot_sha256=initial_snapshot_sha256,
                      isolated_database_sha256=sha256(snapshot.read_bytes()).hexdigest(),
                      production_activated=False, account_mutated=False,
                      limitations=['Preparation timestamp is not authority for later production activation.',
                                   'Recheck all authoritative versions and choose a new actual activation time at deployment.',
                                   'Independent source reads are not an atomic cross-database transaction.'])
        (output / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result
    except Exception as error:
        (output / 'FAILED.json').write_text(json.dumps(dict(status='FAILED_NOT_ACTIVATED', reason=str(error))), encoding='utf-8')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('output-directory', 'risk-path', 'account-path', 'configuration-path',
                     'expected-account-revision', 'expected-risk-sha256', 'expected-configuration-sha256'):
        parser.add_argument('--' + argument, required=True)
    options = vars(parser.parse_args())
    options['account_store'] = StrategyAccountStore(options.pop('account_path'))
    print(json.dumps({'status': prepare(**options)['status']}))


if __name__ == '__main__':
    main()
