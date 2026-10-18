from datetime import datetime,timezone,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest,json
from core.strategy_account_ledger import create_account
from data.strategy_account_market_capture import StrategyAccountMarketCapture

class Identity:
 def __init__(self):self.changed=False
 def __call__(self,ticker):return dict(ticker=ticker,security_id=('WRONG' if self.changed else ticker),source_references=['id'],source_hashes={'id':sha256(b'identity').hexdigest()})
 def _read(self,path,h):return b'identity'

def raw(ticker):
 opening=int(datetime(2026,10,16,13,30,tzinfo=timezone.utc).timestamp())
 return json.dumps(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=opening+120,currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=[opening+60],indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))]))).encode()

class MarketTests(unittest.TestCase):
 def test_full_domain_saved_no_retry_and_no_account_mutation(self):
  with TemporaryDirectory() as d:
   state=create_account('a');identity=Identity();calls=[];now=datetime(2026,10,16,13,32,10,tzinfo=timezone.utc)
   def fetch(t):calls.append(t);return raw(t)
   provider=StrategyAccountMarketCapture(identity_resolver=identity,fetch=fetch,clock=lambda:now,max_workers=2)
   output=Path(d)/'capture';result=provider.capture(state=state,candidate_metadata={'A':{'ticker':'A'},'B':{'ticker':'B'}},output_directory=output)
   self.assertEqual(set(result['marks']),{'A','B'});self.assertFalse(result['unit_review_completed'])
   self.assertTrue((output/'complete.json').is_file());self.assertEqual(state,create_account('a'))
   for p,h in result['source_hashes'].items():self.assertEqual(sha256(result['files'][p]).hexdigest(),h)
   with self.assertRaises(FileExistsError):provider.capture(state=state,candidate_metadata={'A':{'ticker':'A'}},output_directory=output)
   self.assertEqual(len(calls),2)
 def test_failure_stale_and_identity_change_never_partial_success(self):
  for mode in ('missing','delay','identity'):
   with self.subTest(mode=mode),TemporaryDirectory() as d:
    now=[datetime(2026,10,16,13,32,10,tzinfo=timezone.utc)];identity=Identity()
    def fetch(t):
     if mode=='missing':raise OSError('transport')
     if mode=='delay':now[0]+=timedelta(seconds=180)
     if mode=='identity':identity.changed=True
     return raw(t)
    provider=StrategyAccountMarketCapture(identity_resolver=identity,fetch=fetch,clock=lambda:now[0],max_workers=1)
    output=Path(d)/'capture'
    with self.assertRaises(ValueError):provider.capture(state=create_account('a'),candidate_metadata={'A':{'ticker':'A'}},output_directory=output)
    self.assertTrue((output/'failed.json').is_file());self.assertFalse((output/'complete.json').exists())
    if mode!='missing':self.assertEqual(len(list(output.glob('*.raw'))),1)
 def test_identity_final_recheck_delay_cannot_return_expired_marks(self):
  with TemporaryDirectory() as d:
   now=[datetime(2026,10,16,13,32,10,tzinfo=timezone.utc)]
   class DelayedIdentity(Identity):
    calls=0
    def __call__(self,ticker):
     self.calls+=1
     if self.calls==2:now[0]+=timedelta(seconds=180)
     return super().__call__(ticker)
   output=Path(d)/'capture'
   provider=StrategyAccountMarketCapture(identity_resolver=DelayedIdentity(),fetch=raw,clock=lambda:now[0])
   with self.assertRaisesRegex(ValueError,'FINAL_MARK_EXPIRED'):
    provider.capture(state=create_account('a'),candidate_metadata={'A':{'ticker':'A'}},output_directory=output)
   self.assertFalse((output/'complete.json').exists());self.assertTrue((output/'failed.json').exists())
 def test_missing_held_identity_is_not_dropped(self):
  from core.strategy_account_ledger import apply_event
  state=create_account('a');state,_=apply_event(state,dict(event_id='fill',kind='DIRECT_FILL',security_id='HELD',side='BUY',quantity=1,price='10',fees='0',executed_at='2026-10-16T13:00:00Z'),expected_revision=state['revision'])
  with TemporaryDirectory() as d:
   output=Path(d)/'capture'
   provider=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=lambda _:self.fail('no fetch'))
   with self.assertRaisesRegex(ValueError,'HELD_OR_PENDING_IDENTITY_MISSING'):provider.capture(state=state,candidate_metadata={'A':{'ticker':'A'}},output_directory=output)
   self.assertFalse(output.exists())

 def test_departed_holding_still_quoted_and_sold_without_spending_pending_proceeds(self):
  from core.strategy_account_ledger import apply_event
  from data.strategy_account_preview import preview_scoped_account
  now=datetime(2026,10,16,13,32,10,tzinfo=timezone.utc)
  state=create_account('rotation-test');identity=Identity()
  def event(value):
   nonlocal state
   state,_=apply_event(state,value,expected_revision=state['revision'])
  event(dict(event_id='held',kind='DIRECT_FILL',security_id='HELD',side='BUY',quantity=14,
             price='10',fees='0',executed_at=now.isoformat(),identity_evidence=identity('HELD')))
  event(dict(event_id='pending-sale',kind='ORDER_OPEN',order_id='sale',security_id='HELD',
             side='SELL',quantity=4,limit_price='10',fee_per_share='0',identity_evidence=identity('HELD')))
  for partial in (False,True):
   if partial:event(dict(event_id='partial-sale',kind='FILL',order_id='sale',quantity=2,
                        price='10',fees='0',executed_at=now.isoformat()))
   event(dict(event_id='cash-'+str(partial),kind='CASH_CONFIRM',amount='0',cash_basis='TOTAL_UNINVESTED'))
   before=json.dumps(state,sort_keys=True)
   with TemporaryDirectory() as d:
    calls=[]
    def fetch(ticker):calls.append(ticker);return raw(ticker)
    provider=StrategyAccountMarketCapture(identity_resolver=identity,fetch=fetch,clock=lambda:now)
    # HELD has left the candidate pool; only NEW is eligible for selection.
    market=provider.capture(state=state,candidate_metadata={'NEW':{'ticker':'NEW'}},output_directory=Path(d)/'capture')
    self.assertEqual(set(calls),{'NEW','HELD'})
    limits={sid:dict(security_id=sid,price_basis=mark['price_basis'],buy='10',sell='10',observed_at=mark['observed_at']) for sid,mark in market['marks'].items()}
    result=preview_scoped_account(state=state,legacy_shares={},marks=market['marks'],limits=limits,
           target_quantities={'NEW':10},now=now.isoformat(),maximum_mark_age_seconds=120,fee_bps='0')
    self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['new_orders']],[('HELD','SELL',10)])
    self.assertTrue(result['waiting_cash'])
    self.assertEqual(result['spendable_cash'],'0')
    self.assertEqual(json.dumps(state,sort_keys=True),before)

if __name__=='__main__':unittest.main()
