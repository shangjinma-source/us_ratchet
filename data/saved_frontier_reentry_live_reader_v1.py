"""Unrouted source-admitted PRECOMMIT boundary and atomic risk/reference reader.

Construction performs no capture or migration. The release builder owns code
pins and policy authority; this reader retains the account and risk snapshots
through source review and never creates orders or changes monthly targets.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from data.monthly_risk_epoch import initial_completed_risk_session
from data.saved_frontier_first_window_v1 import SOURCES
from data.saved_frontier_supplement_request_v1 import prepare_frontier_supplement_request
from data.saved_frontier_source_reader_v1 import read_frontier_capture
from data.saved_frontier_reentry_exit_packet_v1 import prepare_frontier_reentry_exit_packet, apply_frontier_reentry_exit_packet
from data.reentry_decision_boundary_v1 import DecisionBoundaryArchive
from data.strategy_account_session_snapshot_v1 import account_session_snapshot
from data.strategy_daily_security_domain_v1 import locate_unit_baseline_sources
from data.strategy_daily_rolling_parent_v3 import pinned
from data.strategy_daily_session_capture import stamp, reject_links
from data.strategy_monthly_supplement_gzip_v1 import capture_supplement
from data.strategy_daily_rebound_archive import archive_rebound_evidence


POLICY_ID = 'SAVED_FRONTIER_CAP50_EXIT20_V1'


def capture_namespace(root, *, started, session):
    """Bound captures to one immutable slot per 15 minutes of this session.

    The original request/binding and downstream capture ID remain unchanged.
    No failed slot is deleted or automatically retried; the next slot is a new
    observation with its own real transport timestamps, never a re-dated raw.
    """
    opened, closed = stamp(session['open']), stamp(session['close'])
    current = stamp(started)
    require(opened <= current < closed and
            0 < (closed-opened).total_seconds() <= 8*3600,
            'FRONTIER_CAPTURE_SLOT_SESSION')
    require(current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            == session['date'], 'FRONTIER_CAPTURE_SLOT_DATE')
    slot = int((current-opened).total_seconds() // 900)
    directory = Path(root)/'refresh-v1'/session['date']/f'{slot:02d}'
    reject_links(directory)
    return directory


class SavedFrontierReentryLiveReader:
    def __init__(self, *, root, monthly_view, risk_store, source_configuration,
                 source_pins, capture_root, archive_root, release_bytes, clock,
                 validate_sources, boundary_root, fetch_daily=None, fetch_official=None):
        self.root = Path(root).resolve()
        self.view, self.risk = monthly_view, risk_store
        self.source = deepcopy(source_configuration)
        self.pins = deepcopy(source_pins)
        self.capture_root, self.archive_root = Path(capture_root), Path(archive_root)
        self.release_bytes, self.clock, self.validate = release_bytes, clock, validate_sources
        self.fetch_daily, self.fetch_official = fetch_daily, fetch_official
        self.boundary_root=Path(boundary_root)

    def __call__(self, state, target, now, *, proposal):
        self.validate()
        started = stamp(now)
        release = json.loads(self.release_bytes)
        require(release.get('authorized') is True and release.get('policy_id') == POLICY_ID
                and release.get('monthly_cap') == '1/2' and release.get('exit_ratio') == '4/5'
                and release.get('sma20_overlay') is False, 'FRONTIER_RELEASE_REQUIRED')
        require(stamp(release['authorized_at']) <= started, 'FRONTIER_RELEASE_NOT_YET_AUTHORIZED')
        calendar_raw = pinned(self.root, self.source['calendar'], maximum=8*1024*1024)
        calendar = json.loads(calendar_raw)
        require(calendar['schema'] == 'FIXED_EXCHANGE_SESSIONS_V1'
                and calendar['exchange'] == 'NASDAQ', 'FRONTIER_CALENDAR_SCHEMA')
        rows = calendar['sessions']
        dates = [row['date'] for row in rows]
        require(dates == sorted(set(dates)), 'FRONTIER_CALENDAR_ORDER')
        today = started.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        sessions = [row for row in rows if row['date'] == today]
        if not sessions or not stamp(sessions[0]['open']) <= started < stamp(sessions[0]['close']):
            return dict(status='WAIT_SIGNAL', signal=None, reason='WAIT_POLICY_REVIEW_SESSION')
        session = sessions[0]
        previous = deepcopy(self.risk.read(state['account_id']))
        reference_before=deepcopy(self.risk.read_reference(state['account_id']))
        if reference_before is None:
            return dict(status='WAIT_SIGNAL',signal=None,reason='WAIT_EXPLICIT_REFERENCE_ACTIVATION')
        closes = {row['date']: row['close'] for row in rows}
        completed = [day for day in dates if stamp(closes[day]) <= started]
        require(bool(completed), 'RISK_SELECTION_CLOSE_REQUIRED')
        same_month = previous is not None and previous['target_month'] == target['payload']['target_month']
        decision = (previous['decision_date'] if same_month else initial_completed_risk_session(
            inputs=dict(base_target=dict(monthly_target_created_at=target['payload']['created_at']),
                        signal_date=completed[-1], session_dates=dates,
                        session_close_times=dict(closes=closes)), target=target, now=started))

        def unchanged(*, expected_risk=previous, expected_reference=reference_before):
            self.validate()
            require(self.view.monthly.accounts.read() == state
                    and self.view.monthly.current() == target, 'FRONTIER_CAPTURE_SNAPSHOT_CHANGED')
            require(self.view.require_proposal(target_id=target['target_id'],
                    expected_proposal_id=proposal['proposal_id']) == proposal, 'FRONTIER_PROPOSAL_CHANGED')
            require(self.risk.read(state['account_id']) == expected_risk, 'FRONTIER_RISK_SNAPSHOT_CHANGED')
            require(self.risk.read_reference(state['account_id'])==expected_reference,'FRONTIER_REFERENCE_SNAPSHOT_CHANGED')
            current = stamp(self.clock())
            require(started <= current < stamp(session['close']), 'FRONTIER_CAPTURE_SESSION_ENDED')

        unchanged()
        source_pins = self.pins
        if type(source_pins) is dict:
            source_pins = [dict(path=name, sha256=digest) for name, digest in source_pins.items()]
        pin_map = {row['path']: row for row in source_pins}
        require(len(pin_map) == len(source_pins) and SOURCES <= set(pin_map), 'FRONTIER_SOURCE_PIN_SCOPE')
        prepared = prepare_frontier_supplement_request(root=self.root, state=state, target=target,
            proposal=proposal, risk_state=previous, identity_reference=self.source['identity'],
            calendar_reference=self.source['calendar'],
            unit_source_paths=locate_unit_baseline_sources(root=self.root,
                evidence_root=self.source['target_evidence_root'],
                binding=target['payload']['decision']['payload']['input_binding']),
            source_pins=[pin_map[name] for name in sorted(SOURCES)], decision_date=decision, now=started)
        if prepared['request'] is None:
            return dict(status='WAIT_SIGNAL', signal=None, reason=prepared['status'])

        def read_binding():
            unchanged()
            return deepcopy(prepared['binding'])

        reject_links(self.capture_root)
        unchanged()
        directory = capture_namespace(self.capture_root, started=self.clock(), session=session) / 'gzip-v1'
        capture = capture_supplement(directory=directory, request=prepared['request'],
            binding=prepared['binding'], read_binding=read_binding, execute=True, clock=self.clock,
            fetch_daily=self.fetch_daily, fetch_official=self.fetch_official)
        unchanged()
        reviewed_at = stamp(self.clock())
        source = read_frontier_capture(root=self.root, prepared=prepared, capture=capture,
            state=state, target=target, proposal=proposal, risk_state=previous, now=reviewed_at)
        unchanged()
        inputs = source['review']['inputs']
        recorded_before = self.risk.recorded_prices(state['account_id'], decision)
        prepared_exit=prepare_frontier_reentry_exit_packet(target=target,proposal=proposal,inputs=inputs,
            risk_store=self.risk,account_id=state['account_id'],decision_date=decision,
            expected_previous_session=previous['session_date'] if previous else None,
            authorized_monthly_reset=decision if previous and not same_month else None)
        files = dict(capture['files'])

        def include(name, raw):
            require(name not in files or files[name] == raw, 'FRONTIER_ARCHIVE_SOURCE_COLLISION')
            files[name] = raw

        for sid, packet in source['packets'].items():
            for name, raw in packet['files'].items():
                include(name, raw)
            include('frontier/packets/' + sha256(sid.encode()).hexdigest() + '.json', packet['receipt_bytes'])
        for name, value in (('proposal', proposal), ('source-review', source['review']),
                            ('risk-before', previous),
                            ('precommit-observations',prepared_exit['observations']),
                            ('precommit-preparation',prepared_exit),
                            ('prepared', prepared), ('account', state), ('target', target),
                            ('recorded-prices-before', recorded_before),
                            ('capture', {name: value for name, value in capture.items() if name != 'files'})):
            include('frontier/' + name + '.json', canonical(value))
        include('frontier/release.json', self.release_bytes)
        include('frontier/calendar.json', calendar_raw)
        receipt = dict(schema='SERVER_REVIEWED_REENTRY_INTENT_V1',phase='PRECOMMIT',risk_committed=False,
            risk_before_sha256=sha256(canonical(previous)).hexdigest(),
            preparation_sha256=prepared_exit['preparation_sha256'], policy_id=POLICY_ID,
            account_id=state['account_id'], account_revision=state['revision'], target_id=target['target_id'],
            proposal_id=proposal['proposal_id'], target_month=target['payload']['target_month'],
            valid_from=reviewed_at.isoformat(), valid_until=session['close'],
            execution_session=session, normalized_inputs_path='frontier/inputs.json',
            release_sha256=sha256(self.release_bytes).hexdigest(), policy_approved=False)
        include(receipt['normalized_inputs_path'], canonical(inputs))
        receipt['source_sha256'] = {name: sha256(raw).hexdigest() for name, raw in files.items()}
        intent_receipt=canonical(receipt)
        intent_files=deepcopy(files)
        def authenticate_current():
            unchanged()
            checked=read_frontier_capture(root=self.root,prepared=prepared,capture=capture,
                state=state,target=target,proposal=proposal,risk_state=previous,now=stamp(self.clock()))
            def source_identity(value):
                value=deepcopy(value);review=value['review']
                review_id=review.pop('review_id')
                require(sha256(canonical(review)).hexdigest()==review_id,'FRONTIER_REVIEW_ID_CHANGED')
                review.pop('reviewed_at');review.pop('valid_from')
                review['inputs'].pop('observed_at')
                for packet in value['packets'].values():
                    raw=packet['receipt_bytes']
                    require(sha256(raw).hexdigest()==packet['trusted_receipt_sha256'],'FRONTIER_PACKET_ID_CHANGED')
                    document=json.loads(raw)
                    # Only generated review clocks and their derived IDs vary.
                    # Publication, source receive times, raw files and price data
                    # stay exact; the fresh full source review above still runs.
                    document.pop('valid_from');document.pop('available_at')
                    packet['receipt_bytes']=canonical(document)
                    packet['trusted_receipt_sha256']=sha256(packet['receipt_bytes']).hexdigest()
                return value
            require(source_identity(checked)==source_identity(source),'FRONTIER_PRECOMMIT_SOURCE_CHANGED')
            again=prepare_frontier_reentry_exit_packet(target=target,proposal=proposal,inputs=source['review']['inputs'],
                risk_store=self.risk,account_id=state['account_id'],decision_date=decision,
                expected_previous_session=previous['session_date'] if previous else None,
                authorized_monthly_reset=decision if previous and not same_month else None)
            require(again==prepared_exit,'FRONTIER_PRECOMMIT_PREPARATION_CHANGED')
            unchanged()
            return dict(receipt_bytes=intent_receipt,files=deepcopy(intent_files))
        authority=DecisionBoundaryArchive(root=self.boundary_root/'evidence',
            source_configuration_bytes=canonical(self.source),release_bytes=self.release_bytes,
            authenticate_current=authenticate_current,clock=self.clock)
        current_intent_ref=authority.archive_current()
        current_intent=authority.read_verified(current_intent_ref)
        require(current_intent['status']=='SERVER_ARCHIVED_BOUNDARY_VERIFIED','FRONTIER_BOUNDARY_UNVERIFIED')
        contexts={};boundary_refs={}
        for observation in prepared_exit['observations']:
            day=observation['session_date'];context=dict(completed_at=closes[day])
            key=sha256(canonical(dict(account_id=state['account_id'],decision_date=decision,session_date=day))).hexdigest()
            index=self.boundary_root/'references'/(key+'.json');reject_links(index)
            ref=None
            if index.exists():
                require(index.stat().st_size<=8192,'FRONTIER_BOUNDARY_REFERENCE_BUDGET')
                ref=json.loads(index.read_bytes())
            elif day==completed[-1] and stamp(closes[day])>stamp(reference_before['activation_at']):
                ref=current_intent_ref;index.parent.mkdir(parents=True,exist_ok=True)
                raw=canonical(ref)
                try:
                    with index.open('xb') as stream:
                        stream.write(raw);stream.flush();__import__('os').fsync(stream.fileno())
                except FileExistsError:
                    require(index.read_bytes()==raw,'FRONTIER_BOUNDARY_REFERENCE_RACE')
            if ref is not None:
                verified=authority.read_verified(ref)
                require(verified['status']=='SERVER_ARCHIVED_BOUNDARY_VERIFIED','FRONTIER_BOUNDARY_UNVERIFIED')
                # The old intent authenticates its own original target/proposal.
                # A current same-epoch cash rebalance is separately authenticated
                # by prepare/unchanged; do not rewrite historical holdings context.
                frozen=verified['observation']
                require(all(frozen[k]==observation[k] for k in ('session_date','decision_date','closes','unit_ids')),
                        'FRONTIER_BOUNDARY_OBSERVATION_CHANGED')
                snapshot=account_session_snapshot(self.view.monthly.accounts,account_id=state['account_id'],
                    session_date=day,expected_latest_revision=state['revision'],
                    decision_evidence=verified['decision_evidence'],
                    decision_evidence_sha256=verified['decision_evidence_sha256'],
                    security_ids=tuple(observation['closes']))
                if snapshot['status']!='JOURNAL_PREFIX_VERIFIED_UNITS_NOT_CERTIFIED':
                    return dict(status='WAIT_SIGNAL',signal=None,reason=snapshot.get('reason','WAIT_ACCOUNT_PREFIX'),
                                reference_state=reference_before,risk_committed=False)
                context['holdings']=dict(session_date=day,account_id=state['account_id'],
                    account_revision=snapshot['account_revision'],shares=snapshot['shares'],
                    unit_ids=verified['unit_ids'],evidence_sha256=snapshot['evidence_sha256'],
                    event_boundary_sha256=snapshot['event_boundary_sha256'])
                boundary_refs[day]=ref
            # Missing old intent supplies no invented holdings. If this session
            # first triggers a post-activation exit, atomic advance must rollback.
            contexts[day]=context
        unchanged()
        try:
            projection=apply_frontier_reentry_exit_packet(target=target,proposal=proposal,inputs=inputs,
                risk_store=self.risk,account_id=state['account_id'],decision_date=decision,
                expected_previous_session=previous['session_date'] if previous else None,
                expected_reference_version=reference_before['version'],activation_id=reference_before['activation_id'],
                session_contexts=contexts,expected_preparation_sha256=prepared_exit['preparation_sha256'],
                authorized_monthly_reset=decision if previous and not same_month else None)
        except ValueError as error:
            if str(error)=='REFERENCE_EXIT_HOLDINGS_EVIDENCE_REQUIRED':
                unchanged()
                return dict(status='WAIT_SIGNAL',signal=None,reason='WAIT_ORIGINAL_DECISION_BOUNDARY_MISSING',
                            risk_committed=False,reference_state=reference_before)
            raise
        updated=deepcopy(projection['state']);reference_updated=deepcopy(projection['reference_state'])
        unchanged(expected_risk=updated,expected_reference=reference_updated)
        include('frontier/risk-projection.json',canonical(projection))
        include('frontier/reentry-boundaries.json',canonical(boundary_refs))
        include('frontier/current-precommit-boundary.json',canonical(current_intent_ref))
        receipt=dict(receipt,schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',phase='COMMITTED',risk_committed=True)
        receipt['source_sha256']={name:sha256(raw).hexdigest() for name,raw in files.items()}
        reject_links(self.archive_root)
        archive = archive_rebound_evidence(root=self.archive_root, receipt_bytes=canonical(receipt), files=files)
        unchanged(expected_risk=updated,expected_reference=reference_updated)
        signal = dict(account_id=state['account_id'], account_revision=state['revision'],
            target_id=target['target_id'], proposal_id=proposal['proposal_id'], policy_id=POLICY_ID,
            effective_target_quantities=deepcopy(projection['effective_target_quantities']),
            observed_at=reviewed_at.isoformat(), available_at=reviewed_at.isoformat(),
            valid_from=reviewed_at.isoformat(), valid_until=session['close'],
            evidence_id=archive['receipt_sha256'], evidence_archive=archive)
        commit_context=dict(schema='SERVER_REENTRY_COMMIT_CONTEXT_V1',
            source_inputs_sha256=sha256(canonical(inputs)).hexdigest(),
            prepared_exit=deepcopy(prepared_exit),session_contexts=deepcopy(contexts),
            activation_id=reference_before['activation_id'],
            committed_risk_sha256=sha256(canonical(updated)).hexdigest(),
            committed_reference_sha256=sha256(canonical(reference_updated)).hexdigest())
        commit_context['context_sha256']=sha256(canonical(commit_context)).hexdigest()
        return dict(status='DAILY_SIGNAL_READY', signal=signal, evidence_archive=archive,
                    risk_projection=projection, source_review=source['review'],
                    reference_state=reference_updated, boundary_references=boundary_refs,
                    reentry_execution_applied=False, reentry_commit_context=commit_context)
