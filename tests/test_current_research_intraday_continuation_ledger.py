import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import test_current_research_intraday_continuation as fixtures
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_continuation_ledger import build_continuation_proposal,accept_continuation_proposal,apply_continuation_event,review_continuation_ledger

class ChainTests(unittest.TestCase):
    def inputs(self,args):return {k:v for k,v in args.items() if k not in ('journal_root','now')}
    def accept(self,state,args,operation='continue'):
        proposal=build_continuation_proposal(state,**args)
        self.assertEqual(proposal['status'],'READY',proposal)
        return accept_continuation_proposal(state,proposal,operation_id=operation,journal_root=args['journal_root'],current_inputs=self.inputs(args),now=args['now']),proposal
    def event(self,state,kind='FILL',event_id='fill',**extra):
        result=dict(event_id=event_id,kind=kind,expected_revision=state['revision'],order_id=state['order']['order_id'],recorded_at=NOW.isoformat())
        if kind=='FILL':result.update(quantity=1,price='1400',fees='0',executed_at=NOW.isoformat())
        if kind=='CANCEL':result['cancelled_at']=NOW.isoformat()
        result.update(extra);return result
    def test_repeated_chain_conservation_and_frozen_replay(self):
        with tempfile.TemporaryDirectory() as root:
            service,state,args=fixtures.ContinuationTests().setup(root)
            state,proposal=self.accept(state,args)
            self.assertEqual(state['cash'],'17200');self.assertEqual(state['shares'],{'sndk':2})
            event=self.event(state);state=apply_continuation_event(state,event,now=NOW)
            self.assertEqual(state['cash'],'15800');self.assertEqual(state['shares'],{'sndk':3})
            self.assertEqual(apply_continuation_event(state,event,now=NOW),state)
            state=apply_continuation_event(state,self.event(state,'CANCEL','cancel2'),now=NOW)
            args['expected_revision']=state['revision']
            state,proposal=self.accept(state,args,'continue2')
            self.assertEqual(state['order']['quantity'],11)
            state=apply_continuation_event(state,self.event(state,event_id='fill2',quantity=2),now=NOW)
            self.assertEqual(state['cash'],'13000');self.assertEqual(state['shares'],{'sndk':5})
            self.assertEqual(review_continuation_ledger(state),state)
            for p in (Path(root)/'raw').glob('*'):p.write_bytes(b'changed')
            self.assertEqual(review_continuation_ledger(state),state)
    def test_accept_retry_stale_tampered_and_expired(self):
        with tempfile.TemporaryDirectory() as root:
            _,old,args=fixtures.ContinuationTests().setup(root);state,proposal=self.accept(old,args)
            self.assertEqual(accept_continuation_proposal(state,proposal,operation_id='continue',journal_root=root,current_inputs=self.inputs(args),now=NOW+timedelta(days=1)),state)
            for mode in ('tamper','stale','expired'):
                p=deepcopy(proposal);a=self.inputs(args);now=NOW
                if mode=='tamper':p['quantity']+=1
                if mode=='stale':a['expected_revision']='old'
                if mode=='expired':now+=timedelta(minutes=5)
                with self.assertRaises(ValueError):accept_continuation_proposal(old,p,operation_id='new',journal_root=root,current_inputs=a,now=now)
            broken=deepcopy(state);broken['cash']='20000'
            with self.assertRaises(ValueError):review_continuation_ledger(broken)
    def test_partial_fee_expiry_and_closed_fill(self):
        with tempfile.TemporaryDirectory() as root:
            _,old,args=fixtures.ContinuationTests().setup(root);state,_=self.accept(old,args)
            state=apply_continuation_event(state,self.event(state,fees='1'),now=NOW)
            self.assertEqual(state['cash'],'15799');self.assertEqual(state['fees'],'1')
            close=state['order']['session_close'];event=self.event(state,'EXPIRE','expire',recorded_at=close)
            state=apply_continuation_event(state,event,now=close)
            self.assertEqual(state['reserved_cash'],'0');self.assertEqual(state['shares'],{'sndk':3})
            with self.assertRaises(ValueError):apply_continuation_event(state,self.event(state,event_id='late'),now=close)

if __name__=='__main__':unittest.main()
