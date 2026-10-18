import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
import test_current_research_intraday_retarget_sizing as fixtures
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing
from data.current_research_intraday_retarget_ledger import accept_retarget_proposal,apply_retarget_event,review_retarget_ledger

class RetargetLedgerTests(unittest.TestCase):
    def fixture(self,root):
        old,args=fixtures.SizingTests().fixture(root);now=args.pop('now')
        proposal=build_intraday_retarget_sizing(old,now=now,**args)
        market=dict(date='2026-11-02',timezone='America/New_York',open_at='2026-11-02T09:30:00-05:00',close_at='2026-11-02T16:00:00-05:00',source_references=['training'])
        state=accept_retarget_proposal(old,proposal,sizing_inputs=args,market_session=market,operation_id='retarget',now=now)
        return old,state,proposal,args,market,now
    def event(self,state,side,kind,when,**extra):
        oid=next(k for k,o in state['orders'].items() if o['side']==side)
        return dict(event_id='e'+str(len(state['retarget_events'])),kind=kind,expected_revision=state['revision'],order_id=oid,recorded_at=when.isoformat(),**extra)
    def test_sell_actual_cash_partial_buy_fee_and_replay(self):
        with tempfile.TemporaryDirectory() as root:
            old,s,p,args,m,now=self.fixture(root)
            self.assertEqual(s['cash'],old['cash']);self.assertEqual(s['shares'],old['shares']);self.assertEqual(s['reserved_cash'],'17200')
            t=now+timedelta(minutes=3) # after reference expiry, DAY still valid
            sell=self.event(s,'SELL','FILL',t,quantity=2,price='1501',fees='1',executed_at=t.isoformat())
            s=apply_retarget_event(s,sell,now=t);self.assertEqual(s['cash'],'20201')
            t+=timedelta(seconds=1)
            buy=self.event(s,'BUY','FILL',t,quantity=100,price='99',fees='2',executed_at=t.isoformat())
            s=apply_retarget_event(s,buy,now=t);self.assertEqual(s['cash'],'10299');self.assertEqual(s['reserved_cash'],'7200')
            self.assertEqual(s['shares']['new'],100);self.assertEqual(s['shares']['sndk'],0)
            self.assertEqual(apply_retarget_event(s,buy,now=t+timedelta(days=2)),s)
            self.assertEqual(review_retarget_ledger(s),s)
            bad=deepcopy(s);bad['cash']='50000'
            with self.assertRaisesRegex(ValueError,'REPLAY'):review_retarget_ledger(bad)
            self.assertEqual(accept_retarget_proposal(s,p,sizing_inputs=args,market_session=m,operation_id='retarget',now=t+timedelta(days=2)),s)
    def test_fee_reserves_overfill_stale_and_limits(self):
        with tempfile.TemporaryDirectory() as root:
            old,s,p,args,m,now=self.fixture(root);t=now+timedelta(seconds=1)
            e=self.event(s,'BUY','FILL',t,quantity=1,price='100',fees='1',executed_at=t.isoformat())
            with self.assertRaisesRegex(ValueError,'INSUFFICIENT_CASH'):apply_retarget_event(s,e,now=t)
            for changes in [dict(quantity=173),dict(price='101',fees='0'),dict(expected_revision='wrong'),dict(executed_at=(now-timedelta(seconds=1)).isoformat())]:
                bad=dict(e,**changes)
                with self.assertRaises(ValueError):apply_retarget_event(s,bad,now=t)
            bad=self.event(s,'SELL','FILL',t,quantity=3,price='1501',fees='0',executed_at=t.isoformat())
            with self.assertRaises(ValueError):apply_retarget_event(s,bad,now=t)
    def test_extended_session_cannot_enable_after_hours_fill(self):
        with tempfile.TemporaryDirectory() as root:
            old,s,p,args,m,now=self.fixture(root)
            m['close_at']='2026-11-02T20:00:00-05:00'
            with self.assertRaisesRegex(ValueError,'REFERENCE_MARKET_SESSION_MISMATCH'):
                accept_retarget_proposal(old,p,sizing_inputs=args,market_session=m,operation_id='badclose',now=now)

    def test_cancel_expire_and_second_activation_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            old,s,p,args,m,now=self.fixture(root);t=now+timedelta(seconds=1)
            cancel=self.event(s,'BUY','CANCEL',t,cancelled_at=t.isoformat());s=apply_retarget_event(s,cancel,now=t)
            self.assertEqual(s['cash'],old['cash']);self.assertEqual(s['reserved_cash'],'0')
            fill=self.event(s,'BUY','FILL',t,quantity=1,price='99',fees='0',executed_at=t.isoformat())
            with self.assertRaisesRegex(ValueError,'ORDER_CLOSED'):apply_retarget_event(s,fill,now=t)
            expire=self.event(s,'SELL','EXPIRE',t)
            with self.assertRaisesRegex(ValueError,'SESSION_NOT_CLOSED'):apply_retarget_event(s,expire,now=t)
            close=now.replace(hour=16);expire['recorded_at']=close.isoformat();s=apply_retarget_event(s,expire,now=close)
            self.assertEqual(s['reserved_shares'],{})
            with self.assertRaisesRegex(ValueError,'SECOND_RETARGET'):accept_retarget_proposal(s,p,sizing_inputs=args,market_session=m,operation_id='other',now=close)
            with self.assertRaises(ValueError):accept_retarget_proposal(old,p,sizing_inputs=args,market_session=m,operation_id='late',now=now+timedelta(seconds=120))

if __name__=='__main__':unittest.main()
