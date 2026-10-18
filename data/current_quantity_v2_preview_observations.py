"""Local generated-preview history; never proof of delivery, fills or performance."""
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import re
import base64
from hashlib import sha256

from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_cash_portfolio_research import ResearchExpiredError

HISTORY_SOURCE_BUDGET = 128*1024*1024

PUBLIC_REASONS = frozenset({'OUTSIDE_REGULAR_SESSION', 'SESSION_DATE_MISMATCH',
    'RESEARCH_SNAPSHOT_EXPIRED',
    'LAST_QUOTE_STALE', 'COMPLETED_MINUTE_STALE', 'NO_COMPLETED_VALID_MINUTE',
    'LAST_QUOTE_FUTURE', 'QUOTE_AFTER_CAPTURE', 'REFERENCE_EXPIRED',
    'CURRENT_CASH_REFERENCE_EXPIRED', 'CAPTURE_SUPERSEDED',
    'KNOWN_POST_DECISION_UNIT_ACTION', 'KNOWN_QUOTE_ACTION_UNSUPPORTED',
    'MONTH_MANDATE_REQUIRED', 'RESELECT_REQUIRED', 'EXECUTION_MONTH_NOT_ACTIVE'})


def _quote_captures(supplied, result, decision_id):
    """Select original quote bytes only from the resolver-validated proposal."""
    proposal = supplied['proposal']
    if (proposal['proposal_id'] != result['proposal_id']
            or proposal['account_id'] != result['account_id']
            or proposal['capital_decision_id'] != decision_id
            or proposal['execution_target_id'] != result['execution_target_id']
            or proposal['orders'] != result['orders']):
        raise ValueError('OBSERVATION_PROPOSAL_MISMATCH')
    package = proposal['causal_inputs']['frozen_execution_package']
    pins = package['source_hashes']; encoded = package['files_base64']
    captures = []; total = 0
    def read(path):
        nonlocal total
        value = encoded[path]
        if not isinstance(value, str) or len(value) > 6 * 1024 * 1024:
            raise ValueError('OBSERVATION_SOURCE_LIMIT')
        raw = base64.b64decode(value, validate=True)
        total += len(raw)
        if total > 16 * 1024 * 1024 or sha256(raw).hexdigest() != pins[path]:
            raise ValueError('OBSERVATION_SOURCE_INVALID')
        return raw
    for sid in sorted({order['security_id'] for order in proposal['orders']}):
        ticker = proposal['securities'][sid]['ticker']
        path = package['documents']['quote_receipts'][sid]
        receipt_raw = read(path); receipt = json.loads(receipt_raw)
        raw_path = receipt['raw_path']; raw = read(raw_path)
        if (receipt['security_id'] != sid or receipt['ticker'] != ticker
                or receipt['raw_sha256'] != sha256(raw).hexdigest()):
            raise ValueError('OBSERVATION_RECEIPT_MISMATCH')
        captured = datetime.fromisoformat(receipt['captured_at'])
        if captured.tzinfo is None:
            raise ValueError('OBSERVATION_CAPTURE_TIME_REQUIRED')
        for role, source_path, payload in (
                ('ORIGINAL_QUOTE', raw_path, raw), ('ORIGINAL_QUOTE_RECEIPT', path, receipt_raw)):
            captures.append(dict(role=role, security_id=sid, ticker=ticker,
                original_source_path=source_path, captured_at=receipt['captured_at'], payload=payload))
    return captures


