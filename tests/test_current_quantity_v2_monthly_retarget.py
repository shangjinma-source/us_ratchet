import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from test_current_quantity_v2_paper_chain import ready
from test_current_research_capital_decision_v2 import CapitalV2Tests
from test_current_quantity_v2_paper_ledger import event
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
from data.current_quantity_v2_monthly_retarget import build_monthly_retarget
from data.current_quantity_v2_paper_chain import accept_monthly_retarget,accept_continuation,review_chain,record_chain_event,build_continuation


def fixture(seed=None,day='2026-10-30',at='2026-11-02T12:00:30-05:00'):
    chain,old=ready() if seed is None else seed;ledger=chain['ledger'];session=at[:10]
    args=CapitalV2Tests().arguments();args['decision_date']=day
    args['account_state'].update(asof=day,revision=ledger['revision'],cash=ledger['cash'],shares=deepcopy(ledger['shares']))
    args['source_hashes']['source']='a'*64
    args['source_hashes'].update(old['source_hashes'])
    args['search_arguments'].update(decision_date=day,quote_as_of=day,prices={'B':'1'},metadata={'B':{'ticker':'BBB','issuer_id':'ib'}},
        training_scenarios=[{'B':'2'},{'B':'1/2'}],scenario_dates=['2026-09-30',day])
    args['valuation_quotes']=[dict(security_id=s,as_of=day,price='1',price_basis='SYNTHETIC_USD',source_references=['quote']) for s in ('A','B')]
    d=decide_quantity_v2_for_account(**args);a=deepcopy(old);a.update(capital_decision=d,now=at)
    a['account_state'].update(account_id=ledger['account_id'],revision=ledger['revision'],cash=ledger['cash'],shares=deepcopy(ledger['shares']),observed_at=ledger['last_recorded_at'])
    a['target_mandate'].update(account_id=ledger['account_id'],capital_decision_id=d['decision_id'],target_month=session[:7],active_date=session)
    a['securities']={'A':old['securities']['A'],'B':{'ticker':'BBB','issuer_id':'ib'}}
    a['source_hashes']=args['source_hashes'];a['execution_references']={};a['unit_continuity']={}
    for sid in ('A','B'):
        ref=deepcopy(old['execution_references']['A']);ref.update(security_id=sid,ticker=a['securities'][sid]['ticker'],session=session,
            captured_at=at,checked_at=at,last_at=session+'T12:00:25-05:00',minute_start=session+'T11:59:00-05:00',
            minute_end=session+'T12:00:00-05:00',valid_until=session+'T12:02:00-05:00',
            session_open=session+'T09:30:00-05:00',session_close=session+'T16:00:00-05:00',last_price='0.5',minute_low='0.5')
        a['execution_references'][sid]=ref
        unit=deepcopy(old['unit_continuity']['A']);unit.update(security_id=sid,ticker=ref['ticker'],capital_decision_id=d['decision_id'],
            reference_source_hashes=ref['source_hashes'],covered_from_date=day,covered_through=at,reviewed_at=at,valuation_source_references=['quote'])
        a['unit_continuity'][sid]=unit
    prior=old['execution_references']['A']
    a['held_unit_continuity']={'A':dict(prior_revision=ledger['revision'],security_id='A',
        prior_active_proposal_id=ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']['proposal_id'],prior_price_basis=prior['price_basis'],price_basis=prior['price_basis'],security_class=old['securities']['A'].get('security_class'),
        prior_reference_source_hashes=prior['source_hashes'],reference_source_hashes=a['execution_references']['A']['source_hashes'],
        covered_from=prior['captured_at'],covered_through=at,reviewed_at=at,status='NO_UNPROCESSED_ACTIONS',source_references=['source'])}
    return chain,a,at


