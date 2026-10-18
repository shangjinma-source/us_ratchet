"""Independent saved-state financial/provenance review; no fit/account replay."""
from pathlib import Path
from fractions import Fraction
import json
import math
import unittest
from unittest.mock import patch
from backtest import ndx_modern_new_cash_inputs_research as loader


def resolve(document, pointer):
    result=document
    for item in pointer.split('/')[1:]:
        item=item.replace('~1','/').replace('~0','~')
        result=result[int(item)] if isinstance(result,list) else result[item]
    return result


class IndependentModernCashTests(unittest.TestCase):
    def test_all_frozen_states_original_holdings_and_independent_risk(self):
        reads=[];real=Path.read_bytes
        allowed={str(loader.ROOT/p)for p,h in (*loader.BOUND.values(),*loader.EXECUTION_BOUND.values())}
        allowed.add(str(loader.ROOT/loader.RISK_PATH))
        allowed.update(str(loader.ROOT/f'data/cache/research/multidecision_account_execution_20261003_v1/tracks/{i:02d}/raw_result.json')for i in range(8,16))
        def fixed_read(path):
            self.assertIn(str(path),allowed);reads.append(str(path));return real(path)
        with patch.object(Path,'read_bytes',fixed_read):
            projected=loader.load_historical_frozen_states()
        inputs=json.loads(real(loader.ROOT/loader.BOUND['inputs'][0]));states=0;risks=0
        self.assertEqual(len(projected['coordinates_preserved']),48)
        self.assertEqual(len(projected['historical_execution_tracks']),16)
        for track in projected['historical_execution_tracks']:
            i=track['track_index'];self.assertEqual(len(track['historical_decision_states']),0 if i<8 else 6)
            for st in track['historical_decision_states']:
                raw=json.loads(real(Path(st['raw_reference']['path'])));original=resolve(raw,st['state_pointer']);states+=1
                self.assertEqual(st['original_state_preserved'],original)
                self.assertEqual(st['cash_usd'],original['cash_usd']);self.assertEqual(st['session'],original['session'])
                self.assertEqual(st['shares'],original['shares'] if track['track']=='WHOLE_LOT' else {sid:h['shares']for sid,h in original['holdings'].items()})
                self.assertEqual(st['state_role'],'HISTORICAL_OWN_ACCOUNT_FROZEN_STATE_NOT_CURRENT_BROKER')
                if track['track']=='CONTINUOUS':
                    self.assertIsNone(st['conditional_original_risk_recheck']);self.assertIsNone(st['saved_account_marks']);continue
                self.assertEqual(st['saved_account_marks'],original['prices']);self.assertEqual(st['risk_chains'],original['risk_chains'])
                if not original['shares']:continue
                amounts={sid:q*float(original['prices'][sid])for sid,q in original['shares'].items()};total=sum(amounts.values());weights={sid:v/total for sid,v in amounts.items()};ordered=sorted(weights.values(),reverse=True);chains={}
                for sid,w in weights.items():chains[original['risk_chains'][sid]]=chains.get(original['risk_chains'][sid],0.)+w
                eff=1/sum(w*w for w in ordered)
                checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=.45+1e-9,MIN_SINGLE_WEIGHT=ordered[-1]>=.05-1e-9,SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=.8+1e-9,MINIMUM_EFFECTIVE_N=eff>=.7*len(ordered)-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=.55+1e-9)
                expected=dict(checks=checks,all_passed=all(checks.values()),actual_weights=dict(sorted(weights.items())),top1_weight=ordered[0],minimum_single_weight=ordered[-1],top3_weight=sum(ordered[:3]),effective_n=eff,risk_chain_top1_weight=max(chains.values()))
                self.assertEqual(expected,original['risk']);self.assertEqual(expected,st['conditional_original_risk_recheck']['result']);risks+=1
        self.assertEqual(states,48);self.assertGreater(risks,0)
        for lane in projected['lanes']:
            for decision in lane['decisions']:
                self.assertEqual(len(resolve(inputs,decision['targets_pointer'])),decision['target_count'])
                for p in decision['prices']:
                    self.assertEqual(resolve(inputs,p['account_matrix_pointer']),p['value']);q=resolve(inputs,p['quote_projection_pointer']);self.assertEqual(q['json_pointer'],p['source_json_pointer']);self.assertEqual(float(Fraction(q['exact'])).hex(),p['binary64_hex']);self.assertIsNone(p['price_available_at'])
        for flag in loader.FLAGS:self.assertIs(projected[flag],False)
        self.assertEqual(projected['plan_rows'],[]);self.assertIsNone(projected['current_account']);self.assertIsNone(projected['current_new_money'])

    def test_invalid_risk_inputs_fail_before_fixed_source_read(self):
        cases=[dict(shares={'A':v},marks={'A':20},chains={'A':'x'})for v in [True,False,1.5,0,-1]]
        cases += [dict(shares={'A':1},marks={'A':v},chains={'A':'x'})for v in [True,float('nan'),float('inf'),0,-1]]
        cases += [dict(shares={'A':1},marks={'B':20},chains={'A':'x'}),dict(shares={'A':1},marks={'A':20},chains={'A':' x'}),dict(shares={},marks={},chains={})]
        for case in cases:
            with self.subTest(case=case),patch.object(loader,'_read',side_effect=AssertionError('invalid risk reached IO')),self.assertRaises(ValueError):loader.recheck_conditional_whole_lot_risk(**case)

if __name__=='__main__':unittest.main()
