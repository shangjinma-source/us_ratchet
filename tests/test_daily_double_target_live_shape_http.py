"""Two-stock quantities mirror live 13/52; synthetic A/B evidence, never live signals.
Exercises real SMA20 verifier, SQLite ledger, execution provider, difference and HTTP.
Does not claim to revalidate the live monthly selector/profile publication.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
import test_daily_composition_v3 as fixtures

class DoubleTargetHTTPTests(unittest.TestCase):
 def case(self,folder,cash='0'):
  c=fixtures.CompositionTests().setup_case(folder,held='A');root=Path(folder)
  # Explicit hypothetical monthly portfolio at the monthly->daily boundary.
  quantities={'A':13,'B':52}
  payload=c.target['payload'];payload['target_quantities']=quantities
  decision=payload['decision'];decision['payload']['target_quantities']=quantities
  binding=decision['payload']['input_binding']
  binding['historical_search_arguments']['metadata']['A']={'ticker':'AAA','issuer_id':'IA'}
  decision['payload']['input_id']=sha256(canonical(binding)).hexdigest()
  decision['decision_id']=sha256(canonical(decision['payload'])).hexdigest()
  c.target['target_id']=sha256(canonical(payload)).hexdigest()
  inputs=json.loads((root/'normalized.json').read_bytes());inputs['base_target']['quantities']=quantities
  raw=canonical(inputs);(root/'normalized.json').write_bytes(raw)
  receipt=json.loads((root/'parent.json').read_bytes());receipt['target_id']=c.target['target_id'];receipt['source_sha256']['normalized.json']=sha256(raw).hexdigest()
  body=canonical(receipt);(root/'parent.json').write_bytes(body)
  c.reader=ArchivedRebindingDailyEvidenceReader(root=root,archive_root=root/'archive',parent_receipt_path='parent.json',trusted_parent_sha256=sha256(body).hexdigest(),source_paths={name:name for name in receipt['source_sha256']},release_path='release.json',trusted_release_sha256=sha256((root/'release.json').read_bytes()).hexdigest(),calendar_path='calendar.json')
  c.service.reader=c.reader
  if cash!='0':
   c.store.append(dict(event_id='test-cash',kind='CASH_CONFIRM',amount=cash,cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
  from data.strategy_account_market_capture import StrategyAccountMarketCapture
  from datetime import datetime
  class Identity:
   def __call__(self,ticker):return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
   def _read(self,*args):return b'id'
  def minute_raw(ticker):
   opening=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp());last=opening+1800
   return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=list(range(opening,last,60)),indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
  c.provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=minute_raw,clock=lambda:c.clock[0],max_mark_age=120)
  c.state=c.store.read();return c
 def response(self,c):
  c.state=c.store.read();before=c.store.path.read_bytes();target=deepcopy(c.target)
  response=fixtures.CompositionTests().post(c)
  self.assertEqual(response.status_code,200,response.text);result=response.json()
  self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.target,target)
  self.assertEqual(result['effective_target_quantities'],{'A':6,'B':26},result)
  return result
 def test_zero_cash_sells_eight_and_does_not_spend_unfilled_sale(self):
  with TemporaryDirectory() as folder:
   c=self.case(folder);r=self.response(c)
   self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in r['new_orders']],[('A','SELL',8)])
   self.assertEqual(r['waiting_cash'][0]['security_id'],'B');self.assertEqual(r['waiting_cash'][0]['quantity'],26)
   self.assertEqual(r['difference']['new_buy_cash_required'],'0')
   self.assertEqual(r['execution_quantities'],{'A':6,'B':0})
 def test_funded_both_directions_and_repeat_after_fills_holds(self):
  with TemporaryDirectory() as folder:
   c=self.case(folder,'1000');r=self.response(c)
   self.assertEqual({(o['security_id'],o['side'],o['quantity']) for o in r['new_orders']},{('A','SELL',8),('B','BUY',26)})
   for sid,side,quantity in [('A','SELL',8),('B','BUY',26)]:
    identity=dict(ticker='AAA' if sid=='A' else 'BBB',security_id=sid,source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
    c.store.append(dict(event_id='actual-fixture-fill-'+sid,kind='DIRECT_FILL',security_id=sid,side=side,quantity=quantity,price='10',fees='0',executed_at=c.clock[0].isoformat(),identity_evidence=identity),expected_revision=c.store.read()['revision'])
   c.store.append(dict(event_id='after-fills-cash',kind='CASH_CONFIRM',amount='0',cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
   r=self.response(c);self.assertEqual(r['status'],'HOLD');self.assertEqual(r['new_orders'],[])
   r=self.response(c);self.assertEqual(r['status'],'HOLD');self.assertEqual(r['new_orders'],[])
if __name__=='__main__':unittest.main()
