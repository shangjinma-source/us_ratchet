from copy import deepcopy
import unittest
from fractions import Fraction
from backtest import ndx_multidecision_liquidity_inputs_research as m
from test_ndx_multidecision_training_inputs_research import fixture as training_fixture

def fixture():
    a=training_fixture();s=a['channels_document'];s['source_hashes']={};s['volume_unit_certified']=False
    parent=dict(path='parent-panel.json',sha256='9'*64);s.setdefault('input_references',{})['panel']=parent;s['source_hashes'][parent['path']]=parent['sha256']
    s['preserved_sidecar_references']={name:dict(parent,json_pointer='/'+name) for name in m.SIDECARS}
    for i,r in enumerate(s['rows']):
        c=r['channel'];c.update(volume_unit_verified=False,liquidity_qualified=False,regular_floor=None)
        raw=dict(path=f'raw{i}',sha256='a'*64);receipt=dict(path=f'receipt{i}',sha256='b'*64)
        c.update(raw_reference=raw,receipt_reference=receipt,returned_events={'splits':{}},event_policies=[],bridge_row_preserved=dict(new_raw_reference=deepcopy(raw),new_receipt_reference=deepcopy(receipt),new_returned_splits={},event_policy_bridge={'events':[]}))
        s['source_hashes'].update({raw['path']:raw['sha256'],receipt['path']:receipt['sha256']})
        c['quote_rows']=[dict(session=d,nominal_close_exact=str(50000000+j),raw_volume=1) for j,d in enumerate(s['calendar253'])];c['quote_rows_sha256']=m.digest(c['quote_rows'])
    return dict(channels_document=s,channels_reference=a['channels_reference'],channels_readback_reference=dict(path='audit',sha256='c'*64),full_inventory=a['expected_security_inventory'],decision_contract=dict(document=a['decision_path_contract'],reference=a['decision_path_reference']),liquidity_contract=dict(m.CONTRACT,source_reference=dict(path='repo/backtest/ndx_conditional_channel_input_research.py',sha256=m.SOURCE_SHA)))

def add_event(a,day):
    c=a['channels_document']['rows'][0]['channel'];p=dict(session=day,kind='ORDINARY_SPLIT',numerator=25,denominator=1)
    c['event_policies']=[p];c['returned_events']['splits']={'event':dict(numerator=25,denominator=1)}
    c['bridge_row_preserved']['new_returned_splits']=deepcopy(c['returned_events']['splits'])
    c['bridge_row_preserved']['event_policy_bridge']['events']=[dict(session=day,provider_event_key='event',policy=deepcopy(p))]

class Tests(unittest.TestCase):
    def test_exact_median_full_inventory_and_unchanged(self):
        a=fixture();before=deepcopy(a);out=m.prepare_decision_liquidity(**a);self.assertEqual(a,before)
        for period in out['periods']:
            j=a['channels_document']['calendar253'].index(period['decision_date']);self.assertEqual(len(period['rows']),4)
            r=period['rows'][0];self.assertEqual(r['median_dollar_volume_exact'],str(50000000+j-31));self.assertEqual(len(r['quote_evidence']),63);self.assertTrue(r['conditional_numerical_threshold_passed'])
        self.assertEqual(len(out['original_provenance_and_missing']),101);self.assertEqual(len(out['preserved_evidence_sidecars']),7)
        self.assertTrue(all(out[k] is False for k in m.FLAGS))
    def test_future_quotes_ignored_but_future_split_blocks(self):
        a=fixture();out=m.prepare_decision_liquidity(**a);c=a['channels_document']['rows'][0]['channel'];c['quote_rows'][-1].update(nominal_close_exact='99999999999999999999',raw_volume=999999999);c['quote_rows_sha256']=m.digest(c['quote_rows'])
        self.assertEqual(out['periods'][0],m.prepare_decision_liquidity(**a)['periods'][0])
        add_event(a,a['channels_document']['calendar253'][-1]);r=m.prepare_decision_liquidity(**a)['periods'][0]['rows'][0];self.assertEqual(r['status'],'UNKNOWN_LIQUIDITY');self.assertIsNone(r['median_dollar_volume_exact']);self.assertIsNone(r['conditional_numerical_threshold_passed'])
    def test_exact_fraction_threshold_and_missing_preserved(self):
        a=fixture();c=a['channels_document']['rows'][0]['channel']
        for r in c['quote_rows']:r['nominal_close_exact']='149999999/3'
        c['quote_rows_sha256']=m.digest(c['quote_rows']);r=m.prepare_decision_liquidity(**a)['periods'][0]['rows'][0];self.assertEqual(r['median_dollar_volume_exact'],'149999999/3');self.assertFalse(r['conditional_numerical_threshold_passed'])
        j=a['channels_document']['calendar253'].index(a['decision_contract']['document']['decisions'][0]['decision_date']);c['quote_rows'][j]['raw_volume']=None;c['quote_rows_sha256']=m.digest(c['quote_rows']);r=m.prepare_decision_liquidity(**a)['periods'][0]['rows'][0];self.assertIn('MISSING_RAW_VOLUME',r['reasons']);self.assertIsNone(r['median_dollar_volume_exact'])
    def test_holes_bool_and_source_conflicts(self):
        for change in [lambda a:a['channels_document']['rows'][0]['channel']['quote_rows'].pop(130),lambda a:a['channels_document']['rows'][0]['channel']['quote_rows'][130].update(raw_volume=True),lambda a:a['liquidity_contract'].update(lookback_sessions=True),lambda a:a['channels_document']['rows'][0]['channel']['raw_reference'].update(sha256='e'*64),lambda a:a['full_inventory'].pop(),lambda a:a['channels_document'].update(volume_unit_certified=0)]:
            a=fixture();change(a)
            for row in a['channels_document']['rows']:row['channel']['quote_rows_sha256']=m.digest(row['channel']['quote_rows'])
            with self.assertRaises(ValueError):m.prepare_decision_liquidity(**a)
