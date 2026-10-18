import unittest
from copy import deepcopy
from data.current_research_limit_plan import build_current_research_limit_plan as build


def fixture():
    return dict(research_snapshot=dict(research_id='a'*24,as_of='2026-10-13',
        stocks=[dict(security_id=s,ticker=s.upper(),close='10.009') for s in ('a','b')],source_hashes={'source':'b'*64}),
        quotes=[dict(security_id=s,price='10.009',as_of='2026-10-13',price_kind='RAW_PROVIDER_CLOSE_DECIMAL',price_basis='CONDITIONAL',source_references=['source']) for s in ('a','b')],
        available_cash='100',shares={},account_revision='r1',decision_date='2026-10-13',active_date='2026-10-14',
        calendar=['2026-10-13','2026-10-14','2026-10-15'],strategy_version='paper-v1',target_quantities={'a':9})


class ResearchPlanTests(unittest.TestCase):
    def test_stable_id_and_cash_account_source_binding(self):
        a=fixture();before=deepcopy(a);r=build(**a)
        self.assertEqual(r['status'],'READY');self.assertEqual(a,before)
        self.assertEqual(r['plan_id'],build(**deepcopy(a))['plan_id'])
        for key,value in [('available_cash','101'),('account_revision','r2'),('strategy_version','paper-v2')]:
            changed=deepcopy(a);changed[key]=value;self.assertNotEqual(r['plan_id'],build(**changed)['plan_id'])
        a['research_snapshot']['source_hashes']['source']='c'*64
        self.assertNotEqual(r['plan_id'],build(**a)['plan_id'])

    def test_sells_never_finance_buys_and_exact_target(self):
        a=fixture();a.update(available_cash='0',shares={'a':10},target_quantities={'b':10})
        r=build(**a);self.assertEqual(r['status'],'READY')
        self.assertEqual([(o['side'],o['quantity'],o['limit']) for o in r['orders']],[('SELL',10,'1001/100')])
        self.assertEqual(r['wait_cash'][0]['remaining_deficit'],10)
        self.assertEqual(r['target_quantities'],{'b':10});self.assertEqual(r['reserved_cash'],'0')

    def test_partial_cash_exact_fraction_and_overequity_wait(self):
        a=fixture();a.update(available_cash='25',shares={'a':10},target_quantities={'b':10})
        r=build(**a);self.assertEqual([o['quantity'] for o in r['orders'] if o['side']=='BUY'],[2])
        self.assertEqual(r['reserved_cash'],'20');self.assertEqual(r['unreserved_cash'],'5')
        a['target_quantities']={'b':100};r=build(**a)
        self.assertEqual(r['status'],'READY');self.assertFalse(r['target_affordable_at_reference'])
        self.assertEqual(r['target_quantities'],{'b':100});self.assertEqual(r['wait_cash'][0]['remaining_deficit'],98)

    def test_invalid_values_dates_sources_and_identity(self):
        changes=[('available_cash',True),('available_cash','-1'),('shares',{'a':1.5}),('target_quantities',{'a':True}),
                 ('shares',{'unknown':1}),('active_date','2026-10-15')]
        for key,value in changes:
            a=fixture();a[key]=value;self.assertEqual(build(**a)['status'],'BLOCKED')
        for mutate in [lambda s:s.update(as_of='2026-10-15'),lambda s:s.update(source_hashes={}),
                       lambda s:s['stocks'].append(dict(s['stocks'][0]))]:
            a=fixture();mutate(a['research_snapshot']);self.assertEqual(build(**a)['status'],'BLOCKED')

    def test_selection_date_separate_and_quote_kind_explicit(self):
        a=fixture();a['research_snapshot']['as_of']='2026-10-12'
        a['quotes'][0].update(price='10.01',price_kind='CENT_DISPLAY_REFERENCE')
        r=build(**a);self.assertEqual(r['status'],'READY');self.assertEqual(r['orders'][0]['limit'],'1001/100')
        original=r['plan_id'];a['quotes'][0]['price_kind']='DECLARED_DECIMAL_REFERENCE'
        self.assertNotEqual(build(**a)['plan_id'],original)
        for key,value in [('as_of','2026-10-12'),('price',10.01),('source_references',[]),('price_basis',''),('price_kind','')]:
            b=deepcopy(a);b['quotes'][0][key]=value;self.assertEqual(build(**b)['status'],'BLOCKED')

    def test_research_guard_unknown_costs_and_no_action(self):
        a=fixture();a.update(shares={'a':9},target_quantities={'a':9})
        r=build(**a);self.assertEqual(r['action'],'NO_ACTION')
        self.assertTrue(r['research_only']);self.assertTrue(r['execution_blocked']);self.assertFalse(r['adopted'])
        self.assertFalse(r['fee_scope']['all_transaction_costs_zero'])

    def test_quote_reference_requires_fingerprint_binding(self):
        arguments = fixture()
        arguments['quotes'][0]['source_references'] = ['not-pinned']
        result = build(**arguments)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'QUOTE_SOURCE_NOT_PINNED')
        self.assertEqual(result['orders'], [])


if __name__=='__main__':unittest.main()
