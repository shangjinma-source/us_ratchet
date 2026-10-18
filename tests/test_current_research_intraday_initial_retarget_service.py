from fractions import Fraction
from copy import deepcopy
from datetime import timedelta
from threading import RLock
import tempfile
import unittest
import test_current_research_intraday_retarget_store as fixtures
from data.current_research_intraday_initial_retarget_service import IntradayInitialRetargetService
from data.current_research_intraday_retarget_evidence import freeze_execution_evidence


class InitialRetargetServiceTests(unittest.TestCase):
    def fixture(self, root):
        store, before, proposal, args, _ = fixtures.RetargetStoreTests().fixture(root)
        bundle = dict(sizing_inputs=args['sizing_inputs'], market_session=args['market_session'],
            execution_evidence=freeze_execution_evidence(root=args['root'], sizing_inputs=args['sizing_inputs'], execution_inputs=args['execution_inputs']))
        now=[args['now']]; current=[deepcopy(bundle)]; lock=RLock()
        service=IntradayInitialRetargetService(store=store, evidence_provider=lambda **_:deepcopy(current[0]),
            acceptance_guard=lambda **_:lock, clock=lambda:now[0])
        return service,before,now,current

    def test_accept_preserves_assets_and_retry_needs_no_provider(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,now,current=self.fixture(root)
            p=service.preview(before['account_id'],before['revision'])['proposal']
            accepted=service.accept(before['account_id'],p['proposal_id'],'first-retarget',before['revision'])
            state=service.store.read(before['account_id'])
            for key in ('cash','shares','fees','events','acceptance_id'):self.assertEqual(state[key],before[key])
            self.assertTrue(any(o['side']=='SELL' for o in state['orders'].values()))
            self.assertLessEqual(Fraction(state['reserved_cash']),Fraction(before['cash']))
            retry=IntradayInitialRetargetService(store=service.store,clock=lambda:self.fail('retry clock'))
            self.assertEqual(retry.accept(before['account_id'],p['proposal_id'],'first-retarget',before['revision']),accepted)

    def test_handoff_same_account_to_existing_multiorder_v4(self):
        from data.current_research_intraday_multiorder_service import IntradayMultiorderService
        import test_current_research_intraday_retarget_continuation_chain as chains
        with tempfile.TemporaryDirectory() as root:
            service,before,now,current=self.fixture(root);account=before['account_id']
            p=service.preview(account,before['revision'])['proposal']
            service.accept(account,p['proposal_id'],'initial-retarget',before['revision'])
            state=service.store.read(account)
            for side,kind,extra in [('SELL','FILL',dict(quantity=2,price='1500',fees='1',executed_at=now[0].isoformat())),('BUY','CANCEL',dict(cancelled_at=now[0].isoformat()))]:
                order=next(o for o in state['orders'].values() if o['side']==side)
                state=service.store.record_event(account,dict(event_id='finish-'+side,kind=kind,expected_revision=state['revision'],order_id=order['order_id'],**extra),now=lambda:now[0])
            evidence=deepcopy(service.store.read_retarget_envelope(account)['execution_evidence'])
            for key in ('execution_inputs','units','references'): evidence[key].pop('sndk')
            paths=set(evidence['execution_inputs']['new']['source_hashes'])|set(evidence['units']['new']['source_references'])
            for key in ('files','source_hashes'): evidence[key]={p:v for p,v in evidence[key].items() if p in paths}
            evidence['units']['new'].update(retarget_acceptance_id=state['retarget_acceptance_id'],original_reference_source_hashes=evidence['references']['new']['source_hashes'])
            now[0]+=timedelta(minutes=1)
            evidence=chains.ChainTests().append_quote(evidence,now[0],39,38)
            lock=RLock()
            continuation=IntradayMultiorderService(store=service.store,evidence_provider=lambda **_:deepcopy(evidence),acceptance_guard=lambda **_:lock,clock=lambda:now[0])
            nextp=continuation.preview(account,state['revision'])['proposal']
            continuation.accept(account,nextp['proposal_id'],'continue-v4',state['revision'])
            final=service.store.read(account)
            self.assertEqual(final['schema'],'INTRADAY_RETARGET_CONTINUATION_LEDGER_V4')
            for key in ('cash','shares','fees','events','target_quantities','acceptance_id'):self.assertEqual(final[key],state[key])
            self.assertEqual(final['cash'],'20199')
            self.assertEqual(final['account_id'],account)

    def test_true_v2_continuation_then_first_retarget_preserves_history(self):
        from pathlib import Path
        import test_current_research_intraday_continuation as continuation_fixture
        import test_current_research_intraday_continuation_ledger as continuation_chain
        from test_current_research_intraday_execution import NOW
        from data.current_research_intraday_paper_ledger import _initial
        from data.current_research_intraday_paper_store import IntradayPaperStore
        from data.current_research_intraday_continuation_ledger import build_continuation_proposal, accept_continuation_proposal
        from data.current_research_monthly_retarget_capital import build_monthly_retarget_capital
        from data.current_research_intraday_monthly_selection import build_intraday_monthly_top1_selection
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as journal:
            _,old,continuation_args=continuation_fixture.ContinuationTests().setup(journal)
            store=IntradayPaperStore(Path(root)/'v2-store')
            initial=_initial(old['acceptance'])
            store.accept(old['account_id'],initial['acceptance']['proposal']['proposal_id'],'genesis',lambda:initial)
            for event in old['events']:store.record_event(old['account_id'],event,now=NOW)
            proposal=build_continuation_proposal(old,**continuation_args)
            self.assertEqual(proposal['status'],'READY',proposal)
            frozen_inputs=continuation_chain.ChainTests().inputs(continuation_args)
            v2=store.accept_continuation(old['account_id'],proposal['proposal_id'],'real-v2',old['revision'],
                lambda state:accept_continuation_proposal(state,proposal,operation_id='real-v2',journal_root=journal,current_inputs=frozen_inputs,now=NOW))
            event=continuation_chain.ChainTests().event(v2,event_id='v2-buy',fees='1')
            v2=store.record_event(old['account_id'],event,now=NOW)
            event=continuation_chain.ChainTests().event(v2,'CANCEL','v2-close')
            v2=store.record_event(old['account_id'],event,now=NOW)
            self.assertEqual(v2['schema'],'INTRADAY_CONTINUATION_PAPER_LEDGER_V2')
            self.assertEqual(v2['cash'],'15799');self.assertEqual(v2['shares'],{'sndk':3})
            # Rebuild capital, selection, and unit binding against the real V2 revision.
            service,_,now,current=self.fixture(root)
            bundle=current[0]; inputs=bundle['sizing_inputs']; selection_inputs=inputs['selection_inputs']
            capargs=selection_inputs['capital_inputs'];causal=v2['acceptance']['proposal']['causal_inputs']
            capargs['expected_revision']=v2['revision']
            capargs['initial_capital_identity']=dict(account_id=v2['account_id'],initial_acceptance_id=v2['acceptance_id'],
                initial_proposal_id=v2['acceptance']['proposal']['proposal_id'],initial_research_id=v2['acceptance']['proposal']['research_id'],initial_cash=causal['available_cash'])
            capargs['unit_continuity']['sndk']['initial_event_sha256']=causal['event_sha256']
            selection_inputs['capital']=build_monthly_retarget_capital(v2,**capargs,now=now[0])
            self.assertEqual(selection_inputs['capital']['status'],'READY',selection_inputs['capital'])
            selected=build_intraday_monthly_top1_selection(v2,**selection_inputs,now=now[0])
            self.assertEqual(selected['status'],'READY',selected)
            inputs['selection']=selected
            for unit in inputs['execution_unit_continuity'].values():unit['selection_decision_id']=selected['decision_id']
            bundle['execution_evidence']['units']=deepcopy(inputs['execution_unit_continuity'])
            service.store=store
            preview=service.preview(v2['account_id'],v2['revision'])
            service.accept(v2['account_id'],preview['proposal']['proposal_id'],'v2-first-retarget',v2['revision'])
            after=store.read(v2['account_id'])
            self.assertEqual(after['genesis'],v2)
            for key in ('account_id','cash','shares','fees','events','acceptance','acceptance_id'):self.assertEqual(after[key],v2[key])
            self.assertEqual(after['retarget_acceptance']['sizing_inputs']['selection']['investable_equity'],'20299')
            self.assertEqual(next(o for o in after['orders'].values() if o['side']=='SELL')['quantity'],3)

    def test_changed_expired_and_missing_guard_do_not_write(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,now,current=self.fixture(root);account=before['account_id']
            p=service.preview(account,before['revision'])['proposal']
            current[0]['market_session']['extra']='changed'
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHANGED'):service.accept(account,p['proposal_id'],'changed',before['revision'])
            current[0]['market_session'].pop('extra');now[0]+=timedelta(seconds=121)
            with self.assertRaises(ValueError):service.accept(account,p['proposal_id'],'expired',before['revision'])
            service.acceptance_guard=None
            with self.assertRaisesRegex(ValueError,'GUARD_REQUIRED'):service.accept(account,p['proposal_id'],'unguarded',before['revision'])
            self.assertEqual(service.store.read(account),before)

    def test_corrupt_bytes_or_binding_rejected_and_no_default_provider(self):
        with tempfile.TemporaryDirectory() as root:
            service,before,now,current=self.fixture(root);account=before['account_id']
            current[0]['execution_evidence']['files'][next(iter(current[0]['execution_evidence']['files']))]='YQ=='
            with self.assertRaisesRegex(ValueError,'FROZEN_SOURCE_HASH'):service.preview(account,before['revision'])
            self.assertEqual(service.store.read(account),before)
            disabled=IntradayInitialRetargetService(store=service.store)
            with self.assertRaisesRegex(ValueError,'PROVIDER_UNAVAILABLE'):disabled.preview(account,before['revision'])


if __name__=='__main__':unittest.main()

