"""Candidate reader: initial risk starts at the completed close preceding selection.

Requires explicit server release validation. Never mounts or releases on import.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from data.monthly_risk_epoch import initial_completed_risk_session

from core.strategy_account_ledger import canonical, require
from data.monthly_cap_exit_packet import apply_cap_exit_packet
from data.strategy_monthly_supplement_capture import restore_reviewed_monthly_history
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.strategy_bounded_source_gate_v1 import _read_digest


class MonthlyCapExitReaderV4(ArchivedRebindingDailyEvidenceReader):
    def __init__(self, *, source_reader, risk_store, source_archive_root,
                 output_archive_root, release_bytes, validate_release, risk_history):
        self.source_reader = source_reader
        self.risk_store = risk_store
        self.source_archive_root = Path(source_archive_root).absolute()
        self.output_archive_root = Path(output_archive_root).absolute()
        self.release_bytes = release_bytes
        self.validate_release = validate_release
        self.last_projection = None
        self.risk_history = risk_history

    def __call__(self, account, target, now):
        self.last_projection = None
        self.validate_release()
        admitted = self.source_reader(account, target, now)
        if admitted.get('signal') is None:
            return admitted
        archive = admitted['evidence_archive']
        digest = archive['receipt_sha256']
        require(isinstance(digest, str) and len(digest) == 64 and
                all(char in '0123456789abcdef' for char in digest), 'CAP_SOURCE_ARCHIVE_HASH')
        folder = self.source_archive_root/digest
        require(Path(archive['receipt_path']).absolute() == folder/'receipt.json', 'CAP_SOURCE_ARCHIVE_SCOPE')
        require(_read_digest(folder/'receipt.json', 4*1024*1024) == digest, 'CAP_SOURCE_RECEIPT_CHANGED')
        raw = (folder/'receipt.json').read_bytes()
        receipt = json.loads(raw)
        require(receipt['target_id'] == target['target_id'] and
                receipt['account_revision'] == account['revision'], 'CAP_SOURCE_ACCOUNT_CHANGED')
        files = {}
        for name, value in receipt['source_sha256'].items():
            require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'CAP_SOURCE_HASH')
            path = folder/'sources'/(value+'.bin')
            require(_read_digest(path, 32*1024*1024) == value, 'CAP_SOURCE_BYTES_CHANGED')
            files[name] = path.read_bytes()
        # Existing archive routine checks manifest/completion and all source bytes.
        archive_rebound_evidence(root=self.source_archive_root, receipt_bytes=raw, files=files)
        inputs = json.loads(files[receipt['normalized_inputs_path']])
        previous = self.risk_store.read(account['account_id'])
        month = target['payload']['target_month']
        same_month = previous is not None and previous.get('target_month') == month
        decision = previous['decision_date'] if same_month else initial_completed_risk_session(
            inputs=inputs, target=target, now=now)
        require(decision <= inputs['signal_date'], 'WAIT_FIRST_CONFIGURATION_CLOSE')
        if receipt.get('monthly_history_inputs') or receipt.get('full_domain_inputs_path'):
            inputs = restore_reviewed_monthly_history(receipt=receipt, files=files, decision_date=decision)
        if same_month and set(previous['peaks']) - set(inputs['histories']):
            from data.strategy_monthly_risk_history_v1 import merge_risk_histories
            packets = self.risk_history(account=account, target=target, previous=previous, inputs=inputs)
            inputs, extra_files, references = merge_risk_histories(inputs=inputs, packets=packets,
                account=account, target=target, previous=previous)
            for name, body in extra_files.items():
                require(name not in files or files[name] == body, 'RISK_SUPPLEMENT_SOURCE_COLLISION')
                files[name] = body
            receipt = dict(receipt, risk_supplement_receipts=references)
            require(self.risk_store.read(account['account_id']) == previous, 'RISK_SUPPLEMENT_STATE_CHANGED')
        result = apply_cap_exit_packet(target=target, inputs=inputs,
            risk_store=self.risk_store, account_id=account['account_id'], decision_date=decision,
            expected_previous_session=previous['session_date'] if previous else None,
            authorized_monthly_reset=decision if previous and not same_month else None)
        self.validate_release()
        proof = canonical(dict(policy_id='MONTHLY_CAP50_EXIT20', source_archive=archive,
            release_sha256=sha256(self.release_bytes).hexdigest(), projection=result))
        files['cap-exit/projection.json'] = proof
        files['cap-exit/release.json'] = self.release_bytes
        receipt = dict(receipt, release_sha256=sha256(self.release_bytes).hexdigest(),
                       cap_exit_projection_path='cap-exit/projection.json',
                       source_sha256={name: sha256(body).hexdigest() for name, body in files.items()})
        projected_archive = archive_rebound_evidence(root=self.output_archive_root,
            receipt_bytes=canonical(receipt), files=files)
        signal = deepcopy(admitted['signal'])
        signal.update(policy_id='MONTHLY_CAP50_EXIT20',
            effective_target_quantities=result['effective_target_quantities'],
            evidence_id=projected_archive['receipt_sha256'], evidence_archive=projected_archive)
        self.last_projection = result
        return dict(admitted, signal=signal, evidence_archive=projected_archive)
