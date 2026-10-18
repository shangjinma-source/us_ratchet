"""Server-injected, read-only SAME_MONTH journal evidence provider.

Resolvers are trusted server configuration, never request payloads. Unit reviews
remain explicit reviewed declarations; byte integrity does not certify complete
corporate actions or external timestamps. No default instance, fetch or writes.
"""
import base64
from copy import deepcopy
from hashlib import sha256
from zoneinfo import ZoneInfo

from data.current_research_intraday_buy_plan import _require, _time
from data.current_research_intraday_journal_reference import read_journal_execution_reference
from data.current_research_intraday_retarget_evidence import JOURNAL_SOURCE, _path, _needed, replay_execution_evidence
from data.current_research_intraday_retarget_continuation_chain import (
    review_retarget_continuation_chain, build_retarget_chain_proposal)


class SameMonthJournalEvidenceProvider:
    """Callables: current_reference_reader(rid); receipt_reader(binding, authority).

    binding_resolver receives account_id,target_month,security_id,ticker,session.
    unit_review_resolver receives account_id,payload,session,references,now and
    returns {units, source_hashes, files}, with original bytes in files. Missing
    reviews are errors; this class never manufactures an action declaration.
    receipt_reader wraps cap_store.read_scope_evidence with its server journal.
    """
    def __init__(self, *, current_reference_reader, binding_resolver,
                 receipt_reader, unit_review_resolver):
        for value in (current_reference_reader, binding_resolver, receipt_reader, unit_review_resolver):
            _require(callable(value), 'SERVER_RESOLVER_REQUIRED')
        self.current = current_reference_reader
        self.binding = binding_resolver
        self.receipts = receipt_reader
        self.units = unit_review_resolver

    def __call__(self, *, account_id, payload, now):
        original = deepcopy(payload)
        chain = review_retarget_continuation_chain(original)
        state = chain['ledger']; now = _time(now)
        _require(state['account_id'] == account_id, 'ACCOUNT_BINDING_MISMATCH')
        month = state['retarget_acceptance']['proposal']['binding']['selection']['target_month']
        session = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        _require(session[:7] == month, 'RESELECT_REQUIRED')
        _require(all(o['closed'] for o in state['orders'].values()), 'OPEN_ORDERS_OR_RESERVES')
        domain = {sid for sid, qty in state['shares'].items() if qty > 0}
        domain |= {sid for sid, qty in state['target_quantities'].items() if qty > 0}
        previous = chain['latest_execution_evidence']
        files = {}; pins = {}; total = 0

        def merge(source_files, source_pins):
            nonlocal total
            _require(isinstance(source_files, dict) and isinstance(source_pins, dict)
                     and set(source_files) == set(source_pins), 'SOURCE_BYTE_DOMAIN_MISMATCH')
            for name, raw in source_files.items():
                _path(name)
                _require(isinstance(raw, bytes) and len(raw) <= 32 * 1024 * 1024, 'SOURCE_SIZE_OR_TYPE')
                digest = sha256(raw).hexdigest()
                _require(source_pins[name] == digest, 'SOURCE_HASH_MISMATCH')
                _require(name not in pins or (pins[name] == digest and files[name] == raw), 'SOURCE_PIN_CONFLICT')
                if name not in files:
                    total += len(raw)
                    _require(total <= 128 * 1024 * 1024, 'SOURCE_TOTAL_TOO_LARGE')
                    files[name] = raw; pins[name] = digest

        # Prior bytes have already been authenticated by full ledger replay.
        merge({name: base64.b64decode(value, validate=True) for name, value in previous['files'].items()},
              previous['source_hashes'])
        references = {}; inputs = {}; authorities = {}
        original_refs = state['retarget_acceptance']['sizing_inputs']['execution_references']
        for sid in sorted(domain):
            _require(sid in original_refs, 'SECURITY_IDENTITY_CHANGED')
            ticker = original_refs[sid]['ticker']
            expected = dict(account_id=account_id, target_month=month, security_id=sid, ticker=ticker, session=session)
            binding = self.binding(**expected)
            _require(isinstance(binding, dict) and set(binding) == set(expected) | {'research_id'}
                     and all(binding[k] == value for k, value in expected.items()), 'SERVER_BINDING_MISMATCH')
            authority = deepcopy(self.current(binding['research_id']))
            _require(isinstance(authority, dict) and authority.get('status') == 'AVAILABLE', 'CURRENT_REFERENCE_UNAVAILABLE')
            closure = self.receipts(deepcopy(binding), deepcopy(authority))
            scope = {key: binding[key] for key in ('research_id', 'security_id', 'ticker', 'session')}
            _require(isinstance(closure, dict) and closure.get('scope') == scope
                     and closure.get('current_receipt') == authority.get('current_receipt'), 'OUTBOX_SCOPE_OR_RECEIPT_MISMATCH')
            current_files = closure['frozen_files']
            merge(current_files, {name: sha256(raw).hexdigest() for name, raw in current_files.items()})
            # Hashes here index verified original outbox bytes, not external truth.
            hashes = deepcopy(closure['event_hashes'])
            prior = previous['execution_inputs'].get(sid)
            if prior is not None and previous['references'][sid]['session'] == session:
                _require(prior.get('source_kind') == JOURNAL_SOURCE, 'SAME_SESSION_SOURCE_KIND_CHANGED')
                for name, digest in prior['event_hashes'].items():
                    _require(name not in hashes or hashes[name] == digest, 'SOURCE_PIN_CONFLICT')
                    hashes[name] = digest
            reference = read_journal_execution_reference(root='.', binding=binding,
                current_reference=authority, event_hashes=hashes, now=now,
                frozen_files=files, current_reference_reader=self.current)
            references[sid] = reference
            authorities[binding['research_id']] = authority
            inputs[sid] = dict(source_kind=JOURNAL_SOURCE, binding=deepcopy(binding),
                current_reference=authority, event_hashes=hashes,
                source_hashes=deepcopy(reference['source_hashes']), security_id=sid)

        if domain:
            reviewed = self.units(account_id=account_id, payload=deepcopy(original), session=session,
                                  references=deepcopy(references), now=now)
            _require(isinstance(reviewed, dict) and set(reviewed) == {'units', 'source_hashes', 'files'}, 'UNIT_REVIEW_REQUIRED')
            units = deepcopy(reviewed['units'])
            _require(set(units) == domain, 'COMPLETE_UNIT_REVIEW_DOMAIN_REQUIRED')
            merge(reviewed['files'], reviewed['source_hashes'])
            required = _needed(inputs, units, pins)
            evidence = dict(execution_inputs=inputs, units=units, source_hashes=required,
                files={name: base64.b64encode(files[name]).decode('ascii') for name in required}, references=references)
            replay_execution_evidence(evidence)
        else:
            evidence = dict(execution_inputs={}, units={}, source_hashes={}, files={}, references={})
        proposal = build_retarget_chain_proposal(original, expected_revision=state['revision'],
                                                execution_evidence=evidence, now=now)
        _require(proposal['status'] == 'READY', 'CONTINUATION_EVIDENCE_REJECTED:' + str(proposal.get('reason')))
        for rid, authority in authorities.items():
            _require(self.current(rid) == authority, 'CURRENT_AUTHORITY_CHANGED')
        return evidence
