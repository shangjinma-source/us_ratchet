"""Versioned same-session source supplementation; requires explicit pinned authority."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_domain_packet_reader_v3 import DomainSessionDailyPacketReaderV3
from data.strategy_daily_domain_policy_reader_v2 import ExplicitDomainPolicyReviewReaderV2
from data.strategy_daily_first_window_v4 import SOURCES
from data.strategy_daily_rolling_parent_v3 import pinned, bounded_read
from data.strategy_daily_security_domain_v1 import locate_unit_baseline_sources
from data.strategy_daily_session_capture import stamp, reject_links
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle
from data.strategy_monthly_supplement_capture import (
    prepare_supplement_request, capture_supplement, review_supplement_packets,
    merge_supplement_packets, review_supplement_policy)

EXTRA_SOURCES = SOURCES | {
    'data/strategy_daily_domain_packet_reader_v3.py',
    'data/strategy_monthly_supplement_reader.py',
    'data/strategy_monthly_supplement_capture.py',
}


class MonthlySupplementReader(DomainSessionDailyPacketReaderV3, ExplicitDomainPolicyReviewReaderV2):
    def __init__(self, *, account_reader, target_reader, risk_store,
                 fetch_daily=None, fetch_official=None, **kwargs):
        ExplicitDomainPolicyReviewReaderV2.__init__(self, **kwargs)
        self.account_reader = account_reader
        self.target_reader = target_reader
        self.risk_store = risk_store
        self.fetch_daily = fetch_daily
        self.fetch_official = fetch_official

    def _complete_domain(self, *, state, target, current, needed, packets,
                         calendar_raw, terminal_path, terminal_sha256):
        def wait(reason):
            return dict(status='WAIT_SIGNAL', signal=None, reason=reason)
        if self.review_reference is None:
            return wait('WAIT_POLICY_REVIEW_AUTHORIZATION')
        started = stamp(self.clock())
        require(current <= started, 'SUPPLEMENT_CLOCK_REVERSED')
        control_raw, control, release, archive_root = self._authorization(state, started, calendar_raw)
        authorization = control.get('monthly_supplement', {})
        require(authorization.get('authorized') is True and
            authorization.get('schema') == 'CURRENT_SESSION_MONTHLY_SUPPLEMENT_V1',
            'SUPPLEMENT_AUTHORIZATION_REQUIRED')
        pins = {ref['path']: ref for ref in control['code_pins']}
        require(EXTRA_SOURCES <= set(pins), 'SUPPLEMENT_CODE_SCOPE')
        for name in EXTRA_SOURCES:
            require(pinned(self.root, pins[name], maximum=32*1024*1024) ==
                (Path(__file__).resolve().parents[1]/name).read_bytes(), 'SUPPLEMENT_EXECUTING_CODE')
        relative = Path(authorization['capture_root'])
        require(not relative.is_absolute() and '..' not in relative.parts and bool(relative.parts),
            'SUPPLEMENT_CAPTURE_PATH')
        directory = self.root/relative
        reject_links(directory)
        require(directory.resolve().is_relative_to(self.root) and directory.resolve() != self.root,
            'SUPPLEMENT_CAPTURE_PATH')
        source = json.loads(pinned(self.root, self.reference))
        previous = self.risk_store.read(state['account_id'])
        month = target['payload']['target_month']
        decision = (previous['decision_date'] if previous and previous.get('target_month') == month
            else datetime.fromisoformat(target['payload']['created_at']).astimezone(
                ZoneInfo('America/New_York')).date().isoformat())
        calendar = json.loads(calendar_raw)
        today = started.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        completed = [row['date'] for row in calendar['sessions']
                     if decision <= row['date'] < today]
        saved = self.risk_store.recorded_prices(state['account_id'], decision)
        missing = set(needed)-set(packets)
        for sid in needed & set(packets):
            receipt = json.loads(packets[sid]['receipt_bytes'])
            inputs = json.loads(packets[sid]['files'][receipt['normalized_inputs_path']])
            rows = {row['date'] for row in inputs['histories'][sid]['closes']}
            if not set(completed) <= rows | set(saved.get(sid, {})):
                missing.add(sid)
        binding = dict(account_id=state['account_id'], account_revision=state['revision'],
            target_id=target['target_id'], session=today)
        def read_binding():
            account = self.account_reader(); selected = self.target_reader()
            return dict(account_id=account['account_id'], account_revision=account['revision'],
                target_id=selected['target_id'] if selected else None,
                session=stamp(self.clock()).astimezone(ZoneInfo('America/New_York')).date().isoformat())
        def unchanged():
            require(read_binding() == binding, 'SUPPLEMENT_SNAPSHOT_CHANGED')
            require(sha256(bounded_read(terminal_path)).hexdigest() == terminal_sha256,
                'SUPPLEMENT_TERMINAL_CHANGED')
        unchanged()
        supplements = {}
        if missing:
            prepared = prepare_supplement_request(root=self.root, state=state, target=target,
                identity_reference=source['identity'], calendar_reference=source['calendar'],
                unit_source_paths=locate_unit_baseline_sources(root=self.root,
                    evidence_root=source['target_evidence_root'],
                    binding=target['payload']['decision']['payload']['input_binding']),
                source_pins=[pins[name] for name in sorted(SOURCES)], security_ids=missing,
                decision_date=decision, now=started)
            if prepared['request'] is None:
                return wait(prepared['status'])
            capture = capture_supplement(directory=directory, request=prepared['request'],
                binding=prepared['binding'], read_binding=read_binding, execute=True,
                clock=self.clock, fetch_daily=self.fetch_daily, fetch_official=self.fetch_official)
            reviewed = review_supplement_packets(root=self.root, capture=capture,
                request=prepared['request'], binding=binding, state=state, target=target,
                configurations=prepared['configurations'], clock=self.clock)
            supplements = reviewed['packets']
        unchanged()
        now = stamp(self.clock()).isoformat()
        combined = merge_supplement_packets(existing=packets, supplements=supplements,
            state=state, target=target, now=now)
        if combined.get('receipt') is None:
            return wait(combined['status'])
        all_packets = {sid: supplements.get(sid, packets.get(sid)) for sid in needed}
        event = dict(binding=binding, authorization_sha256=self.review_reference['sha256'],
            terminal_sha256=terminal_sha256,
            packets={sid: packet['trusted_receipt_sha256'] for sid, packet in all_packets.items()})
        event_raw = canonical(event); event_id = sha256(event_raw).hexdigest()
        result = review_supplement_policy(decision_date=decision, state=state, target=target,
            now=now, event_id=event_id, domain=dict(binding, securities={sid:{} for sid in needed}),
            packets=all_packets, release_bytes=release,
            trusted_release_sha256=control['release']['sha256'], calendar_bytes=calendar_raw)
        if result.get('receipt') is None:
            return wait(result['status'])
        receipt = result['receipt']; files = result['files']
        files['supplement-controls/'+self.review_reference['sha256']+'.json'] = control_raw
        files['supplement-events/'+event_id+'.json'] = event_raw
        receipt['source_sha256'] = {name: sha256(body).hexdigest() for name, body in files.items()}
        raw = canonical(receipt)
        verified = verify_daily_signal_bundle(state=state, target=target, now=stamp(self.clock()).isoformat(),
            release_bytes=release, trusted_release_sha256=control['release']['sha256'],
            receipt_bytes=raw, trusted_receipt_sha256=sha256(raw).hexdigest(), files=files,
            calendar_bytes=calendar_raw)
        require(verified['status'] == 'DAILY_SIGNAL_READY', 'SUPPLEMENT_FINAL_VERIFICATION')
        archive = archive_rebound_evidence(root=archive_root, receipt_bytes=raw, files=files)
        unchanged()
        after, _, after_release, after_archive = self._authorization(state, stamp(self.clock()), calendar_raw)
        require(after == control_raw and after_release == release and after_archive == archive_root,
            'SUPPLEMENT_AUTHORIZATION_CHANGED')
        require(stamp(self.clock()) < stamp(receipt['valid_until']), 'SUPPLEMENT_SESSION_ENDED')
        verified['signal']['evidence_archive'] = archive
        return dict(verified, evidence_archive=archive, policy_approved=False)
