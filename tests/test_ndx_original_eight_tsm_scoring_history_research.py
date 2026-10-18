from copy import deepcopy
from fractions import Fraction
import json,unittest
from backtest import ndx_original_eight_tsm_scoring_history_research as m
from test_ndx_multidecision_scoring_history_research import fixture as parent_fixture,bind


def fixture():
    a=parent_fixture();a.pop('outer_inventory_contract')
    a['bridge_row']['ticker']='TSM';a['receipt']['ticker']='TSM'
    body=json.loads(a['raw_bytes']);body['chart']['result'][0]['meta']['symbol']='TSM';bind(a,body)
    securities=[dict(ticker=t,security_id='security:'+t,issuer_id='issuer:'+t,risk_chain='chain',target_weight=0.125) for t in m.CONTROL_ORDER]
    securities[4].update(security_id='security:incumbent_overlay:TSM',issuer_id='issuer:0001046179')
    a['original_control_contract']=dict(role=m.ROLE,control_reference=dict(path='control',sha256='c'*64),securities=securities,selected_security_id=securities[4]['security_id'],identity_evidence=[dict(path='identity',sha256='d'*64)],risk_evidence=[])
    return a


class ControlTests(unittest.TestCase):
    def test_independent_constant_split_numbers_and_preservation(self):
        a=fixture();before=deepcopy(a);r=m.materialize_tsm_control_history(**a)
        self.assertEqual(a,before);self.assertEqual(r['original_control_contract'],a['original_control_contract'])
        self.assertEqual(r['role'],m.ROLE);self.assertFalse(r['ndx_candidate_admitted']);self.assertFalse(r['holdings_or_ads_converted'])
        self.assertFalse(r['source_bytes_authenticated']);self.assertNotIn('outer_inventory_contract',r)
        self.assertEqual(len(r['decisions']),6)
        for d in r['decisions']:
            self.assertEqual(len(d['required_price_dates']),505);self.assertEqual(len(d['windows']),13)
            for i,w in enumerate(d['windows']):
                self.assertEqual(w['relative_price_start'],i*21)
                self.assertEqual(w['evaluation_return_index_stop']-w['training_return_index_start'],252)
        for q in r['quote_rows']:
            expected=Fraction(405,4) if q['session']<'2026-06-12' else Fraction(81,8)
            self.assertEqual(Fraction(q['nominal_close_exact']),expected)
        self.assertTrue(all(Fraction(x['split_only_return_exact'])==0 for x in r['return_rows']))

    def test_floor_and_missing_do_not_compress_or_score(self):
        a=fixture();a['bridge_row']['event_policy_bridge']['regular_floor']='2025-02-24'
        r=m.materialize_tsm_control_history(**a)
        self.assertEqual(len(r['return_rows']),len(r['calendar'])-1)
        self.assertTrue(any(x['split_only_return_exact'] is None for x in r['return_rows']))
        self.assertEqual(sum(len(d['windows']) for d in r['decisions']),78)
        self.assertFalse(r['score_computed']);self.assertFalse(r['unequal_window_pooling_allowed'])
        a=fixture();b=json.loads(a['raw_bytes']);i=a['reference_calendar'].index('2026-03-31');b['chart']['result'][0]['indicators']['quote'][0]['close'][i]=None;bind(a,b)
        r=m.materialize_tsm_control_history(**a);self.assertEqual(r['decisions'][0]['windows'][-1]['status'],'BLOCKED_WINDOW')

    def test_wrong_roles_identity_inventory_and_receipt_rejected(self):
        for mutate in [lambda a:a['original_control_contract'].update(role='NDX_CANDIDATE'),lambda a:a['original_control_contract']['securities'].pop(),lambda a:a['original_control_contract']['securities'][4].update(issuer_id='issuer:fund'),lambda a:a['original_control_contract'].update(selected_security_id='security:TSM'),lambda a:a['bridge_row'].update(ticker='GOOG'),lambda a:a['receipt'].update(ticker='GOOG'),lambda a:a['original_control_contract'].update(security_count=77),lambda a:a['original_control_contract']['securities'][0].update(target_weight=True)]:
            a=fixture();mutate(a)
            with self.assertRaises((ValueError,KeyError)):m.materialize_tsm_control_history(**a)

if __name__=='__main__':unittest.main()