class ObservedCurrentCashPreview:
    def __init__(self, *, service, directory, clock=lambda: datetime.now(timezone.utc), research_context_reader=None,
                 followup_reader=None):
        self.service = service
        self.journal = IntradayObservationJournal(directory)
        self.clock = clock
        self.research_context_reader = research_context_reader
        self.followup_reader = followup_reader

    def preview(self, decision_id):
        started = self.clock()
        context = None
        if self.research_context_reader is not None:
            try:
                view = self.research_context_reader(decision_id)
                if view['decision_id'] != decision_id or view['research_id'] != decision_id[:24]:
                    raise ValueError('OBSERVATION_DECISION_MISMATCH')
                context = {key: deepcopy(view[key]) for key in
                           ('research_id', 'research_version', 'as_of', 'available_cash_exact')}
                context['stocks'] = [{key: row[key] for key in ('security_id', 'ticker')}
                                     for row in view['stocks']]
            except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                context = None
        result = self.service.preview(decision_id)
        observed = self.clock()
        # Only public, bounded fields. Internal exception text and causal files
        # must never become review-page content.
        reason = result.get('reason', '')
        if not isinstance(reason, str) or reason not in PUBLIC_REASONS:
            reason = 'SOURCE_UNAVAILABLE' if result.get('status') != 'READY' else None
        event = dict(event_id=uuid4().hex, schema='V2_GENERATED_PREVIEW_OBSERVATION_V1',
                     request_started_at=started.isoformat(), observed_at=observed.isoformat(),
                     decision_id=decision_id, status=result.get('status'), reason=reason,
                     research_context=context,
                     proposal_id=result.get('proposal_id'),
                     execution_target_id=result.get('execution_target_id'),
                     reference_valid_until=result.get('reference_valid_until'),
                     rows=deepcopy(result.get('rows', [])),
                     orders=deepcopy(result.get('orders', [])),
                     generated_not_confirmed_displayed=True, actual_fill_inferred=False,
                     future_price_evaluation='NOT_EVALUATED')
        captures = []
        evidence_status = 'NOT_REQUIRED_NO_EXECUTABLE_ORDERS'
        if result.get('status') == 'READY' and result.get('proposal_id') and result.get('orders'):
            try:
                supplied = self.service.initial_resolver(result['account_id'], result['proposal_id'], self.clock())
                captures = _quote_captures(supplied, result, decision_id)
                evidence_status = 'SAVED_ORIGINAL_QUOTE_BYTES'
            except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError):
                evidence_status = 'SOURCE_EVIDENCE_UNAVAILABLE'
        event['source_evidence_status'] = evidence_status
        event['source_evidence_missing'] = not bool(captures)
        try:
            receipt = self.journal.record(event, captures)
        except (OSError, ValueError, TypeError):
            # Logging does not convert a valid proposal to a different economic
            # decision. Its absence is visible, never silently called saved.
            result = dict(result, observation_record=dict(status='UNAVAILABLE'))
        else:
            result = dict(result, observation_record=receipt)
        # Persisting the observation takes time. Do not display a quote that
        # expired during the write, even though the generated event is retained.
        failure = None
        if result.get('status') == 'READY' and result.get('proposal_id') and result.get('orders'):
            try:
                self.service.initial_resolver(result['account_id'], result['proposal_id'], self.clock())
            except ResearchExpiredError:
                failure = 'RESEARCH_SNAPSHOT_EXPIRED'
            except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError) as error:
                failure = str(error) if str(error) in PUBLIC_REASONS else 'SOURCE_UNAVAILABLE'
        deadline = result.get('reference_valid_until')
        if result.get('status') == 'READY' and deadline and self.clock() >= datetime.fromisoformat(deadline):
            failure = 'REFERENCE_EXPIRED'
        if failure:
            return dict(status='UNAVAILABLE', reason=failure, decision_id=decision_id,
                        proposal_id=None, orders=[], research_only=True, execution_blocked=True,
                        orders_created=False, account_mutated=False, real_account=False,
                        observation_record=result['observation_record'])
        return result

    def initial_resolver(self, account_id, proposal_id, now):
        return self.service.initial_resolver(account_id, proposal_id, now)

    def history(self, limit=50, *, decision_id=None, research_version=None, available_cash_exact=None):
        if decision_id is not None and (not re.fullmatch(r"[a-f0-9]{64}", decision_id) or not research_version or not available_cash_exact):
            raise ValueError("EXACT_OBSERVATION_BINDING_REQUIRED")
        limit = max(0, min(int(limit), 50))
        events = []
        rejected = 0
        scanned = 0; scanned_bytes = 0; scan_limited = False
        root = self.journal.root / 'events'
        if not root.resolve().is_relative_to(self.journal.root):
            raise ValueError('OBSERVATION_DIRECTORY_OUTSIDE_ROOT')
        if root.exists():
            partitions=[]
            for count, partition in enumerate(root.iterdir(),1):
                if count>4096:
                    scan_limited=True
                    break
                try:
                    if (partition.is_symlink() or not partition.resolve().is_relative_to(root.resolve())
                            or not partition.is_dir() or date.fromisoformat(partition.name).isoformat()!=partition.name):
                        raise ValueError('INVALID_EVENT_PARTITION')
                    partitions.append(partition)
                except (OSError,ValueError):
                    rejected+=1
            # Partition dates are scheduling hints, not event-time authority.
            # Within a capped day we cannot promise the latest event without a
            # verified index; UUID names and mtimes must not imply chronology.
            paths=(path for partition in sorted(partitions,key=lambda p:p.name,reverse=True)
                   for path in partition.glob('*.json'))
            for path in paths:
                scanned += 1
                if scanned > 1000: scan_limited = True; break
                try:
                    if not path.resolve().is_relative_to(root.resolve()) or path.stat().st_size > 1024 * 1024:
                        raise ValueError('INVALID_OBSERVATION_FILE')
                    scanned_bytes += path.stat().st_size
                    if scanned_bytes > 16*1024*1024: scan_limited = True; break
                    raw_event = path.read_bytes()
                    event = json.loads(raw_event)
                    if not isinstance(event,dict):raise ValueError('INVALID_OBSERVATION')
                    if event.get('schema') != 'V2_GENERATED_PREVIEW_OBSERVATION_V1':
                        continue
                    if (event.get('event_id') != path.stem or not isinstance(event.get('captures'), list) or not all(isinstance(c,dict) for c in event['captures'])
                            or event.get('generated_not_confirmed_displayed') is not True
                            or event.get('actual_fill_inferred') is not False):
                        raise ValueError('INVALID_OBSERVATION')
                    if decision_id is not None:
                        context = event.get('research_context')
                        if (event.get('decision_id') != decision_id or not isinstance(context, dict)
                                or context.get('research_id') != decision_id[:24]
                                or context.get('research_version') != research_version
                                or context.get('available_cash_exact') != available_cash_exact):
                            continue
                    # Old summary-only records remain readable in unfiltered history only.

                    event.setdefault('source_evidence_missing', not bool(event['captures']))
                    event.setdefault('source_evidence_status', 'LEGACY_SOURCE_EVIDENCE_MISSING')
                    stamp = datetime.fromisoformat(event['observed_at'])
                    if stamp.tzinfo is None:
                        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
                    # This is local historical metadata, not authenticated market
                    # evidence. No prices are fetched and no touch/fill is inferred.
                    events.append((stamp, event, path.relative_to(self.journal.root).as_posix(), raw_event))
                    events.sort(key=lambda pair: pair[0], reverse=True)
                    del events[limit:]
                except (OSError, ValueError, KeyError, TypeError):
                    rejected += 1
        # Only the bounded selected history supplies later captures. Missing history
        # cannot establish NO_TOUCH; this is not an exhaustive market inventory.
        from data.current_quantity_v2_touch_review import review_generated_reference
        files={}; pins={}; total=0
        for _, event, path, raw in events:
            files[path]=raw; pins[path]=sha256(raw).hexdigest(); total+=len(raw)
        for _, event, _, _ in events:
            for capture in event.get('captures',[]):
                try:
                    relative=capture['path']
                    if not isinstance(relative,str) or not re.fullmatch(r'raw/[0-9a-f]{64}\.bin',relative) or relative!='raw/'+capture['sha256']+'.bin':raise ValueError('INVALID_CAPTURE_PATH')
                    path=self.journal.root/relative
                    if relative in files: continue
                    if (Path(relative).is_absolute() or not path.resolve().is_relative_to(self.journal.root)
                            or path.is_symlink() or path.stat().st_size>32*1024*1024):raise ValueError('INVALID_CAPTURE_PATH')
                    if total+path.stat().st_size>HISTORY_SOURCE_BUDGET:raise ValueError('CAPTURE_BUDGET')
                    raw=path.read_bytes()
                    if sha256(raw).hexdigest()!=capture['sha256']:raise ValueError('CAPTURE_CHANGED')
                    total+=len(raw);files[relative]=raw;pins[relative]=capture['sha256']
                except (OSError,ValueError,KeyError,TypeError):
                    rejected+=1
        from data.current_quantity_v2_pullback_chain_source import read_pullback_chain_sources
        chain_sources={};chain_diagnostic='AVAILABLE'
        try:
            chain=read_pullback_chain_sources(repository_root=self.journal.root.parent.parent,event_raws=[r for _,_,_,r in events])
            for name,raw in chain['files'].items():
                if name in files or total+len(raw)>HISTORY_SOURCE_BUDGET:
                    rejected+=1;chain_diagnostic='CHAIN_SOURCE_BUDGET_OR_COLLISION';continue
                if type(raw)is not bytes or sha256(raw).hexdigest()!=chain['source_hashes'].get(name):
                    rejected+=1;chain_diagnostic='CHAIN_SOURCE_INVALID';continue
                files[name]=raw;pins[name]=chain['source_hashes'][name];total+=len(raw)
            chain_sources={h:v for h,v in chain['record_paths'].items() if v['path'] in files and pins.get(v['path'])==v['sha256']}
            if chain['unavailable']:chain_diagnostic='CHAIN_PREFIX_UNAVAILABLE'
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            rejected+=1;chain_diagnostic='CHAIN_SOURCE_UNAVAILABLE_OR_LIMIT'
        for stamp,event,path,raw_event in events:
            later=[p for t,_,p,_ in events if t>stamp]
            event['touch_diagnostic']=review_generated_reference(event_path=path,subsequent_event_paths=later,files=files,source_hashes=pins,trusted_chain_sources=chain_sources)
            if self.followup_reader is not None and decision_id is not None and event.get('status') == 'READY' and event.get('orders'):
                binding=dict(decision_id=decision_id,research_version=research_version,available_cash_exact=available_cash_exact)
                try:
                    followup=self.followup_reader(event_raw=raw_event,binding=binding,now=self.clock())
                    if (not isinstance(followup,dict) or followup.get('binding')!=binding
                            or followup.get('actual_fill_inferred') is not False
                            or followup.get('performance_computed') is not False):
                        raise ValueError('INVALID_FOLLOWUP_RESULT')
                    event['reference_followup']=followup
                except (OSError,ValueError,KeyError,TypeError,ArithmeticError):
                    event['reference_followup']=dict(status='BLOCKED_FOLLOWUP_VALIDATION',binding=binding,
                        actual_fill_inferred=False,performance_computed=False,orders=[])
        return dict(status='OBSERVATION_HISTORY', decision_id=decision_id, research_version=research_version, available_cash_exact=available_cash_exact, observations=[e for _, e, _, _ in events],
                    evidence_scope='LATEST_SELECTED_MAX_50_LOCAL_RECORDS',scan_limited=scan_limited,
                    scan_order='DATE_PARTITION_DESCENDING_THEN_VALIDATED_OBSERVED_AT',
                    scan_coverage='PARTIAL_SCAN' if scan_limited or rejected else 'ALL_DISCOVERED_FILES_SCANNED',
                    latest_records_guaranteed=False,
                    empty_history_proves_no_records=False,
                    rejected_files=rejected, chain_source_diagnostic=chain_diagnostic, source_authenticated=False,
                    actual_fill_inferred=False, future_price_evaluation='NOT_EVALUATED',
                    research_only=True, execution_blocked=True)
