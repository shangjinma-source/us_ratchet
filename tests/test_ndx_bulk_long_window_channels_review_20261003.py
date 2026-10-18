"""Independent synthetic arithmetic oracle; no saved channel reconstruction."""
from copy import deepcopy
from decimal import Context,Inexact,localcontext
from fractions import Fraction
import gzip
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('long_channels_fixture',ROOT/'tests/test_ndx_bulk_long_window_channels_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);m=f.m

class Review(unittest.TestCase):
 def test_two_later_factors_and_all_252_exact_returns(self):
  a=f.fixture()
  def change(c):
   times=c['timestamp'];c['events']['splits'][str(times[-1])]=dict(date=times[-1],numerator=3,denominator=2,splitRatio='3:2')
   q=c['indicators']['quote'][0]
   for i in range(253):q['open'][i]=10+i/100;q['close'][i]=10+(i+1)/100;q['high'][i]=20;q['low'][i]=1
  f.modify_raw(a,change);body=json.loads(a['raw_bytes']);c=body['chart']['result'][0];splits=c['events']['splits'];a['bridge_row']['new_returned_splits']=deepcopy(splits)
  a['bridge_row']['event_policy_bridge']['events'].append(dict(provider_event_key=str(c['timestamp'][-1]),session='2026-09-22',status='SPECIFIC_POLICY_MATCH',specific_event_reference=dict(path='later',sha256='c'*64),policy=dict(session='2026-09-22',numerator=3,denominator=2,kind='ORDINARY_SPLIT')))
  out=m.reconstruct_long_channel(**a);q=c['indicators']['quote'][0]
  for i,row in enumerate(out['quote_rows']):
   factor=Fraction(3) if i<150 else Fraction(3,2)
   self.assertEqual(Fraction(row['split_factor_exact']),factor)
   self.assertEqual(Fraction(row['nominal_close_exact']),Fraction(str(q['close'][i]))*factor)
  for i,row in enumerate(out['return_rows'],1):
   expected=Fraction(str(q['close'][i]))/Fraction(str(q['close'][i-1]))-1
   self.assertEqual(Fraction(row['split_only_return_exact']),expected);self.assertEqual(row['split_only_return_float'],float(expected));self.assertFalse(row['dividends_included'])
  self.assertEqual(out['training_returns'],out['return_rows'][:126]);self.assertEqual(out['evaluation_returns'],out['return_rows'][126:]);self.assertEqual(len(out['return_rows']),252)

 def test_gzip_transport_distinct_and_no_context_dependence(self):
  a=f.fixture();baseline=m.reconstruct_long_channel(**a);decoded=a['raw_bytes'];a['raw_bytes']=gzip.compress(decoded,mtime=0)
  h=m.sha(a['raw_bytes']);a['raw_reference']['sha256']=h;a['bridge_row']['new_raw_reference']=deepcopy(a['raw_reference']);a['receipt'].update(raw_sha256=h,raw_bytes=len(a['raw_bytes']))
  ctx=Context(prec=2);ctx.traps[Inexact]=True
  with localcontext(ctx):out=m.reconstruct_long_channel(**a)
  self.assertEqual(out['quote_rows'],baseline['quote_rows']);self.assertEqual(out['decoded_sha256'],m.sha(decoded));self.assertNotEqual(out['decoded_sha256'],h)
  a['bridge_row']['new_decoded_sha256']=h
  with self.assertRaises(ValueError):m.reconstruct_long_channel(**a)

 def test_missing_freeze_date_floor_and_policy_denominator(self):
  a=f.fixture()
  def remove(c):
   c['timestamp'].pop(126)
   for array in c['indicators']['quote'][0].values():array.pop(126)
  f.modify_raw(a,remove);out=m.reconstruct_long_channel(**a)
  self.assertEqual(out['calendar'],a['calendar253']);self.assertEqual(out['missing_price_dates'],[a['calendar253'][126]]);self.assertIsNone(out['return_rows'])
  a=f.fixture();a['bridge_row']['event_policy_bridge']['regular_floor']=a['calendar253'][0]
  self.assertEqual(m.reconstruct_long_channel(**a)['status'],'CONDITIONAL_NUMERIC_RESULT')
  a['bridge_row']['event_policy_bridge']['regular_floor']=a['calendar253'][1]
  self.assertEqual(m.reconstruct_long_channel(**a)['status'],'BLOCKED_PRICE_INPUT')
  a=f.fixture();a['bridge_row']['event_policy_bridge']['events']=[]
  with self.assertRaises(ValueError):m.reconstruct_long_channel(**a)

 def test_invalid_numeric_metadata_and_receipt_fail(self):
  mutations=[lambda a:f.modify_raw(a,lambda c:c['indicators']['quote'][0]['open'].__setitem__(0,True)),lambda a:f.modify_raw(a,lambda c:c['timestamp'].__setitem__(1,c['timestamp'][0])),lambda a:f.modify_raw(a,lambda c:c['meta'].update(exchangeTimezoneName='UTC')),lambda a:a['receipt'].update(received_at_utc='2026-09-23T12:00:00'),lambda a:a['receipt'].update(raw_bytes=True),lambda a:a['bridge_row']['event_policy_bridge']['events'][0]['policy'].update(kind='DIVIDEND_AS_SPLIT')]
  for mutate in mutations:
   a=f.fixture();mutate(a)
   with self.assertRaises(ValueError):m.reconstruct_long_channel(**a)

if __name__=='__main__':unittest.main()
