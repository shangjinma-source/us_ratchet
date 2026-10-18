"""Independent assembly checks; no actual prices, weights or accounts."""
from copy import deepcopy
from decimal import localcontext,Inexact
from fractions import Fraction
import unittest
from test_ndx_dated_account_input_research import fixture
from backtest import ndx_dated_account_input_research as m

class Review(unittest.TestCase):
    def test_original_sids_engine_aliases_and_exact_price_boundary(self):
        a=fixture();sid=next(iter(a['candidate_channels_by_security']));price='1234567890123456789012345678901/99999999999999999999999999'
        a['candidate_channels_by_security'][sid]['quote_rows'][126]['nominal_open_exact']=price
        before=deepcopy(a)
        with localcontext() as c:
            c.prec=2;c.traps[Inexact]=True;out=m.assemble_dated_account_inputs(**a)
        self.assertEqual(a,before)
        role=out['candidate'];self.assertEqual(set(role['schedule'][0]['targets']),set(a['task']['numerical_identity']['selected']))
        for s,t in role['schedule'][0]['targets'].items():
            self.assertIn(t['ticker'],role['matrices']['open']['columns']);self.assertEqual(t['ticker'],out['engine_security_keys'][s]);self.assertEqual(t['ticker'],t['ticker'].upper())
        self.assertEqual(role['corporate_actions'][0]['security_id'],sid)
        self.assertEqual(role['exact_quote_conversion_evidence'][sid][0]['open']['value'],float(Fraction(price)))
        self.assertEqual(role['exact_quote_conversion_evidence'][sid][0]['open']['float_hex'],float(Fraction(price)).hex())
        self.assertEqual([x['target_weight'] for x in out['incumbent']['schedule'][0]['targets'].values()],[x['target_weight'] for x in a['incumbent_securities']])

    def test_engine_alias_collision_and_control_mass_rejected(self):
        a=fixture();old=a['incumbent_securities'][0]['security_id'];new='security:1_BKNG';a['incumbent_securities'][0]['security_id']=new
        for key in ('incumbent_channels_by_security','channel_references','split_evidence_by_security'):a[key][new]=a[key].pop(old)
        with self.assertRaises(ValueError):m.assemble_dated_account_inputs(**a)
        a=fixture();a['incumbent_securities'][0]['target_weight']=.5
        with self.assertRaises(ValueError):m.assemble_dated_account_inputs(**a)

    def test_split_ratio_and_quote_integrity_fail_closed(self):
        for mode in ('ratio','boolprice','duplicate','pointer'):
            a=fixture();sid=next(iter(a['candidate_channels_by_security']));ch=a['candidate_channels_by_security'][sid]
            if mode=='ratio':a['split_evidence_by_security'][sid][0]['event']['new_shares']=True
            elif mode=='boolprice':ch['quote_rows'][-1]['nominal_close_exact']=True
            elif mode=='duplicate':ch['quote_rows'][-1]['session']=ch['quote_rows'][-2]['session']
            else:a['channel_references'][sid]['json_pointer']='not-a-pointer'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.assemble_dated_account_inputs(**a)

    def test_zero_target_preserved_but_dispatch_blocked(self):
        a=fixture();sids=list(a['fit_result']['targets']);a['fit_result']['targets'][sids[0]]['target_weight']=0;a['fit_result']['targets'][sids[1]]['target_weight']=1
        out=m.assemble_dated_account_inputs(**a);row=out['candidate']
        self.assertTrue(row['engine_input_status'].startswith('BLOCKED_'));self.assertTrue(row['engine_dispatch_blockers'])
        self.assertEqual(row['schedule'][0]['targets'][sids[0]]['target_weight'],0);self.assertEqual(len(row['matrices']['open']['columns']),2);self.assertFalse(row['account_executed'])

if __name__=='__main__':unittest.main()
