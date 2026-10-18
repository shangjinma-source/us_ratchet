from copy import deepcopy
from fractions import Fraction
import hashlib,json,unittest
from backtest import ndx_multidecision_scoring_history_inspection_research as reader
from test_ndx_multidecision_scoring_history_inspection_research import saved_case

def checksum(d):
 def h(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 d['quote_rows_sha256']=h(d['quote_rows']);d['return_rows_sha256']=h(d['return_rows']);d['content_sha256']=h({k:v for k,v in d.items() if k!='content_sha256'})

class Review(unittest.TestCase):
 def test_independent_constant_price_and_all_window_endpoints(self):
  args,saved=saved_case();raw=json.loads(args['raw_bytes']);cal=args['reference_calendar'];q=raw['chart']['result'][0]['indicators']['quote'][0]
  self.assertTrue(all(Fraction(str(v))==Fraction(81,8) for v in q['close']))
  for row in saved['quote_rows']:
   factor=10 if row['session']<'2026-06-12' else 1
   self.assertEqual(Fraction(row['nominal_close_exact']),Fraction(81,8)*factor)
  self.assertTrue(all(Fraction(r['split_only_return_exact'])==0 for r in saved['return_rows']))
  for period in saved['decisions']:
   last=cal.index(period['cutoff']);first=last-504
   self.assertEqual(period['required_price_dates'],cal[first:last+1])
   for n,w in enumerate(period['windows']):
    self.assertEqual(w['training_price_predecessor'],cal[first+21*n]);self.assertEqual(w['training_freeze_close'],cal[first+21*n+126]);self.assertEqual(w['evaluation_last_return_end'],cal[first+21*n+252])
  self.assertEqual(reader.inspect_scoring_history_channel(saved_channel=saved,**args)['window_count'],78)
 def test_resealed_false_authority_source_and_window_pooling(self):
  args,saved=saved_case()
  attacks=[lambda d:d.update(source_bytes_authenticated=0),lambda d:d['receipt_reference'].update(path='foreign'),lambda d:d['bridge_row_preserved']['event_policy_bridge']['events'][0]['specific_event_reference'].update(path='other'),lambda d:d['decisions'][1].update(windows=deepcopy(d['decisions'][0]['windows'])),lambda d:d['decisions'][0]['windows'].pop(),lambda d:d['quote_rows'][0].update(split_factor_exact='1'),lambda d:d['return_rows'][0].update(split_only_return_exact='1/1000',split_only_return_float=.001)]
  for attack in attacks:
   with self.subTest(attack=attack):
    bad=deepcopy(saved);attack(bad);checksum(bad)
    with self.assertRaises(ValueError):reader.inspect_scoring_history_channel(saved_channel=bad,**args)
 def test_bridge_whole_fields_types_and_missing_raw_cannot_be_hidden(self):
  args,saved=saved_case();eventkey=next(iter(args['bridge_row']['new_returned_splits']))
  for mode in ('key','bool','ratio','extra','date_missing'):
   a=deepcopy(args)
   if mode=='key':a['bridge_row']['new_returned_splits']['wrong']=a['bridge_row']['new_returned_splits'].pop(eventkey)
   elif mode=='bool':a['bridge_row']['new_returned_splits'][eventkey]['denominator']=True
   elif mode=='ratio':a['bridge_row']['new_returned_splits'][eventkey].update(numerator=20,denominator=2,splitRatio='20:2')
   elif mode=='extra':a['bridge_row']['new_returned_splits'][eventkey]['unreviewed']='x'
   else:
    raw=json.loads(a['raw_bytes']);c=raw['chart']['result'][0];i=a['reference_calendar'].index('2026-04-01');c['timestamp'].pop(i)
    for values in c['indicators']['quote'][0].values():values.pop(i)
    b=json.dumps(raw).encode();h=hashlib.sha256(b).hexdigest();a['raw_bytes']=b;a['raw_reference']['sha256']=h;a['receipt'].update(raw_sha256=h,raw_bytes=len(b));a['bridge_row']['new_raw_reference']=deepcopy(a['raw_reference']);a['bridge_row']['new_decoded_sha256']=h
   with self.subTest(mode=mode):
    with self.assertRaises(ValueError):reader.inspect_scoring_history_channel(saved_channel=saved,**a)
if __name__=='__main__':unittest.main()
