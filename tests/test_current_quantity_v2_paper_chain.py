import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from test_current_quantity_v2_paper_ledger import initial,event
from data.current_quantity_v2_paper_ledger import record_event
from data.current_quantity_v2_paper_chain import create_chain,build_continuation,accept_continuation,record_chain_event,review_chain


def ready():
    s,_,args=initial()
    s=record_event(s,event(s),now='2026-10-15T13:01:00-04:00')
    s=record_event(s,event(s,kind='CANCEL',cancelled_at='2026-10-15T13:01:00-04:00'),now='2026-10-15T13:01:00-04:00')
    s=record_event(s,event(s,'SELL',executed_at='2026-10-15T13:01:00-04:00'),now='2026-10-15T13:01:00-04:00')
    return create_chain(s),args


def inputs(args,at='2026-10-15T13:03:30-04:00',price='1'):
    result={k:deepcopy(args[k]) for k in ('securities','execution_references','unit_continuity','source_hashes')}
    for k in ('securities','execution_references','unit_continuity'):result[k].pop('X')
    now=datetime.fromisoformat(at);ref=result['execution_references']['A']
    ref.update(last_price=price,minute_low=price,captured_at=at,checked_at=at,last_at=(now-timedelta(seconds=5)).isoformat(),
        minute_start=(now.replace(second=0)-timedelta(minutes=1)).isoformat(),minute_end=now.replace(second=0).isoformat(),
        valid_until=(now.replace(second=0)+timedelta(seconds=120)).isoformat())
    result['unit_continuity']['A'].update(covered_through=at,reviewed_at=at)
    return result


class ChainTests(unittest.TestCase):
    def test_multiple_accepts_carry_cash_fees_target_and_idempotence(self):
        chain,args=ready();p=build_continuation(chain,execution_inputs=inputs(args),now='2026-10-15T13:03:30-04:00')
        self.assertEqual(p['orders'][0]['quantity'],48)
        c=accept_continuation(chain,p,acceptance_id='accept1',now='2026-10-15T13:03:31-04:00')
        e=event(c['ledger'],quantity=10,price='1',fees='0',executed_at='2026-10-15T13:04:00-04:00',recorded_at='2026-10-15T13:04:01-04:00')
        c=record_chain_event(c,e,now=e['recorded_at'])
        cancel=event(c['ledger'],kind='CANCEL',cancelled_at='2026-10-15T13:04:02-04:00',recorded_at='2026-10-15T13:04:02-04:00')
        c=record_chain_event(c,cancel,now=cancel['recorded_at'])
        p2=build_continuation(c,execution_inputs=inputs(args,'2026-10-15T13:05:30-04:00','.5'),now='2026-10-15T13:05:30-04:00')
        self.assertEqual(p2['orders'][0]['quantity'],38) # Lower price never expands original 50 target.
        c=accept_continuation(c,p2,acceptance_id='accept2',now='2026-10-15T13:05:31-04:00')
        self.assertEqual(c['ledger']['cash'],'110');self.assertEqual(c['ledger']['recorded_fees'],'1/5')
        self.assertEqual(c['ledger']['shares']['A'],12);self.assertEqual(c['ledger']['target_quantities'],{'A':50})
        self.assertEqual(accept_continuation(c,p,acceptance_id='accept1',now='2026-11-01T00:00:00-04:00'),c)
        self.assertEqual(record_chain_event(c,e,now='2026-11-01T00:00:00-04:00'),c)
        self.assertEqual(review_chain(c),c)

    def test_open_expiry_month_and_tamper_reject(self):
        s,_,args=initial()
        with self.assertRaises(ValueError):build_continuation(create_chain(s),execution_inputs=inputs(args),now='2026-10-15T13:03:30-04:00')
        c,args=ready();p=build_continuation(c,execution_inputs=inputs(args),now='2026-10-15T13:03:30-04:00')
        with self.assertRaises(ValueError):accept_continuation(c,p,acceptance_id='a',now='2026-10-15T13:06:00-04:00')
        with self.assertRaises(ValueError):build_continuation(c,execution_inputs=inputs(args),now='2026-11-02T13:03:30-05:00')
        bad=deepcopy(c);bad['ledger']['cash']='1000'
        with self.assertRaises(ValueError):review_chain(bad)
        accepted=accept_continuation(c,p,acceptance_id='a',now='2026-10-15T13:03:31-04:00')
        bad=deepcopy(p);bad['orders'][0]['quantity']=49
        with self.assertRaises(ValueError):accept_continuation(accepted,bad,acceptance_id='a',now='2026-10-15T13:03:32-04:00')
        with self.assertRaises(ValueError):accept_continuation(accepted,p,acceptance_id='b',now='2026-10-15T13:03:32-04:00')

    def test_original_pins_and_no_action_not_accepted(self):
        c,args=ready();bad=inputs(args);bad['source_hashes']['source']='0'*64
        with self.assertRaises(ValueError):build_continuation(c,execution_inputs=bad,now='2026-10-15T13:03:30-04:00')
        p=build_continuation(c,execution_inputs=inputs(args),now='2026-10-15T13:03:30-04:00')
        c=accept_continuation(c,p,acceptance_id='a',now='2026-10-15T13:03:31-04:00')
        e=event(c['ledger'],quantity=48,price='1',fees='0',executed_at='2026-10-15T13:04:00-04:00',recorded_at='2026-10-15T13:04:01-04:00')
        c=record_chain_event(c,e,now=e['recorded_at'])
        done=build_continuation(c,execution_inputs=inputs(args,'2026-10-15T13:05:30-04:00'),now='2026-10-15T13:05:30-04:00')
        self.assertEqual(done['action'],'NO_ACTION');self.assertEqual(done['orders'],[])
        with self.assertRaises(ValueError):accept_continuation(c,done,acceptance_id='empty',now='2026-10-15T13:05:31-04:00')


if __name__=='__main__':unittest.main()
