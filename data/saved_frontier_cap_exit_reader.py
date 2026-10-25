"""Default-off isolated proposal risk projection, preserving all risk tables.

This adapter never mounts a production policy. Source consistency is checked by
the independent full-window adapter; it is not a claim of vendor authenticity.
Only an explicit existing research directory beneath this repository's tmp is
accepted. The original monthly target and account are never modified.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from core.strategy_account_ledger import canonical, require
from data.monthly_peak_exit_history import monthly_exit_observations
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.saved_frontier_daily_evidence import verify_saved_frontier_daily_evidence
from data.saved_frontier_policy_archive import _research_root
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.strategy_daily_session_capture import reject_links, stamp


POLICY_ID = 'SAVED_FRONTIER_CAP50_EXIT20_ISOLATED_V1'
TABLES = {'risk_state', 'risk_prices', 'risk_domain_evidence'}
MAX_DATABASE_BYTES = 32 * 1024 * 1024


def _digest(raw):
    return sha256(raw).hexdigest()


def _database(path):
    path = Path(path).absolute()
    reject_links(path)
    require(path.is_file() and path.stat().st_nlink == 1
            and 0 < path.stat().st_size <= MAX_DATABASE_BYTES, 'FRONTIER_RISK_FILE_REQUIRED')
    for suffix in ('-wal', '-shm', '-journal'):
        require(not Path(str(path) + suffix).exists(), 'FRONTIER_RISK_QUIESCENT_COPY_REQUIRED')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        require(connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'FRONTIER_RISK_DATABASE_INTEGRITY')
        objects = connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        require({name for name, kind in objects if kind == 'table'} == TABLES
                and all(kind == 'table' for name, kind in objects), 'FRONTIER_RISK_ALL_THREE_TABLES_REQUIRED')
        require(all(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] > 0
                    for table in TABLES), 'FRONTIER_RISK_HISTORY_REQUIRED')
    return path


def clone_monthly_risk_store(*, research_root, source_path, source_sha256, clone_name):
    """Copy a quiescent, explicitly hashed risk database without resetting it."""
    root = _research_root(research_root)
    source = _database(source_path)
    temporary_root = Path(__file__).resolve().parents[1] / 'tmp'
    require(source.resolve().is_relative_to(temporary_root.resolve()), 'FRONTIER_RISK_SOURCE_ISOLATION_REQUIRED')
    require(type(clone_name) is str and re.fullmatch(r'[A-Za-z0-9_-]+\.sqlite3', clone_name),
            'FRONTIER_RISK_CLONE_NAME')
    destination = root / clone_name
    reject_links(destination)
    require(destination != source and not destination.exists(), 'FRONTIER_RISK_CLONE_CREATE_ONLY')
    sidecar = Path(str(destination) + '.clone.json')
    require(not sidecar.exists(), 'FRONTIER_RISK_CLONE_CREATE_ONLY')
    raw = source.read_bytes()
    require(_digest(raw) == source_sha256, 'FRONTIER_RISK_SOURCE_HASH')
    proof = dict(schema='SAVED_FRONTIER_RISK_CLONE_V1', source_path=str(source),
                 source_sha256=source_sha256, path=str(destination), tables=sorted(TABLES))
    with destination.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(_digest(source.read_bytes()) == source_sha256 and destination.read_bytes() == raw,
            'FRONTIER_RISK_SOURCE_CHANGED_DURING_COPY')
    _database(destination)
    with sidecar.open('xb') as stream:
        stream.write(canonical(proof))
        stream.flush()
        os.fsync(stream.fileno())
    return dict(proof, source_mutated=False)


def project_saved_frontier_cap_exit(*, research_root, risk_path, target_id, state,
        review_bytes, trusted_review_sha256, files, now,
        authorized_monthly_reset=None, enabled=False):
    """Verify sources, advance only the inherited tmp clone, archive projection.

    A stale review is rejected after a risk-state change. Repeated previews can
    clone the same unchanged seed; no reset or same-month re-entry is inferred.
    If archive writing fails after risk advance, no signal is returned; retain
    that research clone for diagnosis and rebind a reviewed snapshot explicitly.
    """
    require(type(enabled) is bool, 'FRONTIER_ENABLED_BOOLEAN')
    if not enabled:
        return dict(status='SAVED_FRONTIER_RISK_DISABLED', production_admitted=False)
    root = _research_root(research_root)
    path = _database(risk_path)
    require(path.resolve().is_relative_to(root) and path.resolve() != root,
            'FRONTIER_RISK_CLONE_SCOPE')
    sidecar = Path(str(path) + '.clone.json')
    reject_links(sidecar)
    require(sidecar.is_file() and sidecar.stat().st_size <= 4096, 'FRONTIER_RISK_CLONE_PROOF_REQUIRED')
    clone = json.loads(sidecar.read_bytes())
    require(clone['schema'] == 'SAVED_FRONTIER_RISK_CLONE_V1' and clone['path'] == str(path)
            and clone['source_path'] != str(path) and clone['tables'] == sorted(TABLES), 'FRONTIER_RISK_CLONE_PROOF')
    snapshot = deepcopy(state)
    source_files = files.copy()
    store = MonthlyPeakExitStore(path)
    previous = store.read(snapshot['account_id'])
    require(previous is not None and previous.get('target_month'), 'FRONTIER_EXISTING_RISK_STATE_REQUIRED')
    before_bytes = path.read_bytes()
    admitted = verify_saved_frontier_daily_evidence(research_root=root, target_id=target_id,
        state=snapshot, risk_state=previous, review_bytes=review_bytes,
        trusted_review_sha256=trusted_review_sha256, files=source_files, now=now, enabled=True)
    require(admitted['status'] == 'SAVED_FRONTIER_DAILY_EVIDENCE_READY', 'FRONTIER_SOURCE_NOT_READY')
    inputs = deepcopy(admitted['inputs'])
    baseline = deepcopy(inputs['base_target']['quantities'])
    month = admitted['target_month']
    epoch = inputs['base_target']['monthly_decision_date']
    if month == previous['target_month']:
        require(epoch == previous['decision_date'] and authorized_monthly_reset is None,
                'FRONTIER_SAME_MONTH_RESET_FORBIDDEN')
    else:
        require(month > previous['target_month'] and authorized_monthly_reset == epoch,
                'FRONTIER_NEW_MONTH_AUTHORIZATION_REQUIRED')
    require(inputs['base_target']['origin_reference'] == admitted['proposal_id']
            and set(baseline) == set(admitted['required_security_ids'])
            and all(q == admitted['proposed_target_quantities'].get(sid, 0) for sid, q in baseline.items()),
            'FRONTIER_PROJECTION_BASE_BINDING')
    observations = monthly_exit_observations(**inputs)
    require(path.read_bytes() == before_bytes and store.read(snapshot['account_id']) == previous,
            'FRONTIER_RISK_CHANGED_DURING_VERIFICATION')
    projection = store.advance(account_id=snapshot['account_id'],
        expected_previous_session=previous['session_date'], observations=observations,
        baseline_targets=baseline, authorized_monthly_reset=authorized_monthly_reset,
        target_month=month)
    require(state == snapshot, 'FRONTIER_ACCOUNT_CHANGED_DURING_PROJECTION')
    if month == previous['target_month']:
        require(set(previous['exited']) <= set(projection['state']['exited'])
                and all(projection['effective_target_quantities'][sid] == 0 for sid in previous['exited']),
                'FRONTIER_PRIOR_EXIT_LOST')
    # Ledger retains fully sold positions as zero keys. They have no exposure
    # and need no new price history, but the existing daily gate preserves their
    # display domain. This never fills a missing positive holding or risk name.
    zero_balance_ids = sorted(sid for sid, quantity in snapshot['shares'].items()
                              if quantity == 0 and sid not in baseline)
    signal_baseline = dict(baseline, **{sid:0 for sid in zero_balance_ids})
    effective = dict(projection['effective_target_quantities'], **{sid:0 for sid in zero_balance_ids})
    review = json.loads(review_bytes)
    proof = dict(schema='SAVED_FRONTIER_CAP_EXIT_PROJECTION_V1', policy_id=POLICY_ID,
        source_target_id=target_id, proposal_id=admitted['proposal_id'], account_id=snapshot['account_id'],
        account_revision=snapshot['revision'], source_content_id=admitted['content_id'],
        risk_before=previous, risk_after=projection['state'], baseline_targets=signal_baseline,
        risk_baseline_targets=baseline, zero_balance_security_ids=zero_balance_ids,
        effective_target_quantities=effective,
        projection=projection, risk_clone=clone, source_authenticity_verified=False,
        production_admitted=False, account_mutated=False)
    additions = {'frontier-risk/review.json': review_bytes,
                 'frontier-risk/source-admission.json': canonical(admitted),
                 'frontier-risk/projection.json': canonical(proof)}
    require(not set(additions) & set(source_files), 'FRONTIER_ARCHIVE_SOURCE_COLLISION')
    source_files.update(additions)
    receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1', policy_id=POLICY_ID,
        target_id=target_id, proposal_id=admitted['proposal_id'], account_id=snapshot['account_id'],
        account_revision=snapshot['revision'], target_month=month,
        cap_exit_projection_path='frontier-risk/projection.json',
        source_sha256={name:_digest(raw) for name,raw in source_files.items()},
        valid_from=admitted['valid_from'], valid_until=admitted['valid_until'],
        source_authenticity_verified=False, production_admitted=False)
    archive_root = root / 'risk-projections'
    reject_links(archive_root)
    # The old archive helper rejects symlinks; also reject Windows junctions at
    # every existing child before passing it a create-only archive destination.
    receipt_bytes = canonical(receipt)
    archive_folder = archive_root / _digest(receipt_bytes)
    for child in ['receipt.json', 'manifest.json', 'complete.json'] + [
            'sources/' + digest + '.bin' for digest in receipt['source_sha256'].values()]:
        reject_links(archive_folder / child)
    evidence_archive = archive_rebound_evidence(root=archive_root, receipt_bytes=receipt_bytes, files=source_files)
    signal = dict(account_id=snapshot['account_id'], account_revision=snapshot['revision'],
        target_id=target_id, source_target_id=target_id, proposal_id=admitted['proposal_id'],
        policy_id=POLICY_ID, effective_target_quantities=deepcopy(effective),
        evidence_id=evidence_archive['receipt_sha256'], evidence_archive=evidence_archive,
        observed_at=inputs['observed_at'], available_at=review['reviewed_at'],
        valid_from=admitted['valid_from'], valid_until=admitted['valid_until'])
    require(stamp(signal['observed_at']) <= stamp(signal['available_at']) <= stamp(now)
            and stamp(signal['valid_from']) <= stamp(now) < stamp(signal['valid_until']), 'FRONTIER_SIGNAL_TIME')
    return dict(status='DAILY_SIGNAL_READY', proposal_id=admitted['proposal_id'],
        source_target_id=target_id, projection=projection, baseline_targets=signal_baseline,
        risk_baseline_targets=baseline, zero_balance_security_ids=zero_balance_ids,
        source_admission=admitted, signal=signal, evidence_archive=evidence_archive,
        production_admitted=False, source_authenticity_verified=False, account_mutated=False,
        isolated_risk_mutated=True, orders_created=False, new_searches=0)
