import unittest
from copy import deepcopy
from hashlib import sha256
import json
from test_current_quantity_v2_difference_plan import fixture
from data.current_quantity_v2_difference_plan import build_account_difference_plan
from data.current_quantity_v2_paper_ledger import accept_proposal,record_event,review_ledger


def initial():
    args=fixture();d=args['capital_decision'];b=d['binding']
    args['account_state']['cash']='20';b['available_cash']='20';d['available_cash']='20'
    b['valuation_quotes']['X']['price']='40';d['holding_market_values']['X']='80'
    identity=sha256(json.dumps(b,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    d.update(decision_id=identity,research_id=identity[:24]);args['target_mandate']['capital_decision_id']=identity
    for unit in args['unit_continuity'].values():unit['capital_decision_id']=identity
    proposal=build_account_difference_plan(**args)
    return accept_proposal(proposal,account_state=args['account_state'],now=args['now']),proposal,args


def event(state,side='BUY',kind='FILL',**overrides):
    oid=next(k for k,v in state['orders'].items() if v['side']==side)
    e=dict(event_id='e'+str(len(state['events'])),type=kind,order_id=oid,expected_revision=state['revision'],recorded_at='2026-10-15T13:01:00-04:00')
    if kind=='FILL':e.update(quantity=2,price='0.9' if side=='BUY' else '51',fees='0.1',executed_at='2026-10-15T13:00:00-04:00')
    if kind=='CANCEL':e['cancelled_at']='2026-10-15T13:00:00-04:00'
    e.update(overrides);return e


class LedgerTests(unittest.TestCase):
    def test_partial_buy_sell_fees_replay_and_idempotence(self):
        s,_,_=initial();before=deepcopy(s)
        self.assertEqual(s['cash'],'20');self.assertEqual(s['reserved_cash'],'20')
        e=event(s);s=record_event(s,e,now='2026-10-15T13:02:00-04:00')
        self.assertEqual(s['cash'],'181/10');self.assertEqual(s['reserved_cash'],'18')
        self.assertEqual(record_event(s,e,now='2026-10-16T10:00:00-04:00'),s)
        sell=event(s,'SELL',executed_at='2026-10-15T13:01:00-04:00',recorded_at='2026-10-15T13:02:00-04:00')
        s=record_event(s,sell,now='2026-10-15T13:02:00-04:00')
        self.assertEqual(s['cash'],'120');self.assertEqual(s['recorded_fees'],'1/5')
        self.assertEqual(s['shares'],{'X':0,'A':2});self.assertEqual(review_ledger(s),s)
        self.assertEqual(before['events'],[])
        with self.assertRaises(ValueError):record_event(s,dict(e,fees='0'),now='2026-10-16T10:00:00-04:00')

    def test_cancel_expire_release_only_and_late_fill_rejected(self):
        s,_,_=initial();s=record_event(s,event(s,kind='CANCEL'),now='2026-10-15T13:01:00-04:00')
        self.assertEqual(s['cash'],'20');self.assertEqual(s['reserved_cash'],'0')
        with self.assertRaises(ValueError):record_event(s,event(s),now='2026-10-15T13:01:00-04:00')
        early=event(s,'SELL','EXPIRE')
        with self.assertRaises(ValueError):record_event(s,early,now='2026-10-15T13:01:00-04:00')
        s=record_event(s,event(s,'SELL','EXPIRE',recorded_at='2026-10-15T16:00:00-04:00'),now='2026-10-15T16:00:00-04:00')
        self.assertEqual(s['reserved_shares'],{});self.assertEqual(s['shares'],{'X':2})

    def test_limits_reserve_revision_times_and_tamper(self):
        for change in ({'price':'1.01'},{'fees':'1'},{'quantity':21},{'expected_revision':'old'},
                       {'executed_at':'2026-10-15T12:00:00-04:00'},
                       {'executed_at':'2026-10-15T16:00:00-04:00','recorded_at':'2026-10-15T16:01:00-04:00'}):
            s,_,_=initial()
            with self.assertRaises(ValueError):record_event(s,event(s,**change),now='2026-10-15T16:02:00-04:00')
        s,p,a=initial();s['cash']='999'
        with self.assertRaises(ValueError):review_ledger(s)
        p['orders'][0]['quantity']=1
        with self.assertRaises(ValueError):accept_proposal(p,account_state=a['account_state'],now=a['now'])

    def test_acceptance_expiry_and_account_binding(self):
        _,p,a=initial()
        with self.assertRaises(ValueError):accept_proposal(p,account_state=a['account_state'],now='2026-10-15T12:03:00-04:00')
        a['account_state']['revision']='changed'
        with self.assertRaises(ValueError):accept_proposal(p,account_state=a['account_state'],now=a['now'])


if __name__=='__main__':unittest.main()
