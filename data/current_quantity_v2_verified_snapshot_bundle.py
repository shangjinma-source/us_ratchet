"""Live service adapter; preserves the sealed research implementation bytes."""
from copy import deepcopy
from hashlib import sha256
from pathlib import PurePosixPath
import re

from data.current_cash_portfolio_research import ResearchExpiredError


class VerifiedSnapshotBundleService:
    """Delegate research unchanged and combine fresh source reads for consumers."""

    def __init__(self, service, *, source_withdrawals=()):
        self._service = service
        self._withdrawals = deepcopy(tuple(source_withdrawals))
        for record in self._withdrawals:
            if (set(record) != {'input_path', 'input_sha256', 'descriptor_sha256', 'reason', 'evidence'}
                    or not isinstance(record['reason'], str) or not record['reason'].strip()
                    or not record['evidence']):
                raise ValueError('INVALID_SOURCE_WITHDRAWAL')
            for value in (record['input_sha256'], record['descriptor_sha256'], *record['evidence'].values()):
                if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
                    raise ValueError('INVALID_SOURCE_WITHDRAWAL_HASH')
            for name in (record['input_path'], *record['evidence']):
                if (not isinstance(name, str) or not name or '\\' in name or ':' in name
                        or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
                    raise ValueError('INVALID_SOURCE_WITHDRAWAL_PATH')
            # Evidence authenticates this server-owned revocation, not prices.
            for name, expected in record['evidence'].items():
                path = (service.root / name).resolve()
                if (not path.is_relative_to(service.root.resolve())
                        or sha256(path.read_bytes()).hexdigest() != expected):
                    raise ValueError('SOURCE_WITHDRAWAL_EVIDENCE_CHANGED')

    def _withdrawal(self, descriptor):
        # Match the input itself, so rewrapping it in a new descriptor cannot
        # revive it. descriptor_sha256 records the deployment being withdrawn.
        for record in self._withdrawals:
            if descriptor['source_hashes'].get(descriptor['input_path']) == record['input_sha256']:
                return deepcopy(record)
        return None

    def _require_admitted(self, descriptor):
        if self._withdrawal(descriptor) is not None:
            raise ValueError('RESEARCH_SOURCE_WITHDRAWN')

    def require_source_hashes_admitted(self, source_hashes):
        """Revalidate frozen continuation evidence without a snapshot cache."""
        for record in self._withdrawals:
            if record['input_sha256'] in source_hashes.values():
                raise ValueError('RESEARCH_SOURCE_WITHDRAWN')

    def calculate(self, entered_cash):
        with self._service.lock:
            self._require_admitted(self._service.loader())
            return self._service.calculate(entered_cash)

    def snapshot(self, research_id):
        with self._service.lock:
            view = self._service.snapshot(research_id)
            record = self._withdrawal(self._service.snapshots[research_id]['descriptor'])
            if record is not None:
                view.update(status='UNAVAILABLE', error_code='RESEARCH_SOURCE_WITHDRAWN',
                            source_admission_status='WITHDRAWN', source_withdrawal=record,
                            research_only=True, execution_blocked=True)
            return view

    def decision(self, research_id):
        with self._service.lock:
            self._require_admitted(self._service.loader())
            return self._service.decision(research_id)

    def __getattr__(self, name):
        return getattr(self._service, name)

    def verified_snapshot_bundle(self, research_id):
        # Never cache source verification across calls. The base lock also guards
        # the snapshot lookup, descriptor comparison and returned detached data.
        service = self._service
        with service.lock:
            if research_id not in service.snapshots:
                raise ResearchExpiredError('V2 snapshot unknown; explicit cash calculation required')
            saved = service.snapshots[research_id]
            self._require_admitted(saved['descriptor'])
            self._require_admitted(service.loader())
            descriptor, _, _, files = service._load()
            if descriptor != saved['descriptor']:
                raise ValueError('V2_SNAPSHOT_SOURCE_CHANGED')
            return deepcopy(dict(decision=saved['decision'], snapshot=saved['view'],
                                 files=files, source_hashes=descriptor['source_hashes']))
