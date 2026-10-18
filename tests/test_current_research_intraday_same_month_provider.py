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


import json
from unittest.mock import Mock
from data.current_research_intraday_same_month_provider import SameMonthJournalEvidenceProvider


def provider_fixture(root, retain_held=False):
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
    envelope = accept_retarget_with_execution_evidence(state, proposal, root=root, sizing_inputs=sizing,
        execution_inputs=execution_inputs, market_session=original['selection_inputs']['capital_inputs']['market_session'],
        operation_id='journal-initial-retarget', now=clock[0])
    for side, kind, values in [('SELL','CANCEL' if retain_held else 'FILL',dict(cancelled_at=clock[0].isoformat()) if retain_held else dict(quantity=2, price='1500', fees='0', executed_at=clock[0].isoformat())),
                               ('BUY','CANCEL',dict(cancelled_at=clock[0].isoformat()))]:
        ledger = envelope['ledger']; order = next(o for o in ledger['orders'].values() if o['side'] == side)
        event = dict(event_id='journal-'+side, kind=kind, expected_revision=ledger['revision'],
            order_id=order['order_id'], recorded_at=clock[0].isoformat(), **values)
        envelope['ledger'] = apply_retarget_event(ledger, event, now=clock[0])
    review_source_verified_retarget(envelope)

    # A fresh genuine observation follows the last recorded manual event.
    clock[0] += timedelta(seconds=20)
    for sid, service in services.items():
        raw=quotes[sid]['chart']['result'][0]
        raw['meta']['regularMarketTime']=int(clock[0].timestamp())
        service.preview(bindings[sid]['research_id'])
    def current(rid):
        sid=next(s for s,b in bindings.items() if b['research_id']==rid)
        return services[sid].current_reference(rid)
    def receipt(binding, authority):
        return caps.read_scope_evidence(journal, **{k:binding[k] for k in ('research_id','security_id','ticker','session')},
            current_event_id=authority['current_receipt']['event_id'])
    def unit_review(**kwargs):
        result={}
        for sid, ref in kwargs['references'].items():
            unit=deepcopy(units[sid])
            unit.update(retarget_acceptance_id=envelope['ledger']['retarget_acceptance_id'],
                original_reference_source_hashes=references[sid]['source_hashes'],reference_source_hashes=ref['source_hashes'],
                covered_through=clock[0].isoformat(),reviewed_asof=clock[0].isoformat())
            result[sid]=unit
        raw=(root/'units.json').read_bytes()
        return dict(units=result,source_hashes={'units.json':sha256(raw).hexdigest()},files={'units.json':raw})
    provider=SameMonthJournalEvidenceProvider(current_reference_reader=current,
        binding_resolver=lambda **k:deepcopy(bindings[k['security_id']]),receipt_reader=receipt,
        unit_review_resolver=unit_review)
    return provider,envelope,clock,services,bindings


class ProviderTests(unittest.TestCase):
    def call(self, provider, envelope, clock):
        return provider(account_id=envelope['ledger']['account_id'],payload=envelope,now=clock[0])

    def test_real_journal_prior_history_and_readonly_stable_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            p,e,c,services,_=provider_fixture(Path(directory))
            before=deepcopy(e)
            for service in services.values(): service.fetch=Mock(side_effect=AssertionError('NO_HTTP'))
            evidence=self.call(p,e,c)
            self.assertEqual(set(evidence['references']),{'new'})
            self.assertEqual(replay_execution_evidence(evidence),evidence['references'])
            self.assertEqual(self.call(p,e,c),evidence)
            result=build_retarget_chain_proposal(e,expected_revision=e['ledger']['revision'],execution_evidence=evidence,now=c[0])
            self.assertEqual(result['status'],'READY',result)
            self.assertEqual(result['actual_cash'],'20200')
            self.assertEqual(result['unfilled_sell_proceeds_available'],'0')
            self.assertEqual(e,before)

    def test_complete_held_target_union_missing_unit_and_mapping_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            p,e,c,_,_=provider_fixture(Path(directory),retain_held=True)
            evidence=self.call(p,e,c)
            self.assertEqual(set(evidence['references']),{'sndk','new'})
            original=p.units
            p.units=lambda **k:dict(original(**k),units={})
            with self.assertRaisesRegex(ValueError,'COMPLETE_UNIT'):self.call(p,e,c)
            p.units=original
            binding=p.binding
            p.binding=lambda **k:dict(binding(**k),account_id='OTHER')
            with self.assertRaisesRegex(ValueError,'SERVER_BINDING'):self.call(p,e,c)

    def test_no_review_pin_conflict_and_late_authority_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            p,e,c,_,_=provider_fixture(Path(directory))
            original=p.units
            p.units=lambda **k:None
            with self.assertRaisesRegex(ValueError,'UNIT_REVIEW_REQUIRED'):self.call(p,e,c)
            def conflicting(**k):
                result=original(**k);raw=b'changed unit bytes'
                result['files']['units.json']=raw;result['source_hashes']['units.json']=sha256(raw).hexdigest()
                return result
            p.units=conflicting
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN_CONFLICT'):self.call(p,e,c)
            current=p.current
            def moved(**k):
                result=original(**k);p.current=lambda rid:dict(current(rid),status='PENDING')
                return result
            p.units=moved
            with self.assertRaisesRegex(ValueError,'CURRENT_AUTHORITY_CHANGED'):self.call(p,e,c)

    def test_failed_current_and_cross_month_reject_before_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            p,e,c,_,_=provider_fixture(Path(directory))
            p.receipts=Mock(side_effect=AssertionError('NO_COLLECT'))
            p.current=lambda rid:dict(status='UNAVAILABLE')
            with self.assertRaisesRegex(ValueError,'CURRENT_REFERENCE_UNAVAILABLE'):self.call(p,e,c)
            c[0]=c[0].replace(month=12)
            with self.assertRaisesRegex(ValueError,'RESELECT_REQUIRED'):self.call(p,e,c)
            p.receipts.assert_not_called()


if __name__=='__main__':unittest.main()
