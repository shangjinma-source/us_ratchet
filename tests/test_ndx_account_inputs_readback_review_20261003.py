"""Independent source-and-output coordinated mutations, no actual accounts."""
from copy import deepcopy
import unittest
from scripts import ndx_multidecision_account_inputs_independent_readback_20261003 as r
from test_ndx_multidecision_account_inputs_independent_readback_20261003 import inputs, resign


def add_flow(x):
    key = r.MODES[1] + '|RETURN'
    event = dict(session='2026-04-02', amount_usd=1000., timing='BEFORE_OPEN', currency='USD',
        source_reference=dict(path='E:/synthetic/flow.json', sha256='a'*64))
    x['contract']['execution_contract']['cash_flow_role'] = 'EXPLICIT_NEW_CASH_RESEARCH'
    x['saved']['execution_contract_preserved']['cash_flow_role'] = 'EXPLICIT_NEW_CASH_RESEARCH'
    x['contract']['flows_by_lane'][key] = [deepcopy(event)]
    for tr in x['saved']['rows'][4]['tracks']:
        tr['stateful_input']['external_flows'] = [deepcopy(event)]
        tr['engine_binding']['keyword_arguments']['external_flows'] = [deepcopy(event)]
    x['saved']['source_hashes'][event['source_reference']['path']] = event['source_reference']['sha256']
    resign(x)
    return key


class Review(unittest.TestCase):
    def test_synchronized_source_flow_attack_cannot_be_certified(self):
        x = inputs(); key = add_flow(x)
        self.assertEqual(r.inspect_projection(**x)['status'], 'PASS')
        for field, value in [('currency','CNY'), ('timing','AFTER_CLOSE'), ('amount_usd',True), ('amount_usd','1000')]:
            with self.subTest(field=field, value=value):
                bad = deepcopy(x)
                bad['contract']['flows_by_lane'][key][0][field] = value
                for track in bad['saved']['rows'][4]['tracks']:
                    track['stateful_input']['external_flows'][0][field] = value
                    track['engine_binding']['keyword_arguments']['external_flows'][0][field] = value
                resign(bad)
                with self.assertRaises(ValueError): r.inspect_projection(**bad)

    def test_source_contract_authority_and_zero_role_cannot_hide_injection(self):
        x = inputs()
        for value in (True, 0):
            bad = deepcopy(x); bad['contract']['execution_authorized'] = value
            with self.assertRaises(ValueError): r.inspect_projection(**bad)
        bad = deepcopy(x); bad['contract']['schema'] = 'FOREIGN'
        with self.assertRaises(ValueError): r.inspect_projection(**bad)
        bad = inputs(); add_flow(bad)
        bad['contract']['execution_contract']['cash_flow_role'] = 'ZERO_FLOW_BASELINE'
        bad['saved']['execution_contract_preserved']['cash_flow_role'] = 'ZERO_FLOW_BASELINE'
        resign(bad)
        with self.assertRaises(ValueError): r.inspect_projection(**bad)

    def test_all_tracks_keep_slots_and_no_engine_misrouting(self):
        x = inputs(); baseline = deepcopy(x)
        self.assertEqual(r.inspect_projection(**x)['track_count'],16)
        self.assertEqual(x,baseline)
        for mode in ('missing_to_cash','tracks_swapped','fx_swapped','source_dropped'):
            bad=deepcopy(x)
            if mode=='missing_to_cash':
                tr=bad['saved']['rows'][0]['tracks'][0];tr['blocking_reasons']=[];tr['status']='ENGINE_INPUTS_PREPARED_NOT_EXECUTED'
            elif mode=='tracks_swapped':bad['saved']['rows'][4]['tracks'].reverse()
            elif mode=='fx_swapped':bad['saved']['rows'][4]['fx_mode']=r.MODES[0]
            else:bad['saved']['source_hashes'].pop(r.ENGINES[0]['path'])
            resign(bad)
            with self.subTest(mode=mode), self.assertRaises(ValueError):r.inspect_projection(**bad)


if __name__=='__main__':unittest.main()
