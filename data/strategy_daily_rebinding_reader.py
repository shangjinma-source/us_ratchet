"""Server-only composition: reviewed parent -> same-session rebind -> verifier.

No source fetch, approval, receipt promotion or account mutation. In particular a
parent with release_sha256=None stays unbound and cannot be used with a released
policy until a separately reviewed receipt explicitly binds that policy.
"""
from hashlib import sha256

from core.strategy_account_ledger import canonical
from core.strategy_account_difference import require
from data.strategy_daily_evidence_adapter import SavedDailyEvidenceAdapter
from data.strategy_daily_evidence_rebind import SameSessionDailyEvidenceProducer
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle
from data.strategy_daily_rebound_archive import archive_rebound_evidence


class RebindingDailyEvidenceReader:
    """Callable implementing the live adapter's {status, signal} contract."""
    def __init__(self, *, root, parent_receipt_path, trusted_parent_sha256,
                 source_paths, release_path=None, trusted_release_sha256=None,
                 calendar_path=None, archive_root=None):
        self.reader = SavedDailyEvidenceAdapter(root=root)
        self.producer = SameSessionDailyEvidenceProducer(
            root=root, parent_receipt_path=parent_receipt_path,
            trusted_parent_sha256=trusted_parent_sha256, source_paths=source_paths)
        self.release_path = release_path
        self.release_sha = trusted_release_sha256
        self.calendar_path = calendar_path
        self.archive_root = archive_root

    def __call__(self, state, target, now):
        if self.release_path is None or self.release_sha is None:
            return dict(status='WAIT_POLICY_RELEASE', signal=None,
                        reason='APPROVED_SERVER_RELEASE_NOT_CONFIGURED')
        rebound = self.producer.prepare(state, target, now)
        if rebound['receipt'] is None:
            reason = rebound['status']
            mapping = dict(WAIT_NEW_SESSION_EVIDENCE='WAIT_FRESH_SIGNAL',
                           WAIT_MONTHLY_TARGET='WAIT_MONTHLY_TARGET',
                           WAIT_NEW_SECURITY_EVIDENCE='WAIT_SIGNAL',
                           WAIT_TARGET_HISTORY_ALIGNMENT='WAIT_SIGNAL')
            require(reason in mapping, 'UNRECOGNIZED_REBIND_WAIT')
            return dict(status=mapping[reason], signal=None, reason=reason)
        receipt = rebound['receipt']
        require(receipt.get('release_sha256') == self.release_sha,
                'REVIEWED_PARENT_POLICY_BINDING_REQUIRED')
        # The new receipt is generated only by the verified server-side rebind;
        # its digest is not an independently supplied browser assertion.
        receipt_bytes = canonical(receipt)
        result = verify_daily_signal_bundle(
            state=state, target=target, now=now.isoformat(),
            release_bytes=self.reader._read(self.release_path),
            trusted_release_sha256=self.release_sha,
            receipt_bytes=receipt_bytes,
            trusted_receipt_sha256=sha256(receipt_bytes).hexdigest(),
            files=rebound['files'], calendar_bytes=self.reader._read(self.calendar_path))
        archive = None
        if result['status'] == 'DAILY_SIGNAL_READY' and self.archive_root is not None:
            # Failure propagates before any signal reaches the execution caller.
            archive = archive_rebound_evidence(root=self.archive_root,
                receipt_bytes=receipt_bytes, files=rebound['files'])
            result['signal']['evidence_archive'] = archive
        return dict(result, reason=result['status'],
                    parent_review_sha256=self.producer.parent_sha,
                    rebound_receipt_sha256=sha256(receipt_bytes).hexdigest(),
                    source_received_at=receipt['source_received_at'],
                    evidence_archive=archive)


class ArchivedRebindingDailyEvidenceReader(RebindingDailyEvidenceReader):
    """Execution-facing reader: verified signals require a complete archive."""
    def __init__(self, *, archive_root, **kwargs):
        require(archive_root is not None, 'DAILY_EVIDENCE_ARCHIVE_REQUIRED')
        super().__init__(archive_root=archive_root, **kwargs)
