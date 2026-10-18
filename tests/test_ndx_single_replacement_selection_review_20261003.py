import copy,unittest
from backtest import ndx_single_replacement_selection_research as m
from test_ndx_single_replacement_selection_research import fixture
class Tests(unittest.TestCase):
 def test_small_case_exact_tie_order_and_detached_winner(self):
  a=fixture();items=a['records'];first=[r for r in items if r['task']['scenario_index']==0]
  for r in first:r['evaluation'].update(original_target_stock_l1='3/7',total_fee_usd='1/10',sell_fee_usd='1/25',buy_fee_usd='3/50')
  expected=copy.deepcopy(next(r for r in first if r['task']['identity']['outgoing_security_id']=='A'and r['task']['identity']['incoming_security_id']=='C'and r['task']['identity']['buy_quantity']==1))
  result=m.select_complete_single_replacements(**a)['document'];self.assertEqual(result['rows'][0]['selected'],expected)
  first[0]['evaluation']['original_target_stock_l1']='999';self.assertEqual(result['rows'][0]['selected'],expected)
  for r in first:r['evaluation'].update(original_target_stock_l1='3/7',total_fee_usd='1/10',sell_fee_usd='1/25',buy_fee_usd='3/50')
  winner=first[-1];winner['evaluation'].update(original_target_stock_l1='2/7',total_fee_usd='100',sell_fee_usd='50',buy_fee_usd='50')
  self.assertEqual(m.select_complete_single_replacements(**a)['document']['rows'][0]['selected']['task']['task_id'],winner['task']['task_id'])
 def test_last_missing_duplicate_and_technical_never_returns_prefix(self):
  for mode in ('last','duplicate','technical'):
   a=fixture()
   if mode=='last':a['records']=iter(a['records'][:-1])
   elif mode=='duplicate':a['records'][-1]=copy.deepcopy(a['records'][-2])
   else:a['readback']['partition']['outcome_counts']['VALIDATION_FAILURE']=1
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.select_complete_single_replacements(**a)
 def test_iterator_cannot_replace_validated_metadata_in_result(self):
  a=fixture();original_scope=copy.deepcopy(a['prepared']['document']['scope']);items=a['records']
  def records():
   for i,row in enumerate(items):
    if i==1:a['prepared']['document']['scope']='UNREGISTERED_REPLACEMENT_SCOPE'
    yield row
  a['records']=records()
  try:result=m.select_complete_single_replacements(**a)
  except ValueError:return
  self.assertEqual(result['document']['scope'],original_scope)
if __name__=='__main__':unittest.main()
