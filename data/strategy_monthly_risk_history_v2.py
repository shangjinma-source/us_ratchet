"""Collect missing tracked securities and merge source-reviewed monthly rows.

This is a risk-only evidence path. It does not change account shares or targets.
The deployment builder must authenticate source pins and collection authority.
"""
from copy import deepcopy
from hashlib import sha256
import json
from core.strategy_account_ledger import canonical, require
from data.strategy_daily_security_domain_v1 import locate_unit_baseline_sources
from data.strategy_monthly_risk_capture_v2 import (
    prepare_risk_supplement_request, capture_supplement, review_risk_supplement_packets)


class MonthlyRiskHistoryV2:
    def __init__(self, *, root, source, directory, source_pins, account_reader,
                 target_reader, risk_store, clock, validate, fetch_daily=None, fetch_official=None):
        self.root, self.source, self.directory = root, source, directory
        self.source_pins = source_pins
        self.account_reader, self.target_reader, self.risk_store = account_reader, target_reader, risk_store
        self.clock, self.validate = clock, validate
        self.fetch_daily, self.fetch_official = fetch_daily, fetch_official

    def __call__(self, *, account, target, previous, inputs):
        self.validate()
        missing = set(previous['peaks']) - set(inputs['histories'])
        require(bool(missing), 'RISK_SUPPLEMENT_DOMAIN_EMPTY')
        def unchanged():
            self.validate()
            require(self.account_reader() == account and self.target_reader() == target
                    and self.risk_store.read(account['account_id']) == previous,
                    'RISK_SUPPLEMENT_SNAPSHOT_CHANGED')
        unchanged()
        paths = locate_unit_baseline_sources(root=self.root,
            evidence_root=self.source['target_evidence_root'],
            binding=target['payload']['decision']['payload']['input_binding'])
        prepared = prepare_risk_supplement_request(root=self.root, state=account, target=target,
            identity_reference=self.source['identity'], calendar_reference=self.source['calendar'],
            unit_source_paths=paths, source_pins=self.source_pins, security_ids=missing,
            decision_date=previous['decision_date'], now=self.clock(), risk_state=previous)
        require(prepared['request'] is not None, prepared['status'])
        def binding():
            unchanged()
            return prepared['binding']
        capture = capture_supplement(directory=self.directory, request=prepared['request'],
            binding=prepared['binding'], read_binding=binding, execute=True, clock=self.clock,
            fetch_daily=self.fetch_daily, fetch_official=self.fetch_official)
        result = review_risk_supplement_packets(root=self.root, capture=capture,
            request=prepared['request'], binding=prepared['binding'], state=account, target=target,
            configurations=prepared['configurations'], risk_state=previous, clock=self.clock)
        unchanged()
        return result['packets']


def merge_risk_histories(*, inputs, packets, account, target, previous):
    """Caller supplies packets from the authorized reviewer, not client hashes."""
    result = deepcopy(inputs); files = {}; references = {}
    missing = set(previous['peaks']) - set(inputs['histories'])
    require(set(packets) == missing, 'RISK_SUPPLEMENT_PACKET_DOMAIN')
    for sid, packet in packets.items():
        raw = packet['receipt_bytes']; digest = sha256(raw).hexdigest()
        require(digest == packet['trusted_receipt_sha256'], 'RISK_SUPPLEMENT_RECEIPT_CHANGED')
        receipt = json.loads(raw)
        require(receipt['account_id'] == account['account_id'] and
                receipt['account_revision'] == account['revision'] and receipt['target_id'] == target['target_id'],
                'RISK_SUPPLEMENT_ACCOUNT_CHANGED')
        require(set(packet['files']) == set(receipt['source_sha256']), 'RISK_SUPPLEMENT_SOURCE_DOMAIN')
        for name, body in packet['files'].items():
            require(sha256(body).hexdigest() == receipt['source_sha256'][name], 'RISK_SUPPLEMENT_BYTES_CHANGED')
            require(name not in files or files[name] == body, 'RISK_SUPPLEMENT_SOURCE_COLLISION')
            files[name] = body
        full = json.loads(packet['files'][receipt['monthly_history_inputs_path']])
        require(set(full['histories']) == {sid} and all(full[key] == inputs[key] for key in
            ('signal_date', 'observed_at', 'session_dates', 'session_close_times')),
            'RISK_SUPPLEMENT_CALENDAR_CHANGED')
        require(full['base_target']['monthly_decision_date'] == previous['decision_date'] and
            full['histories'][sid]['units']['basis_id'] == previous['unit_ids'][sid],
            'RISK_SUPPLEMENT_UNITS_CHANGED')
        result['histories'][sid] = deepcopy(full['histories'][sid])
        result['base_target']['price_units'][sid] = previous['unit_ids'][sid]
        name = 'risk-supplement-receipts/'+digest+'.json'
        files[name] = raw; references[sid] = dict(path=name, sha256=digest)
    return result, files, references
