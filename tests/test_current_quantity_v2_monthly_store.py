from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import unittest
from test_current_quantity_v2_monthly_retarget import fixture
from data.current_quantity_v2_monthly_retarget import build_monthly_retarget
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from data.current_quantity_v2_paper_service import compact
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge

class MonthlyStoreTests(unittest.TestCase):
    def setup(self,folder):
        state,args,at=fixture();store=QuantityV2PaperStore(Path(folder)/'paper.sqlite3')
        with store.transaction(create=True) as db:store.save(db,state['ledger']['account_id'],state)
        proposal=build_monthly_retarget(state,proposal_inputs=args,now=at);calls=[]
        def factory(current,now):
            self.assertEqual(current,state);calls.append(now);return deepcopy(proposal)
        request=dict(account_id=state['ledger']['account_id'],proposal_id=proposal['proposal_id'],operation_id='monthly',
            expected_revision=state['ledger']['revision'],factory=factory,clock=lambda:datetime.fromisoformat(at))
        return store,state,args,proposal,request,calls
    def test_concurrent_accept_retry_latest_compact_and_active_source(self):
        with TemporaryDirectory() as folder:
            store,state,args,p,request,calls=self.setup(folder)
            with ThreadPoolExecutor(2) as pool:result=list(pool.map(lambda _:store.accept_monthly_retarget(**request),range(2)))
            self.assertEqual(result[0],result[1]);self.assertEqual(len(calls),1)
            current=result[0]
            for key in ('cash','shares','recorded_fees','events'):self.assertEqual(current['ledger'][key],state['ledger'][key])
            view=compact(current);self.assertEqual(view['capital_decision_id'],p['capital_decision_id']);self.assertEqual(view['target_month'],'2026-11')
            self.assertEqual(view['initial_capital_decision_id'],compact(state)['capital_decision_id'])
            order=next(iter(current['ledger']['orders'].values()))
            event=dict(event_id='cancel',type='CANCEL',order_id=order['order_id'],expected_revision=current['ledger']['revision'],cancelled_at=args['now'])
            latest=store.record_event(account_id=request['account_id'],event=event,clock=request['clock'])
            retry=dict(request,factory=lambda *_:self.fail('retry source'),clock=lambda:self.fail('retry clock'))
            self.assertEqual(QuantityV2PaperStore(store.path).accept_monthly_retarget(**retry),latest)
            with self.assertRaisesRegex(ValueError,'OPERATION_ID_CONFLICT'):store.accept_continuation(**request)
            seen=[]
            def missing(account,decision):seen.append((account,decision));raise ValueError('NEW_PACKAGE_MISSING')
            bridge=QuantityV2ContinuationSourceBridge(store=store,resolver=missing,clock=request['clock'])
            with self.assertRaisesRegex(ValueError,'NEW_PACKAGE_MISSING'):bridge._evidence(latest,request['clock']())
            self.assertEqual(seen,[(request['account_id'],p['capital_decision_id'])])
    def test_active_continuation_public_execution_lineage(self):
        with TemporaryDirectory() as folder:
            store,state,args,p,r,_=self.setup(folder)
            state=store.accept_monthly_retarget(**r)
            for oid in list(state['ledger']['orders']):
                state=store.record_event(account_id=r['account_id'],event=dict(event_id='close-'+oid,
                    type='CANCEL',order_id=oid,expected_revision=state['ledger']['revision'],
                    cancelled_at=args['now']),clock=r['clock'])
            # Isolate the compact bridge contract; actual evidence decoder has
            # separate source tests. Use real reviewed monthly chain and sizing.
            class DeclaredFixtureBridge(QuantityV2ContinuationSourceBridge):
                def _evidence(self,current,now):
                    inputs={key:deepcopy(args[key]) for key in ('securities','execution_references','unit_continuity','source_hashes')}
                    for ref in inputs['execution_references'].values():ref['last_at']=args['now']
                    return inputs,'fixture'
            bridge=DeclaredFixtureBridge(store=store,resolver=None,clock=r['clock'])
            result=bridge.preview(account_id=r['account_id'],expected_revision=state['ledger']['revision'])
            self.assertEqual(result['target_scope'],'MONTHLY_CURRENT_QUOTE_ALLOCATION')
            self.assertEqual(result['execution_target_id'],p['execution_target_id'])
            self.assertEqual(result['historical_target_quantities'],p['historical_target_quantities'])
            self.assertEqual(result['target_quantities'],p['target_quantities'])
            self.assertEqual(result['capital_decision_id'],p['capital_decision_id'])

    def test_rollback_stale_slow_and_conflict(self):
        with TemporaryDirectory() as folder:
            store,state,args,p,r,calls=self.setup(folder)
            with self.assertRaisesRegex(ValueError,'STALE_REVISION'):store.accept_monthly_retarget(**dict(r,expected_revision='old'))
            self.assertEqual(calls,[])
            stamps=iter([datetime.fromisoformat(args['now']),datetime.fromisoformat(args['now'])+timedelta(minutes=3)])
            with self.assertRaises(ValueError):store.accept_monthly_retarget(**dict(r,clock=lambda:next(stamps)))
            self.assertEqual(store.read(r['account_id']),state)
            with closing(sqlite3.connect(store.path,isolation_level=None)) as db:db.execute("CREATE TRIGGER abort_op BEFORE INSERT ON v2_accept_operations BEGIN SELECT RAISE(ABORT,'test'); END")
            with self.assertRaises(sqlite3.IntegrityError):store.accept_monthly_retarget(**r)
            self.assertEqual(QuantityV2PaperStore(store.path).read(r['account_id']),state)
            with closing(sqlite3.connect(store.path,isolation_level=None)) as db:db.execute('DROP TRIGGER abort_op')
            store.accept_monthly_retarget(**r)
            with self.assertRaisesRegex(ValueError,'OPERATION_ID_CONFLICT'):store.accept_monthly_retarget(**dict(r,account_id='other'))

if __name__=='__main__':unittest.main()
