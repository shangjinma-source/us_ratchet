from copy import deepcopy
from decimal import Context,Inexact,localcontext
from fractions import Fraction
import unittest
from backtest import ndx_original_eight_tsm_scoring_history_research as m
from test_ndx_original_eight_tsm_scoring_history_research import fixture
class Review(unittest.TestCase):
 def test_preserves_literal_control_weights_zero_and_retrospective_role(self):
  a=fixture();a['original_control_contract']['securities'][0]['target_weight']='0.12500000000000003';a['original_control_contract']['securities'][1]['target_weight']=0;before=deepcopy(a)
  ctx=Context(prec=2);ctx.traps[Inexact]=True
  with localcontext(ctx):r=m.materialize_tsm_control_history(**a)
  self.assertEqual(a,before);self.assertEqual(r['original_control_contract'],before['original_control_contract']);self.assertFalse(r['ndx_candidate_admitted']);self.assertFalse(r['holdings_or_ads_converted']);self.assertTrue(all(r[k]is False for k in m.FLAGS))
  for q in r['quote_rows']:self.assertEqual(Fraction(q['nominal_close_exact']),Fraction(81,8)*(10 if q['session']<'2026-06-12'else 1))
 def test_distinct_order_type_and_tsm_join_fail_closed(self):
  for attack in (lambda a:a['original_control_contract']['securities'].reverse(),lambda a:a['original_control_contract']['securities'][0].update(security_id='security:incumbent_overlay:TSM'),lambda a:a['original_control_contract']['securities'][4].update(target_weight=float('nan')),lambda a:a['original_control_contract']['securities'][4].update(target_weight=False),lambda a:a['original_control_contract'].update(role='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE '),lambda a:a['window_contract'].update(price_count_per_decision=253)):
   a=fixture();attack(a)
   with self.assertRaises(ValueError):m.materialize_tsm_control_history(**a)
if __name__=='__main__':unittest.main()
