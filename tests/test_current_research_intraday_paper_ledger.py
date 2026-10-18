import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import test_current_research_intraday_buy_plan as proposal_tests
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_buy_plan import build_intraday_initial_buy_proposal
from data.current_research_intraday_paper_ledger import accept_intraday_proposal,apply_intraday_paper_event,review_intraday_paper_ledger

class AcceptanceTests(unittest.TestCase):
    def fixture(self,root):
        service,args=proposal_tests.BuyProposalTests().fixture(root);proposal=build_intraday_initial_buy_proposal(**args)
        current={k:v for k,v in args.items() if k not in ('journal_root','now')}
        state=accept_intraday_proposal(proposal,journal_root=root,current_inputs=current,now=NOW)
        return service,proposal,current,state
    def event(self,state,kind='FILL',**extra):
        e=dict(event_id='one',kind=kind,expected_revision=state['revision'],order_id=state['order']['order_id'],recorded_at=(NOW+timedelta(minutes=5)).isoformat())
        if kind=='FILL':e.update(quantity=1,price='1400',fees='1',executed_at=(NOW+timedelta(minutes=4)).isoformat())
        e.update(extra);return e
    def test_fill_after_reference_expiry_and_frozen_replay(self):
        with tempfile.TemporaryDirectory() as root:
            service,p,c,s=self.fixture(root);e=self.event(s)
            result=apply_intraday_paper_event(s,e,now=NOW+timedelta(minutes=6))
            self.assertEqual(result['cash'],'18599');self.assertEqual(result['shares'],{'sndk':1})
            self.assertEqual(apply_intraday_paper_event(result,e,now=NOW+timedelta(minutes=6)),result)
            service.preview('a'*24)
            for path in Path(root).rglob('*.bin'):path.write_bytes(b'changed later')
            self.assertEqual(review_intraday_paper_ledger(result),result)
    def test_acceptance_rechecks_and_tampered_proposal(self):
        with tempfile.TemporaryDirectory() as root:
            service,p,c,s=self.fixture(root)
            bad=deepcopy(p);bad['quantity']+=1
            with self.assertRaises(ValueError):accept_intraday_proposal(bad,journal_root=root,current_inputs=c,now=NOW)
            for change in ({'available_cash':'19000'},{'account_revision':'new','expected_revision':'new'}):
                args=deepcopy(c);args.update(change)
                with self.assertRaises(ValueError):accept_intraday_proposal(p,journal_root=root,current_inputs=args,now=NOW)
            with self.assertRaises(ValueError):accept_intraday_proposal(p,journal_root=root,current_inputs=c,now=NOW+timedelta(minutes=3))
            service.preview('a'*24)
            with self.assertRaises(ValueError):accept_intraday_proposal(p,journal_root=root,current_inputs=c,now=NOW)
    def test_times_fees_overfill_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            _,_,_,s=self.fixture(root)
            for values in ({'executed_at':(NOW-timedelta(seconds=1)).isoformat()},{'executed_at':s['order']['session_close']},{'fees':'20000'},{'quantity':15},{'price':'1500'},{'recorded_at':(NOW+timedelta(days=1)).isoformat()}):
                with self.assertRaises(ValueError):apply_intraday_paper_event(s,self.event(s,**values),now=NOW+timedelta(minutes=6))
            e=self.event(s);r=apply_intraday_paper_event(s,e,now=NOW+timedelta(minutes=6));e['fees']='0'
            with self.assertRaises(ValueError):apply_intraday_paper_event(r,e,now=NOW+timedelta(minutes=6))
    def test_cancel_expire_preserve_partial_and_reject_late_fill(self):
        with tempfile.TemporaryDirectory() as root:
            _,_,_,s=self.fixture(root);s=apply_intraday_paper_event(s,self.event(s),now=NOW+timedelta(minutes=6))
            cancel=self.event(s,'CANCEL',event_id='cancel',cancelled_at=(NOW+timedelta(minutes=5)).isoformat())
            r=apply_intraday_paper_event(s,cancel,now=NOW+timedelta(minutes=6))
            self.assertEqual(r['cash'],s['cash']);self.assertEqual(r['reserved_cash'],'0');self.assertEqual(r['shares'],s['shares'])
            with self.assertRaises(ValueError):apply_intraday_paper_event(r,self.event(r,event_id='late'),now=NOW+timedelta(minutes=6))
            with self.assertRaises(ValueError):apply_intraday_paper_event(s,self.event(s,'EXPIRE',event_id='expiry'),now=NOW+timedelta(minutes=6))
            close=s['order']['session_close'];e=self.event(s,'EXPIRE',event_id='expiry',recorded_at=close)
            r=apply_intraday_paper_event(s,e,now=close);self.assertEqual(r['closed'],'EXPIRE')

if __name__=='__main__':unittest.main()
