import unittest
from copy import deepcopy
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import (initialize_paper_ledger,apply_paper_fill,review_paper_ledger,
    apply_paper_order_event,activate_paper_plan,migrate_paper_ledger)


def create_paper_account(plan,*,mode):
    return initialize_paper_ledger(plan,'synthetic-account',mode=mode)


def plan(shares=None,cash='100',target=None):
    return build_current_research_limit_plan(research_snapshot=dict(research_id='a'*24,as_of='2030-01-01',
        stocks=[dict(security_id='a',ticker='A')],source_hashes={'synthetic':'b'*64}),
        quotes=[dict(security_id='a',price='10',as_of='2030-01-01',price_kind='DECLARED_DECIMAL_REFERENCE',
            price_basis='SYNTHETIC',source_references=['synthetic'])],available_cash=cash,shares=shares or {},
        account_revision='r0',decision_date='2030-01-01',active_date='2030-01-02',calendar=['2030-01-01','2030-01-02'],
        strategy_version='synthetic',target_quantities={'a':10} if target is None else target)


def event(state,**changes):
    result=dict(event_id='e1',mode='PAPER_MANUAL_FILL',plan_id=state['active_plan_id'],
        order_id=state['plan']['orders'][0]['order_id'],qty=3,price='9',fees='1',session=state['plan']['active_date'],expected_revision=state['revision'])
    result.update(changes);return result


def close_event(state,kind='CANCEL',**changes):
    value=dict(event_id='close1',mode='PAPER_MANUAL_FILL',event_type=kind,plan_id=state['active_plan_id'],
        order_id=state['plan']['orders'][0]['order_id'],expected_revision=state['revision'])
    if kind=='EXPIRE':value['completed_session']=state['plan']['active_date']
    value.update(changes);return value


def next_plan(state,**changes):
    c=state['plan']['causal_inputs'];d=state['plan']['active_date']
    args=dict(research_snapshot=deepcopy(c['research_snapshot']),
        quotes=[dict(v,security_id=s,as_of=d) for s,v in c['quotes'].items()],available_cash=state['cash'],
        shares=state['shares'],account_revision=state['revision'],decision_date=d,active_date='2030-01-03',
        calendar=[d,'2030-01-03'],strategy_version=c['strategy_version'],target_quantities={'a':10})
    args.update(changes);return build_current_research_limit_plan(**args)


def activation(state,new,**changes):
    value=dict(event_id='activate1',mode='PAPER_MANUAL_FILL',event_type='ACTIVATE_PLAN',
        plan_id=new['plan_id'],expected_revision=state['revision']);value.update(changes);return value


