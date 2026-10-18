from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import sqlite3
import tempfile
from threading import Event
import unittest
import test_current_research_intraday_retarget_store as base
import test_current_research_intraday_retarget_continuation_chain as chains
from data.current_research_intraday_paper_store import IntradayPaperStore
from data.current_research_intraday_retarget_continuation_chain import build_retarget_chain_proposal,accept_retarget_chain_proposal,review_retarget_continuation_chain

class ChainStoreTests(unittest.TestCase):
    def fixture(self,root):
        store,before,proposal,args,factory=base.RetargetStoreTests().fixture(root)
        account=before['account_id'];initial_call=(account,proposal['proposal_id'],args['operation_id'],before['revision'])
        s=store.accept_retarget(*initial_call,factory)
        for side,kind,extra in [('SELL','FILL',dict(quantity=2,price='1500',fees='0',executed_at=args['now'].isoformat())),('BUY','CANCEL',dict(cancelled_at=args['now'].isoformat()))]:
            order=next(o for o in s['orders'].values() if o['side']==side)
            e=dict(event_id='close-'+side,kind=kind,expected_revision=s['revision'],order_id=order['order_id'],**extra)
            s=store.record_event(account,e,now=lambda:args['now'])
        payload=store.read_retarget_envelope(account);evidence=deepcopy(payload['execution_evidence'])
        for key in ('execution_inputs','units','references'):evidence[key].pop('sndk')
        paths=set(evidence['execution_inputs']['new']['source_hashes'])|set(evidence['units']['new']['source_references'])
        for key in ('files','source_hashes'):evidence[key]={p:v for p,v in evidence[key].items() if p in paths}
        u=evidence['units']['new'];u['retarget_acceptance_id']=s['retarget_acceptance_id'];u['original_reference_source_hashes']=evidence['references']['new']['source_hashes']
        now=args['now']+timedelta(minutes=1)
        evidence=chains.ChainTests().append_quote(evidence,now,39,38)
        p=build_retarget_chain_proposal(payload,expected_revision=s['revision'],execution_evidence=evidence,now=now)
        self.assertEqual(p['status'],'READY',p)
        call=(account,p['proposal_id'],'chain-1',s['revision'])
        def accept(current):return accept_retarget_chain_proposal(current,p,operation_id='chain-1',expected_revision=s['revision'],execution_evidence=evidence,now=now)
        return store,s,p,evidence,now,call,accept,initial_call,before
    def test_restart_fill_retry_and_second_cycle(self):
        with tempfile.TemporaryDirectory() as root:
            store,before,p,evidence,now,call,factory,initial,genesis=self.fixture(root)
            after=store.accept_retarget_chain(*call,factory)
            self.assertEqual(after['cash'],before['cash']);self.assertEqual(after['shares'],before['shares'])
            order=next(iter(after['orders'].values()));t=now+timedelta(seconds=1)
            fill=dict(event_id='part',kind='FILL',expected_revision=after['revision'],order_id=order['order_id'],quantity=100,price='37',fees='1',executed_at=t.isoformat())
            after=store.record_event(call[0],fill,now=lambda:t)
            cancel=dict(event_id='chain-cancel',kind='CANCEL',expected_revision=after['revision'],order_id=order['order_id'],cancelled_at=t.isoformat())
            after=store.record_event(call[0],cancel,now=lambda:t)
            restored=IntradayPaperStore(store.path.parent)
            self.assertEqual(restored.read(call[0]),after)
            payload=restored.read_retarget_envelope(call[0]);self.assertEqual(review_retarget_continuation_chain(payload),payload)
            fail=lambda *_:self.fail('retry factory/clock called')
            self.assertEqual(restored.accept_retarget_chain(*call,fail),after)
            self.assertEqual(restored.accept_retarget(*initial,fail),after)
            self.assertEqual(restored.accept(call[0],genesis['acceptance']['proposal']['proposal_id'],'initial',fail),after)
            self.assertEqual(restored.record_event(call[0],fill,now=fail),after)
            t=now+timedelta(minutes=1);e2=chains.ChainTests().append_quote(evidence,t,50,49)
            p2=build_retarget_chain_proposal(payload,expected_revision=after['revision'],execution_evidence=e2,now=t)
            final=restored.accept_retarget_chain(call[0],p2['proposal_id'],'chain-2',after['revision'],lambda current:accept_retarget_chain_proposal(current,p2,operation_id='chain-2',expected_revision=after['revision'],execution_evidence=e2,now=t))
            self.assertEqual(final['cash'],'16499');self.assertEqual(final['shares']['new'],100)
            self.assertEqual(next(iter(final['orders'].values()))['limit_price'],'38')
            self.assertEqual(final['target_quantities'],{'new':505})
    def test_insert_failure_rolls_back_payload_and_operation(self):
        with tempfile.TemporaryDirectory() as root:
            store,before,p,e,now,call,factory,_,_=self.fixture(root);oldpayload=store.read_retarget_envelope(call[0])
            with closing(sqlite3.connect(store.path)) as db:
                db.execute("CREATE TRIGGER reject_chain BEFORE INSERT ON intraday_retarget_chains BEGIN SELECT RAISE(ABORT,'rollback'); END");db.commit()
            with self.assertRaises(sqlite3.Error):store.accept_retarget_chain(*call,factory)
            self.assertEqual(store.read(call[0]),before);self.assertEqual(store.read_retarget_envelope(call[0]),oldpayload)
            with closing(sqlite3.connect(store.path)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM intraday_retarget_chains').fetchone()[0],0)
    def test_concurrent_same_operation_factory_once(self):
        with tempfile.TemporaryDirectory() as root:
            store,before,p,e,now,call,factory,_,_=self.fixture(root)
            entered,release,calls=Event(),Event(),[]
            def guarded(payload):
                calls.append(1);entered.set();self.assertTrue(release.wait(5));return factory(payload)
            with ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(store.accept_retarget_chain,*call,guarded);self.assertTrue(entered.wait(5))
                b=pool.submit(store.accept_retarget_chain,*call,guarded);release.set()
                self.assertEqual(a.result(10),b.result(10))
            self.assertEqual(calls,[1])
    def test_factory_reads_clock_after_external_write_lock(self):
        with tempfile.TemporaryDirectory() as root:
            store,before,p,e,now,call,factory,_,_=self.fixture(root)
            entered=Event();clock=[now];seen=[]
            def current_factory(payload):
                seen.append(clock[0])
                return accept_retarget_chain_proposal(payload,p,operation_id=call[2],expected_revision=call[3],execution_evidence=e,now=clock[0])
            def request():
                entered.set();return store.accept_retarget_chain(*call,current_factory)
            with closing(sqlite3.connect(store.path,isolation_level=None)) as blocker:
                blocker.execute('BEGIN IMMEDIATE')
                with ThreadPoolExecutor(max_workers=1) as pool:
                    task=pool.submit(request);self.assertTrue(entered.wait(5))
                    clock[0]=now+timedelta(seconds=1);self.assertEqual(seen,[])
                    blocker.commit();state=task.result(10)
            self.assertEqual(seen,[clock[0]])
            self.assertEqual(next(iter(state['orders'].values()))['accepted_at'],clock[0].isoformat())

    def test_global_operation_ids_stale_and_malicious_factory(self):
        with tempfile.TemporaryDirectory() as root:
            store,before,p,e,now,call,factory,initial,genesis=self.fixture(root)
            for oid,rev in [('initial',before['revision']),(initial[2],before['revision']),('new','stale')]:
                with self.assertRaises(ValueError):store.accept_retarget_chain(call[0],p['proposal_id'],oid,rev,lambda _:self.fail('invalid factory'))
            def bad(payload):
                result=factory(payload);result['ledger']['cash']='999999';return result
            with self.assertRaises(ValueError):store.accept_retarget_chain(*call,bad)
            self.assertEqual(store.read(call[0]),before)
            store.accept_retarget_chain(*call,factory)
            for method,args in [(store.accept,('other',p['proposal_id'],call[2])),(store.accept_continuation,(call[0],p['proposal_id'],call[2],before['revision'])),(store.accept_retarget,(call[0],p['proposal_id'],call[2],before['revision']))]:
                with self.assertRaises(ValueError):method(*args,lambda *_:self.fail('cross-table ID reused'))

if __name__=='__main__':unittest.main()

