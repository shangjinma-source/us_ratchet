from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from test_current_research_intraday_journal_reference import fixture
import test_current_research_intraday_retarget_sources as retarget_sources
from test_current_research_intraday_execution import snapshot
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_journal_reference import read_journal_execution_reference
from data.current_research_intraday_retarget_evidence import (
    freeze_execution_evidence, replay_execution_evidence, read_execution_evidence_reference,
    accept_retarget_with_execution_evidence, review_source_verified_retarget)
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing
from data.current_research_intraday_retarget_ledger import apply_retarget_event
from data.current_research_intraday_retarget_continuation_chain import (
    build_retarget_chain_proposal, accept_retarget_chain_proposal, review_retarget_continuation_chain)
from data.current_research_intraday_retarget_continuation import _same_session_source_history


def execution_input(binding, authority, hashes, reference):
    return dict(source_kind='INTRADAY_JOURNAL_OBSERVATION_V1', binding=deepcopy(binding),
                current_reference=deepcopy(authority), event_hashes=deepcopy(hashes),
                source_hashes=deepcopy(reference['source_hashes']), security_id=binding['security_id'])


class JournalEvidenceTests(unittest.TestCase):
    def test_pending_original_capture_freezes_and_replays_after_files_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            value = fixture(directory, pending=True)
            root = value['root']; reference = value['reference']
            (root / 'units.json').write_bytes(b'{"synthetic_unit_review":true}')
            pins = dict(reference['source_hashes'], **{'units.json': sha256((root/'units.json').read_bytes()).hexdigest()})
            arguments = execution_input(value['binding'], value['current_reference'], value['event_hashes'], reference)
            inputs = dict(execution_references={'sndk': reference},
                execution_unit_continuity={'sndk': {'source_references': ['units.json']}}, source_hashes=pins)
            evidence = freeze_execution_evidence(root=root, sizing_inputs=inputs, execution_inputs={'sndk': arguments})
            self.assertEqual(read_execution_evidence_reference(root=root, arguments=arguments, now=value['now']), reference)
        self.assertEqual(replay_execution_evidence(evidence), {'sndk': reference})
        self.assertLess(reference['captured_at'], reference['last_at'])
        altered = deepcopy(evidence); altered['references']['sndk']['replay_at'] = reference['valid_until']
        with self.assertRaises(ValueError): replay_execution_evidence(altered)
        altered = deepcopy(evidence); altered['execution_inputs']['sndk']['source_kind'] = 'UNKNOWN'
        with self.assertRaisesRegex(ValueError, 'JOURNAL_EXECUTION_INPUT_SCHEMA'): replay_execution_evidence(altered)

    def test_original_journal_to_v3_and_same_month_v4_preserves_cap_and_cash(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, original = retarget_sources.RetargetSourcesTests().fixture(root)
            clock = [original['now']]
            journal = IntradayObservationJournal(root)
            caps = PersistentIntradayCapStore(root/'caps.sqlite3')
            services = {}; bindings = {}; quotes = {}; receipts = {}
            for index, (sid, ticker) in enumerate([('sndk', 'SNDK'), ('new', 'NEW')]):
                rid = str(index+1)*24
                quotes[sid] = json.loads((root/(sid+'.raw.json')).read_bytes())
                if sid == 'new':
                    quotes[sid]['chart']['result'][0]['meta']['regularMarketTime'] += 7
                snap = snapshot(rid)
                snap.update(research_id=rid, selected_security=dict(security_id=sid, ticker=ticker),
                    selected_ranking_security_id=sid, stocks=[dict(security_id=sid, ticker=ticker, units=1, close=40)])
                service = IntradayExecutionService(snapshot_reader=lambda _, s=snap: deepcopy(s),
                    fetch=lambda _, s=sid: deepcopy(quotes[s]), clock=lambda: clock[0], journal=journal, cap_store=caps)
                services[sid] = service
                receipt = service.preview(rid)['observation_record']
                receipts[receipt['event_path']] = receipt['event_sha256']
                bindings[sid] = dict(account_id=state['account_id'], target_month='2026-11',
                    research_id=rid, security_id=sid, ticker=ticker, session='2026-11-02')
            clock[0] += timedelta(seconds=8)
            quotes['new']['chart']['result'][0]['meta']['regularMarketTime'] += 8
            receipt = services['new'].preview(bindings['new']['research_id'])['observation_record']
            receipts[receipt['event_path']] = receipt['event_sha256']
            references = {}; execution_inputs = {}; units = deepcopy(original['execution_unit_continuity'])
            pins = dict(original['source_hashes'])
            for sid, binding in bindings.items():
                authority = services[sid].current_reference(binding['research_id'])
                reference = read_journal_execution_reference(root=root, binding=binding, current_reference=authority,
                    event_hashes=receipts, now=clock[0])
                references[sid] = reference; pins.update(reference['source_hashes'])
                units[sid]['reference_source_hashes'] = reference['source_hashes']
                units[sid].update(covered_through=clock[0].isoformat(), reviewed_asof=clock[0].isoformat())
                execution_inputs[sid] = execution_input(binding, authority, receipts, reference)
            sizing = dict(selection=original['selection'], selection_inputs=original['selection_inputs'],
                execution_references=references, execution_unit_continuity=units, source_hashes=pins)
            proposal = build_intraday_retarget_sizing(state, **sizing, now=clock[0])
            self.assertEqual(proposal['status'], 'READY', proposal)
            self.assertLess(references['new']['captured_at'], references['new']['last_at'])
            envelope = accept_retarget_with_execution_evidence(state, proposal, root=root, sizing_inputs=sizing,
                execution_inputs=execution_inputs, market_session=original['selection_inputs']['capital_inputs']['market_session'],
                operation_id='journal-initial-retarget', now=clock[0])
            for side, kind, values in [('SELL','FILL',dict(quantity=2, price='1500', fees='0', executed_at=clock[0].isoformat())),
                                       ('BUY','CANCEL',dict(cancelled_at=clock[0].isoformat()))]:
                ledger = envelope['ledger']; order = next(o for o in ledger['orders'].values() if o['side'] == side)
                event = dict(event_id='journal-'+side, kind=kind, expected_revision=ledger['revision'],
                    order_id=order['order_id'], recorded_at=clock[0].isoformat(), **values)
                envelope['ledger'] = apply_retarget_event(ledger, event, now=clock[0])
            review_source_verified_retarget(envelope)
            clock[0] += timedelta(minutes=1)
            raw = quotes['new']['chart']['result'][0]; raw['meta']['regularMarketTime'] = int(clock[0].timestamp())
            raw['meta']['regularMarketPrice'] += 10
            raw['timestamp'] = [stamp+60 for stamp in raw['timestamp']]
            for key in ('open','high','low','close'): raw['indicators']['quote'][0][key][0] += 10
            receipt = services['new'].preview(bindings['new']['research_id'])['observation_record']
            receipts[receipt['event_path']] = receipt['event_sha256']
            authority = services['new'].current_reference(bindings['new']['research_id'])
            reference = read_journal_execution_reference(root=root, binding=bindings['new'], current_reference=authority,
                event_hashes=receipts, now=clock[0])
            self.assertEqual(reference['buy_limit'], references['new']['buy_limit'])
            unit = deepcopy(units['new'])
            unit.update(retarget_acceptance_id=envelope['ledger']['retarget_acceptance_id'],
                original_reference_source_hashes=references['new']['source_hashes'],
                reference_source_hashes=reference['source_hashes'], covered_through=clock[0].isoformat(), reviewed_asof=clock[0].isoformat())
            new_input = execution_input(bindings['new'], authority, receipts, reference)
            evidence = freeze_execution_evidence(root=root, execution_inputs={'new':new_input},
                sizing_inputs=dict(execution_references={'new':reference}, execution_unit_continuity={'new':unit},
                    source_hashes=dict(reference['source_hashes'], **{'units.json': pins['units.json']})))
            ledger = envelope['ledger']
            continuation = build_retarget_chain_proposal(envelope, expected_revision=ledger['revision'], execution_evidence=evidence, now=clock[0])
            self.assertEqual(continuation['status'], 'READY', continuation)
            chain = accept_retarget_chain_proposal(envelope, continuation, operation_id='journal-continue',
                expected_revision=ledger['revision'], execution_evidence=evidence, now=clock[0])
            self.assertEqual(chain['ledger']['cash'], '20200')
            self.assertEqual(chain['ledger']['target_quantities'], proposal['target_quantities'])
            bad_input = deepcopy(new_input); bad_input['current_reference']['attempt_token'] = 0
            with self.assertRaisesRegex(ValueError, 'MOVED_BACKWARD'):
                _same_session_source_history(execution_inputs['new'],bad_input,references['new'],reference)
            bad_input = deepcopy(new_input); bad_input['event_hashes'].pop(next(iter(receipts)))
            with self.assertRaisesRegex(ValueError, 'HISTORY_REMOVED'):
                _same_session_source_history(execution_inputs['new'],bad_input,references['new'],reference)
        self.assertEqual(review_retarget_continuation_chain(chain), chain)


if __name__ == '__main__': unittest.main()
