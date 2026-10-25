"""Server-configured read-only saved evidence adapter, no network or approval.

Constructor arguments are deployment configuration, never browser input. A missing
release intentionally stops before reading evidence. Reviewed file paths are
explicit, bounded to one evidence root and pinned by the independently stored
server receipt. This module does not promote draft receipts.
"""
from pathlib import Path

from core.strategy_account_difference import require
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle


class SavedDailyEvidenceAdapter:
    def __init__(self, *, root, release_path=None, trusted_release_sha256=None,
                 receipt_path=None, trusted_receipt_sha256=None,
                 calendar_path=None, source_paths=None):
        self.root = Path(root).resolve()
        self.release_path = release_path
        self.release_sha = trusted_release_sha256
        self.receipt_path = receipt_path
        self.receipt_sha = trusted_receipt_sha256
        self.calendar_path = calendar_path
        self.source_paths = dict(source_paths or {})
        self.last_result = None

    def _read(self, relative):
        require(type(relative) is str and bool(relative), 'SERVER_EVIDENCE_PATH_REQUIRED')
        path = self.root / relative
        require(not path.is_symlink() and
                all(not parent.is_symlink() for parent in path.parents),
                'SERVER_EVIDENCE_SYMLINK_REFUSED')
        require(path.resolve().is_relative_to(self.root) and path.is_file(),
                'SERVER_EVIDENCE_PATH_OUTSIDE_ROOT')
        require(path.stat().st_size <= 32 * 1024 * 1024, 'SERVER_EVIDENCE_FILE_BUDGET')
        return path.read_bytes()

    def verify(self, state, target, now):
        if self.release_path is None or self.release_sha is None:
            self.last_result = dict(status='WAIT_POLICY_RELEASE', signal=None)
            return self.last_result
        require(len(self.source_paths) <= 2000, 'SERVER_EVIDENCE_DOMAIN_BUDGET')
        files = {}
        total = 0
        for name, path in self.source_paths.items():
            raw = self._read(path)
            total += len(raw)
            require(total <= 32 * 1024 * 1024, 'SERVER_EVIDENCE_TOTAL_BUDGET')
            files[name] = raw
        result = verify_daily_signal_bundle(
            state=state, target=target, now=now.isoformat(),
            release_bytes=self._read(self.release_path),
            trusted_release_sha256=self.release_sha,
            calendar_bytes=self._read(self.calendar_path),
            receipt_bytes=self._read(self.receipt_path) if self.receipt_path is not None else None,
            trusted_receipt_sha256=self.receipt_sha,
            files=files)
        self.last_result = result
        return result

    def __call__(self, state, target, now):
        return self.verify(state, target, now)['signal']