class PaperFillTests(unittest.TestCase):
    def test_partial_cancel_releases_only_remainder_latefill_and_duplicate(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL');fill=event(s)
        s=apply_paper_fill(s,fill);before=deepcopy(s);cancel=close_event(s)
        s=apply_paper_order_event(s,cancel)
        self.assertEqual((s['cash'],s['shares'],s['total_recorded_fees']),(before['cash'],before['shares'],before['total_recorded_fees']))
        self.assertEqual(s['reserved_cash'],'0')
        self.assertEqual(s['closed_orders'][cancel['order_id']]['unfilled_quantity'],7)
        self.assertEqual(apply_paper_order_event(s,cancel),s)
        self.assertEqual(apply_paper_fill(s,fill),s)
        with self.assertRaisesRegex(ValueError,'ORDER_CLOSED'):apply_paper_fill(s,event(s,event_id='newfill'))
        with self.assertRaisesRegex(ValueError,'CONFLICTING_EVENT_ID'):apply_paper_order_event(s,dict(cancel,event_type='EXPIRE',completed_session='2030-01-02'))

    def test_expiry_manual_session_and_no_capital_change(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL')
        with self.assertRaisesRegex(ValueError,'EXPIRY_SESSION'):apply_paper_order_event(s,close_event(s,'EXPIRE',completed_session='2030-01-01'))
        e=close_event(s,'EXPIRE');out=apply_paper_order_event(s,e)
        self.assertEqual(out['cash'],'100');self.assertEqual(out['shares'],{})
        self.assertEqual(review_paper_ledger(out)['orders'][0]['order_status'],'EXPIRE')

    def test_switch_exact_capital_history_and_cross_plan_duplicates(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL');fill=event(s);s=apply_paper_fill(s,fill)
        n=next_plan(s)
        with self.assertRaisesRegex(ValueError,'OLD_PLAN_HAS_OPEN'):activate_paper_plan(s,n,activation(s,n))
        cancel=close_event(s);s=apply_paper_order_event(s,cancel)
        for changes,reason in [(dict(available_cash='999'),'NEW_PLAN_CASH'),(dict(shares={'a':4}),'NEW_PLAN_SHARES'),(dict(account_revision='wrong'),'NEW_PLAN_REVISION')]:
            n=next_plan(s,**changes)
            with self.assertRaisesRegex(ValueError,reason):activate_paper_plan(s,n,activation(s,n))
        n=next_plan(s);a=activation(s,n);out=activate_paper_plan(s,n,a)
        self.assertEqual(out['cash'],s['cash']);self.assertEqual(out['shares'],s['shares']);self.assertEqual(len(out['plans']),2)
        self.assertEqual(apply_paper_fill(out,fill),out)
        self.assertEqual(apply_paper_order_event(out,cancel),out)
        self.assertEqual(activate_paper_plan(out,n,a),out)
        self.assertEqual(review_paper_ledger(out)['plan_history_ids'],[s['plan']['plan_id'],n['plan_id']])
        out=apply_paper_fill(out,event(out,event_id='new-plan-fill',qty=1,price='10',fees='0'))
        self.assertEqual(out['shares']['a'],4);self.assertEqual(out['cash'],'62')
        self.assertEqual(apply_paper_fill(out,fill),out)
        with self.assertRaisesRegex(ValueError,'CONFLICTING_EVENT_ID'):
            apply_paper_fill(out,event(out,event_id=fill['event_id'],qty=1))
        tampered=deepcopy(out);tampered['plans'][0]['orders'][0]['quantity']=999
        with self.assertRaises(ValueError):review_paper_ledger(tampered)

    def test_activation_requires_new_id_and_nonretrograde_decision(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL')
        s=apply_paper_order_event(s,close_event(s))
        with self.assertRaisesRegex(ValueError,'PLAN_ID_REUSED'):
            activate_paper_plan(s,s['plan'],activation(s,s['plan']))
        c=s['plan']['causal_inputs']
        olddate=c['decision_date']
        n=next_plan(s,decision_date=olddate,active_date='2030-01-02',calendar=[olddate,'2030-01-02'],
            quotes=[dict(v,security_id=k,as_of=olddate) for k,v in c['quotes'].items()])
        with self.assertRaisesRegex(ValueError,'BEFORE_OLD_ACTIVE'):
            activate_paper_plan(s,n,activation(s,n))

    def test_explicit_v1_migration_verifies_preserves_and_rejects_tamper(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL');s=apply_paper_fill(s,event(s))
        old={k:v for k,v in s.items() if k not in ('schema','plans','closed_orders')}
        with self.assertRaisesRegex(ValueError,'MIGRATION_REQUIRED'):review_paper_ledger(old)
        self.assertEqual(migrate_paper_ledger(old),s)
        old['cash']='999'
        with self.assertRaisesRegex(ValueError,'LEGACY_STATE_TAMPERED'):migrate_paper_ledger(old)

    def test_revision_binds_account_and_nondict_state_rejected(self):
        p=plan()
        first=initialize_paper_ledger(p,'account-one')
        second=initialize_paper_ledger(p,'account-two')
        self.assertNotEqual(first['revision'],second['revision'])
        with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_REVISION'):
            apply_paper_fill(second,event(first))
        with self.assertRaisesRegex(ValueError,'PAPER_STATE_DICT_REQUIRED'):
            apply_paper_fill(None,event(first))
        with self.assertRaisesRegex(ValueError,'PAPER_STATE_DICT_REQUIRED'):
            review_paper_ledger([])

    def test_partial_duplicate_conflict_revision_and_review(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL');e=event(s);original=deepcopy(s)
        filled=apply_paper_fill(s,e);self.assertEqual(s,original)
        self.assertEqual(filled['cash'],'72');self.assertEqual(filled['shares'],{'a':3})
        self.assertEqual(apply_paper_fill(filled,e),filled)
        with self.assertRaisesRegex(ValueError,'CONFLICTING_EVENT_ID'):apply_paper_fill(filled,dict(e,qty=2))
        with self.assertRaisesRegex(ValueError,'STALE_ACCOUNT_REVISION'):apply_paper_fill(filled,dict(e,event_id='e2'))
        filled=apply_paper_fill(filled,event(filled,event_id='e2',qty=7,price='10',fees='2'))
        r=review_paper_ledger(filled);self.assertEqual(r['cash'],'0');self.assertEqual(r['shares']['a'],10)
        self.assertEqual(r['orders'][0]['unfilled_quantity'],0);self.assertEqual(r['total_recorded_fees'],'3')
        self.assertEqual(r['price_touch_status'],'UNKNOWN_NOT_EVALUATED')

    def test_overfill_price_cash_and_other_plan_rejected(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL')
        for changes in [dict(qty=11),dict(price='10.01'),dict(qty=10,price='10',fees='1'),dict(plan_id='other'),dict(session='2030-01-03'),dict(qty=True),dict(mode='BROKER_REAL')]:
            with self.assertRaises(ValueError):apply_paper_fill(s,event(s,**changes))

    def test_sell_limit_oversell_and_late_record_session(self):
        s=create_paper_account(plan(shares={'a':4},cash='0',target={}),mode='PAPER_MANUAL_FILL')
        with self.assertRaises(ValueError):apply_paper_fill(s,event(s,qty=5,price='10'))
        with self.assertRaises(ValueError):apply_paper_fill(s,event(s,price='9'))
        s=apply_paper_fill(s,event(s,qty=4,price='11',fees='1'))
        self.assertEqual(s['cash'],'43');self.assertEqual(s['shares']['a'],0)

    def test_tampered_plan_state_and_real_mode_rejected(self):
        p=plan();p['orders'][0]['quantity']=100
        with self.assertRaises(ValueError):create_paper_account(p,mode='PAPER_MANUAL_FILL')
        with self.assertRaises(ValueError):create_paper_account(plan(),mode='BROKER_REAL')
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL');s['cash']='1000'
        with self.assertRaises(ValueError):apply_paper_fill(s,event(s))

    def test_fee_cannot_consume_remaining_order_reservation(self):
        s=create_paper_account(plan(),mode='PAPER_MANUAL_FILL')
        with self.assertRaisesRegex(ValueError,'REMAINING_BUY_RESERVATIONS'):
            apply_paper_fill(s,event(s,qty=1,price='10',fees='1'))
        filled=apply_paper_fill(s,event(s,qty=1,price='9',fees='1'))
        self.assertEqual(filled['reserved_cash'],'90')
        self.assertEqual(filled['cash'],'90')


if __name__=='__main__':unittest.main()
