from copy import deepcopy
import unittest
from backtest import ndx_multidecision_liquidity_inputs_v2_research as m
import test_ndx_multidecision_liquidity_inputs_research as prior

def fixture():
    a=prior.fixture()
    for r in a['channels_document']['rows']:r['channel']['returned_event_encoding']=m.ENCODING
    return a

class Tests(unittest.TestCase):
    def test_actual_minimal_pcar_pair(self):
        a=fixture();c=a['channels_document']['rows'][0]['channel'];saved={'1675866600':{'date':1675866600,'denominator':'2.0','numerator':'3.0','splitRatio':'3:2'}};bridge={'1675866600':{'date':1675866600,'denominator':2.0,'numerator':3.0,'splitRatio':'3:2'}}
        c['returned_events']['splits']=deepcopy(saved);c['bridge_row_preserved']['new_returned_splits']=deepcopy(bridge)
        p=dict(session='2023-02-08',kind='ORDINARY_SPLIT',numerator=3,denominator=2);c['event_policies']=[p];c['bridge_row_preserved']['event_policy_bridge']['events']=[dict(session=p['session'],provider_event_key='1675866600',policy=deepcopy(p))]
        before=deepcopy(a);out=m.prepare_decision_liquidity(**a);self.assertEqual(a,before);self.assertEqual(out['periods'][0]['rows'][0]['status'],'CONDITIONAL_MDV_COMPUTABLE');self.assertEqual(out['recovery_evidence_references'],m.RECOVERY_REFERENCES)
        evidence=out['channel_action_and_source_evidence'][0];self.assertEqual(evidence['returned_events']['splits'],saved);self.assertEqual(evidence['bridge_row_preserved']['new_returned_splits'],bridge)
    def test_narrow_typed_encoding_not_ratio_tolerance(self):
        s={'1675866600':dict(date=1675866600,numerator='3.0',denominator='2.0',splitRatio='3:2')};b={'1675866600':dict(date=1675866600,numerator=3.0,denominator=2.0,splitRatio='3:2')}
        for modify in [lambda x:x['1675866600'].update(numerator='6.0',denominator='4.0'),lambda x:x['1675866600'].update(date='1675866600'),lambda x:x['1675866600'].update(numerator=True),lambda x:x['1675866600'].update(numerator='NaN'),lambda x:x['1675866600'].update(extra='x'),lambda x:x['1675866600'].update(splitRatio='6:4'),lambda x:x.update(other=x['1675866600'])]:
            bad=deepcopy(s);modify(bad)
            with self.assertRaises(ValueError):m.compare_split_representations(bad,b,m.ENCODING)
        with self.assertRaises(ValueError):m.compare_split_representations(s,b,'UNDECLARED')
    def test_causal_and_recovery_conflict(self):
        a=fixture();before=m.prepare_decision_liquidity(**a);c=a['channels_document']['rows'][0]['channel'];c['quote_rows'][-1]['raw_volume']=987654;c['quote_rows_sha256']=m.digest(c['quote_rows']);self.assertEqual(before['periods'][0],m.prepare_decision_liquidity(**a)['periods'][0])
        r=m.RECOVERY_REFERENCES['prior_core'];a['channels_document']['source_hashes'][r['path']]='0'*64
        with self.assertRaises(ValueError):m.prepare_decision_liquidity(**a)
    def test_unchanged_existing_arithmetic_guards(self):
        a=fixture();j=a['channels_document']['calendar253'].index(a['decision_contract']['document']['decisions'][0]['decision_date']);c=a['channels_document']['rows'][0]['channel'];c['quote_rows'][j]['raw_volume']=False;c['quote_rows_sha256']=m.digest(c['quote_rows'])
        with self.assertRaises(ValueError):m.prepare_decision_liquidity(**a)
