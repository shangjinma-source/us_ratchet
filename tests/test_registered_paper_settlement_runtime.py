from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import json
from backtest.registered_paper_settlement_runtime import finalize_registered_paper as finalize
from backtest.current_quantity_v2_simulated_settlement import register_valuation
from backtest.current_quantity_v2_simulation_store import SimulationStore
import test_current_quantity_v2_daily_simulation as fixtures


class FinalSettlementTests(fixtures.DailySimulationTests):
    # Reuse setup helpers only, not its daily-dispatch test cases.
    def setup_final(self,folder,missing=False,days=None):
        args,captures,calls,clock=self.arguments(folder,missing)
        state=fixtures.continuation_fixture.ContinuationSimulationTests.cash_simulation(self)
        day='2026-10-15';days=days or [day]
        state=register_valuation(simulation=state,calendar=dict(session_dates=days,closes={d:d+'T16:00:00-04:00' for d in days},source_references=['synthetic-calendar']),initial_marks={},registered_at=state['chain']['ledger']['acceptance']['accepted_at'])
        store=SimulationStore(Path(folder)/'final.sqlite3');current=store.create(state)
        clock[0]=datetime.fromisoformat(days[-1]+'T16:01:00-04:00')
        result=dict(store=store,simulation_id=args['simulation_id'],account_id=state['origin']['ledger']['account_id'],expected_revision=current['revision'],evaluation_end=days[-1],clock=lambda:clock[0],capture_arguments=args['capture_arguments'],settlement_review=args['settlement_review'],close_arguments=args['close_arguments'])
        return result,captures,calls,clock

    def test_final_registered_day_and_idempotent_no_decisions(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder)
            with patch('backtest.current_quantity_v2_daily_simulation.run_daily',side_effect=AssertionError('no daily decisions')):
                result=finalize(**args)
            self.assertEqual(result['settlement_status'],'FINALIZED_DECLARED_END')
            self.assertEqual(result['simulation']['valuation']['records'][-1]['session'],'2026-10-15')
            self.assertEqual(result['simulation']['valuation']['records'][-1]['status'],'COMPLETE')
            self.assertEqual(calls,[]);self.assertEqual(result['new_decisions'],0)
            before=len(captures)
            args['expected_revision']=result['revision']
            again=finalize(**args)
            self.assertEqual(again['settlement_status'],'ALREADY_FINALIZED');self.assertEqual(len(captures),before)

    def test_unknown_never_expires_or_recaptures(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder,True)
            result=finalize(**args)
            self.assertEqual(result['settlement_status'],'UNKNOWN_UNRESOLVED_ORDERS')
            self.assertTrue(all(not o['closed'] for o in result['simulation']['chain']['ledger']['orders'].values()))
            self.assertEqual(result['simulation']['valuation']['records'],[])
            args['expected_revision']=result['revision'];n=len(captures)
            self.assertEqual(finalize(**args)['settlement_status'],'UNKNOWN_UNRESOLVED_ORDERS')
            self.assertEqual(len(captures),n)

    def test_foreign_account_stale_revision_early_clock_and_unregistered_end(self):
        for mode in ['account','revision','early','future']:
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args,captures,calls,clock=self.setup_final(folder)
                before=args['store'].path.read_bytes()
                if mode=='account':args['account_id']='foreign'
                elif mode=='revision':args['expected_revision']='wrong'
                elif mode=='early':clock[0]=datetime.fromisoformat('2026-10-15T15:59:59-04:00')
                else:args['evaluation_end']='2026-10-16'
                with self.assertRaises(ValueError):finalize(**args)
                self.assertEqual(captures,[]);self.assertEqual(before,args['store'].path.read_bytes())

    def test_missing_close_preserves_settlement_no_fabricated_nav(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder)
            args['close_arguments']=lambda *_:dict(status='MISSING_CLOSE_EVIDENCE',reason='unavailable')
            r=finalize(**args)
            self.assertEqual(r['settlement_status'],'BLOCKED_MISSING_CLOSE_EVIDENCE')
            self.assertEqual(r['simulation']['valuation']['records'],[])
            self.assertTrue(all(o['closed']=='FILLED' for o in r['simulation']['chain']['ledger']['orders'].values()))

    def test_multiple_days_in_registered_order_without_new_decisions(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder,days=['2026-10-15','2026-10-16'])
            original=args['capture_arguments']
            def capture(state,day):
                options=original(state,day);fetch=options['fetch']
                def no_cross(url):
                    raw=json.loads(fetch(url));quote=raw['chart']['result'][0]['indicators']['quote'][0]
                    for key in ('open','high','low','close'):quote[key]=[10000]*len(quote[key])
                    return json.dumps(raw).encode()
                options['fetch']=no_cross;return options
            args['capture_arguments']=capture
            args['close_arguments']=lambda *_:dict(root=folder,captures={},source_hashes={},unit_reviews={})
            r=finalize(**args)
            self.assertEqual(r['settlement_status'],'FINALIZED_DECLARED_END')
            self.assertEqual([x['session'] for x in r['simulation']['valuation']['records']],['2026-10-15','2026-10-16'])
            self.assertTrue(all(o['closed']=='EXPIRED' for o in r['simulation']['chain']['ledger']['orders'].values()))
            self.assertEqual(calls,[])

    def test_registered_future_terminal_close_blocks_all_capture(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder,days=['2026-10-15','2026-10-16'])
            clock[0]=datetime.fromisoformat('2026-10-15T17:00:00-04:00')
            with self.assertRaisesRegex(ValueError,'EVALUATION_END_NOT_CLOSED'):finalize(**args)
            self.assertEqual(captures,[])
            self.assertEqual(args['store'].read(args['simulation_id'])['simulation']['valuation']['records'],[])

    def test_post_write_failure_preserves_store_for_explicit_readback(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder)
            original=args['store'].apply
            def apply(**kwargs):
                result=original(**kwargs)
                if ':daily-close:' in kwargs['operation_id']:raise OSError('after commit')
                return result
            with patch.object(args['store'],'apply',side_effect=apply):
                with self.assertRaises(OSError):finalize(**args)
            current=args['store'].read(args['simulation_id'])
            self.assertEqual(current['simulation']['valuation']['records'][-1]['status'],'COMPLETE')
            args['expected_revision']=current['revision']
            self.assertEqual(finalize(**args)['settlement_status'],'ALREADY_FINALIZED')

    def test_capture_then_clock_rollback_keeps_evidence_without_commit(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder)
            original=args['settlement_review']
            def review(state,prepared):
                result=original(state,prepared)
                clock[0]=datetime.fromisoformat('2026-10-15T16:00:59-04:00')
                return result
            args['settlement_review']=review
            before=args['store'].read(args['simulation_id'])
            with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):finalize(**args)
            self.assertTrue(captures)
            self.assertEqual(args['store'].read(args['simulation_id']),before)

    def test_capture_then_other_valid_writer_causes_cas_rejection(self):
        from backtest.current_quantity_v2_daily_settlement_simulation import apply_daily_settlement
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.setup_final(folder)
            original=args['settlement_review'];committed=[]
            def review(state,prepared):
                result=original(state,prepared)
                committed.append(apply_daily_settlement(store=args['store'],prepared=prepared,
                    evaluated_at=clock[0].isoformat(),**result))
                return result
            args['settlement_review']=review
            with self.assertRaisesRegex(ValueError,'STALE_SIMULATION_REVISION'):finalize(**args)
            self.assertTrue(captures)
            self.assertEqual(args['store'].read(args['simulation_id'])['simulation'],committed[0]['simulation'])
            self.assertEqual(committed[0]['simulation']['valuation']['records'],[])


# Avoid inheriting unrelated dispatcher tests while retaining its fixture setup.
for name in list(vars(fixtures.DailySimulationTests)):
    if name.startswith('test_'):setattr(FinalSettlementTests,name,None)
if __name__=='__main__':unittest.main()

