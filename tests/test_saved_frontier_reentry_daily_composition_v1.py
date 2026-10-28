"""Offline source/risk/provider integration of the explicit monthly proposal gate."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data.saved_frontier_reentry_daily_composition_v1 import SavedFrontierReentryDailyComposition
from data.monthly_peak_exit_reentry_store_v1 import MonthlyPeakExitReentryStore
from data.strategy_observed_reentry_daily_admission_v1 import ObservedReentryDailyAdmission
from core.strategy_account_ledger import canonical
from hashlib import sha256
from data.saved_frontier_cap_exit_reader import POLICY_ID, project_saved_frontier_cap_exit, clone_monthly_risk_store
from data.saved_frontier_policy_archive import archive_saved_frontier_policy
import test_saved_frontier_isolated_pipeline as fixture


class ReentryCompositionTests(unittest.TestCase):
    def run_case(self, cash, buy_data_missing=False):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmp') as directory:
            case = fixture.IsolatedFrontierPipelineTests().case(directory, cash=cash, cancel=True)
            archive_saved_frontier_policy(research_root=case['root'], target=case['target'],
                proposal=case['proposal'], source_files=case['source_files'], enabled=True)
            original = deepcopy(case['target'])
            risk_path = clone_monthly_risk_store(research_root=case['root'],
                source_path=case['risk_path'], source_sha256=fixture.digest(case['risk_path'].read_bytes()),
                clone_name='composition-risk.sqlite3')['path']
            saved_evidence=project_saved_frontier_cap_exit(research_root=case['root'],risk_path=risk_path,
                target_id=case['target']['target_id'],state=case['accounts'].read(),review_bytes=case['review_bytes'],
                trusted_review_sha256=case['trusted_review_sha256'],files=case['files'],now=case['clock'][0].isoformat(),enabled=True)
            risk_store=MonthlyPeakExitReentryStore(risk_path)
            config=canonical(dict(schema='SERVER_REENTRY_COMPOSITION_CONFIG_V1',reference_sources={}))
            risk_store.activate_reference(account_id=case['accounts'].read()['account_id'],activation_id='a'*64,
                activation_at=case['clock'][0].isoformat(),activation_session=case['clock'][0].date().isoformat(),
                account_revision=case['accounts'].read()['revision'],source_configuration_sha256=sha256(config).hexdigest())
            account_bytes = case['accounts'].path.read_bytes()
            monthly = SimpleNamespace(accounts=case['accounts'], current=lambda: dict(deepcopy(case['target']),proposal_id=case['proposal']['proposal_id']),
                snapshot_operation=nullcontext, validate_current_target_pins=lambda: None)
            def proposal(**arguments):
                self.assertEqual(arguments['expected_proposal_id'], case['proposal']['proposal_id'])
                return deepcopy(case['proposal'])
            def reader(state, target, now, *, proposal):
                self.assertEqual({k:v for k,v in target.items() if k!='proposal_id'}, original)
                return deepcopy(saved_evidence) # Already authenticated saved evidence; live-reader chain has its own real integration suite.
            service = SavedFrontierReentryDailyComposition(root=case['root'],risk_store=risk_store,configuration_reader=lambda:config,monthly_service=monthly,
                monthly_view=SimpleNamespace(require_proposal=proposal), evidence_reader=reader,
                execution_provider=case['provider'].execution, clock=lambda: case['clock'][0],
                policy_execution_enabled=True, policy_id=POLICY_ID, fee_bps='1')
            # Real observer around the real original provider/composition. Journal IO
            # is an inert test seam; financial source/provider/SQLite remain real.
            service=ObservedReentryDailyAdmission(service=service,monthly=monthly,
                journal=SimpleNamespace(append=lambda *a,**k:None,record_return=lambda *a,**k:None),
                clock=lambda:case['clock'][0],validate_sources=lambda:None,policy_references={},
                reference_store=risk_store,configuration_reader=lambda:sha256(config).hexdigest())
            with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
                 patch('data.strategy_account_evidence_provider.compile_saved_training',
                       side_effect=AssertionError('NEW_TRAINING_FORBIDDEN')), \
                 (patch('data.saved_frontier_daily_composition_v1.SavedFrontierPreviewService.preview',
                        side_effect=ValueError('MINUTE_GAP')) if buy_data_missing else nullcontext()):
                result = service.preview(expected_revision=case['accounts'].read()['revision'],
                    target_id=original['target_id'], expected_proposal_id=case['proposal']['proposal_id'])
            self.assertEqual(result['proposal_id'], case['proposal']['proposal_id'])
            self.assertEqual(original, case['target'])
            self.assertEqual(account_bytes, case['accounts'].path.read_bytes())
            self.assertTrue(result['risk_valid_until'])
            self.assertEqual(result['status'], 'READY',result)
            self.assertEqual(result['policy_id'],'SAVED_FRONTIER_CAP50_EXIT20_REENTRY_V1')
            self.assertEqual(len(result['reference_projection']),6)
            self.assertNotIn('reentry_commit_context',str(result))
            self.assertTrue(result['new_orders'])
            for order in result['new_orders']:
                self.assertEqual(order['proposal_id'], case['proposal']['proposal_id'])
            return result

    def test_positive_cash_real_execution_bridge(self):
        self.run_case('20000')

    def test_zero_cash_real_sell_only_bridge(self):
        result = self.run_case('0')
        self.assertTrue(all(order['side'] == 'SELL' for order in result['new_orders']))

    def test_buy_data_missing_preserves_real_sell_bridge(self):
        result = self.run_case('20000', buy_data_missing=True)
        self.assertEqual(result['buy_data_failure'], 'MINUTE_GAP')
        self.assertTrue(all(order['side'] == 'SELL' for order in result['new_orders']))


class ConditionalReferenceCompositionTests(unittest.TestCase):
    """Real source/store/ledger; original-preview acquisition is the explicit seam.
    The preceding class independently exercises the actual original provider.
    """
    def exercise(self,mode='locked',tamper=False):
        import test_reentry_cross_layer_v1 as cross
        from data.current_quantity_v2_paper_action_sources import stamp
        from data import saved_frontier_reentry_daily_composition_v1 as module
        fixture_case=cross.CrossLayerTests();fixture_case.setUp();self.addCleanup(fixture_case.doCleanups)
        c=fixture_case;source=c.prepare(True) # Observed intermediate recovery still not closed identity authority.
        projected,difference=c.preview()
        now='2026-11-03T22:00:00Z'
        original=dict(status='READY',policy_id=POLICY_ID,account_revision=c.state['revision'],target_id='target',proposal_id='original',
            risk_valid_from=now,risk_valid_until='2026-11-03T22:01:00Z',effective_target_quantities={'A':4,'B':4,'C':1},
            reference_quotes=deepcopy(difference['binding']['limits']),difference=difference,new_orders=difference['new_orders'])
        if mode in {'HOLD','WAIT'}:original.update(status=mode,new_orders=[],reference_quotes={},difference={})
        config=canonical(dict(schema='SERVER_REENTRY_COMPOSITION_CONFIG_V1',reference_sources={'A':source}))
        target=dict(target_id='target',proposal_id='original',payload=dict(target_month='2026-11'))
        proposal=dict(proposal_id='original')
        monthly=SimpleNamespace(accounts=c.account,current=lambda:deepcopy(target),snapshot_operation=nullcontext,validate_current_target_pins=lambda:None)
        service=SavedFrontierReentryDailyComposition(root=c.root,risk_store=c.risk,configuration_reader=lambda:config,
            monthly_service=monthly,monthly_view=SimpleNamespace(require_proposal=lambda **kw:deepcopy(proposal)),
            evidence_reader=lambda *a,**kw:None,execution_provider=None,clock=lambda:stamp(now))
        observer=ObservedReentryDailyAdmission(service=service,monthly=monthly,journal=SimpleNamespace(append=lambda *a,**kw:None,record_return=lambda *a,**kw:None),
            clock=lambda:stamp(now),validate_sources=lambda:None,policy_references={},reference_store=c.risk,configuration_reader=lambda:sha256(config).hexdigest())
        before=c.risk.read_reference('synthetic');account_before=c.account.path.read_bytes()
        realformat=module.format_reference_advice
        def formatting(**kw):
            answer=realformat(**kw)
            if tamper:(c.root/'daily.json').write_bytes(b'tampered after source review')
            return answer
        with patch.object(module.SavedFrontierDailyComposition,'preview',return_value=original),patch.object(module,'format_reference_advice',side_effect=formatting):
            run=lambda:observer.preview(expected_revision=c.state['revision'],target_id='target',expected_proposal_id='original')
            if tamper:
                with self.assertRaisesRegex(ValueError,'REFERENCE_SOURCE_CHANGED'):run()
                return
            answer=run();again=run()
        self.assertEqual(c.risk.read_reference('synthetic'),before)
        self.assertEqual(c.account.path.read_bytes(),account_before)
        self.assertNotIn('context',str(answer.get('reference_projection',{})))
        if mode=='locked':
            self.assertEqual(answer['status'],'READY',answer)
            self.assertEqual(answer['new_orders'],[o for o in original['new_orders'] if o['side']=='SELL'])
            self.assertEqual(set(answer['reference_projection']['buy_status'].values()),{'WAIT_REFERENCE'})
            self.assertEqual(answer['reference_projection'],again['reference_projection'])
        else:self.assertEqual(answer['status'],mode,answer)
    def test_conditional_recovery_cannot_unlock_and_repeat_is_stable(self):self.exercise()
    def test_source_mutation_after_review_rejected(self):self.exercise(tamper=True)
    def test_hold_preserved_through_real_observer(self):self.exercise('HOLD')
    def test_wait_preserved_through_real_observer(self):self.exercise('WAIT')

if __name__ == '__main__':
    unittest.main()