class MonthlyTests(unittest.TestCase):
    def test_carry_new_targets_and_followup(self):
        c,a,at=fixture();before=deepcopy(c);p=build_monthly_retarget(c,proposal_inputs=a,now=at)
        self.assertGreater(p['target_quantities']['B'],p['historical_target_quantities']['B'])
        n=accept_monthly_retarget(c,p,acceptance_id='month1',now=at)
        with self.assertRaisesRegex(ValueError,'ACCEPTANCE_ID_CONFLICT'):
            accept_continuation(n,p,acceptance_id='month1',now=at)
        self.assertFalse(n['ledger']['current_execution_bytes_verified'])
        for key in ('cash','shares','recorded_fees','events'):self.assertEqual(n['ledger'][key],c['ledger'][key])
        self.assertEqual(n['genesis'],c['genesis']);self.assertEqual(c,before)
        for oid in list(n['ledger']['orders']):
            e=dict(event_id='cancel-'+oid,type='CANCEL',order_id=oid,expected_revision=n['ledger']['revision'],
                recorded_at=at,cancelled_at=at)
            n=record_chain_event(n,e,now=at)
        inp={k:deepcopy(a[k]) for k in ('securities','execution_references','unit_continuity','source_hashes')}
        for ref in inp['execution_references'].values():ref['last_at']=at
        follow=build_continuation(n,execution_inputs=inp,now=at)
        self.assertEqual(follow['binding']['capital_decision_id'],p['capital_decision_id'])
        self.assertEqual(follow['binding']['target_quantities'],p['target_quantities'])
        self.assertEqual(accept_monthly_retarget(n,p,acceptance_id='month1',now='2027-01-01T00:00:00+00:00'),n)
        self.assertEqual(review_chain(n),n)
        c2,a2,at2=fixture((n,p['causal_inputs']),day='2026-11-30',at='2026-12-01T12:00:30-05:00')
        p2=build_monthly_retarget(c2,proposal_inputs=a2,now=at2)
        n2=accept_monthly_retarget(c2,p2,acceptance_id='month2',now=at2)
        self.assertEqual(n2['genesis'],c['genesis']);self.assertEqual(n2['ledger']['recorded_fees'],c['ledger']['recorded_fees'])
        self.assertEqual(review_chain(n2),n2)

    def test_real_currentcash_genesis_to_new_month(self):
        import test_current_quantity_v2_current_cash_plan as base
        from test_current_quantity_v2_current_cash_continuation import fixture as cash_fixture
        from test_current_quantity_v2_difference_plan import fixture as old_fixture
        base.CurrentCashTests.setUpClass()
        try:
            state,_,_=cash_fixture(base.CurrentCashTests.args)
            original=state['ledger']['acceptance']['proposal'];old=old_fixture()
            old['securities']['A']=deepcopy(original['securities']['A'])
            row=next(r for r in original['rows'] if r['security_id']=='A')
            old['execution_references']['A'].update(captured_at=row['captured_at'],source_hashes=row['source_hashes'])
            old['source_hashes'].update(original['causal_inputs']['frozen_execution_package']['source_hashes'])
            c,a,at=fixture((state,old))
            a['held_unit_continuity']['A']['prior_price_basis']='PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE'
            p=build_monthly_retarget(c,proposal_inputs=a,now=at)
            n=accept_monthly_retarget(c,p,acceptance_id='cash-new-month',now=at)
            self.assertEqual(n['genesis'],c['genesis']);self.assertEqual(n['ledger']['cash'],'459/5')
            self.assertEqual(n['ledger']['recorded_fees'],'1/5')
            self.assertNotEqual(n['ledger']['target_quantities'],{'A':6,'B':4})
            for oid in list(n['ledger']['orders']):
                e=dict(event_id='close-'+oid,type='CANCEL',order_id=oid,expected_revision=n['ledger']['revision'],recorded_at=at,cancelled_at=at)
                n=record_chain_event(n,e,now=at)
            inp={k:deepcopy(a[k]) for k in ('securities','execution_references','unit_continuity','source_hashes')}
            for r in inp['execution_references'].values():r['last_at']=at
            follow=build_continuation(n,execution_inputs=inp,now=at)
            self.assertEqual(follow['binding']['capital_decision_id'],p['capital_decision_id'])
            self.assertEqual(follow['binding']['target_quantities'],p['target_quantities'])
            self.assertEqual(review_chain(n),n)
        finally:base.CurrentCashTests.tearDownClass()

    def test_reject_stale_tamper_missing_bridge_and_repeat_month(self):
        c,a,at=fixture()
        for change in (lambda x:x['account_state'].update(cash='999'),lambda x:x['held_unit_continuity'].clear(),
            lambda x:x['held_unit_continuity']['A'].update(covered_from=at)):
            bad=deepcopy(a);change(bad)
            with self.assertRaises(ValueError):build_monthly_retarget(c,proposal_inputs=bad,now=at)
        bad=deepcopy(a);bad['capital_decision']['decision_date']=c['genesis']['acceptance']['proposal']['causal_inputs']['capital_decision']['decision_date']
        with self.assertRaisesRegex(ValueError,'NEW_MONTHLY_DECISION_REQUIRED'):build_monthly_retarget(c,proposal_inputs=bad,now=at)
        p=build_monthly_retarget(c,proposal_inputs=a,now=at)
        with self.assertRaises(ValueError):accept_monthly_retarget(c,p,acceptance_id='x',now='2026-11-02T12:02:00-05:00')
        bad=deepcopy(p);bad['target_quantities']['B']+=1
        with self.assertRaises(ValueError):accept_monthly_retarget(c,bad,acceptance_id='x',now=at)


if __name__=='__main__':unittest.main()
