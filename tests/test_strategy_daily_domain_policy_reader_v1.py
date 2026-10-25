from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_domain_policy_reader_v1 import ExplicitDomainPolicyReviewReaderV1,REVIEW_SOURCES
from data.strategy_continuous32_target_decision import PROFILE_ID,VERSION
from data.strategy_daily_signal_verifier import POLICY
from data.strategy_daily_composition_v3 import DailyCompositionV3
from data.strategy_profiled_daily_packet_admission import ProfiledCurrentSessionDailyReader
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_market_capture import StrategyAccountMarketCapture
import test_strategy_daily_domain_policy_review_v1 as fixtures

ROOT=Path(__file__).resolve().parents[1]

class ExplicitPolicyReaderTests(unittest.TestCase):
 def setup(self,folder,authorized=True):
  c,root,args=fixtures.DomainPolicyReviewTests().setup(folder)
  source=(root/'reader-config.json').read_bytes()
  pins=[]
  for name in REVIEW_SOURCES:
   raw=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
   pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
  config=dict(schema='SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1',authorized=authorized,
   scope='COMPLETE_CURRENT_SESSION_DOMAIN',account_id=c.store.read()['account_id'],
   selector_profile=PROFILE_ID,selection_method=VERSION,continuous_iterations=32,
   authorization_id='FIXTURE_ONLY_DEVELOPMENT_REVIEW',authorization_source='ISOLATED_TEST_NOT_USER_RULE_APPROVAL',
   rule_selection_role='IMPLEMENTER_RECOMMENDATION_REVIEWED',
   authorized_at='2026-11-02T14:00:00Z',valid_from='2026-11-02T14:00:00Z',valid_until='2026-11-02T21:00:00Z',
   source_configuration=dict(path='reader-config.json',sha256=sha256(source).hexdigest()),
   calendar=json.loads(source)['calendar'],release=dict(path='release.json',sha256=sha256(args['release_bytes']).hexdigest()),
   code_pins=pins,archive_root='explicit-policy-archive',fixture_only=True)
  raw=canonical(config);(root/'policy-review-config.json').write_bytes(raw)
  options=dict(root=root,configuration_path='reader-config.json',configuration_sha256=sha256(source).hexdigest(),
   archive_root=None,release_path='release.json',trusted_release_sha256=sha256(args['release_bytes']).hexdigest(),
   review_configuration_path='policy-review-config.json',review_configuration_sha256=sha256(raw).hexdigest(),
   clock=lambda:c.clock[0])
  reader=ExplicitDomainPolicyReviewReaderV1(**options)
  class CompositionReader(ProfiledCurrentSessionDailyReader):
   def __init__(self):self.packet_reader=reader
  c.service=DailyCompositionV3(monthly_service=c.monthly,evidence_reader=CompositionReader(),
   execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,
   policy_id=POLICY,fee_bps='10')
  return c,root,reader,options
 def test_actual_composition_buy_sell_hold_wait(self):
  for mode in ('SELL','BUY','HOLD','WAIT'):
   with self.subTest(mode=mode),TemporaryDirectory() as folder:
    c,root,reader,options=self.setup(folder)
    resolver=PinnedStrategyIdentity(root,c.identity_reference['path'],c.identity_reference['sha256'])
    if mode in ('BUY','HOLD'):
     state=c.store.read()
     for sid,held in state['shares'].items():
      wanted=0 if mode=='BUY' else c.target['payload']['target_quantities'].get(sid,0)//2
      quantity=abs(held-wanted)
      if quantity:
       c.store.append(dict(event_id='align-'+sid,kind='DIRECT_FILL',security_id=sid,
        side='BUY' if wanted>held else 'SELL',quantity=quantity,price='10',fees='0',
        executed_at=c.clock[0].isoformat(),identity_evidence=resolver('AAA' if sid=='A' else 'BBB')),
        expected_revision=c.store.read()['revision'])
     c.store.append(dict(event_id='align-cash',kind='CASH_CONFIRM',amount='1000' if mode=='BUY' else '0',
      cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
     def minute_raw(ticker):
      opening=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp());last=opening+1800
      return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',
       instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',
       regularMarketPrice=10,regularMarketTime=last,currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),
       timestamp=list(range(opening,last,60)),indicators=dict(quote=[dict(open=[10]*30,high=[11]*30,
       low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
     c.provider.market=StrategyAccountMarketCapture(identity_resolver=resolver,fetch=minute_raw,clock=lambda:c.clock[0],max_mark_age=120)
    if mode=='WAIT':reader.review_reference=None
    before=c.store.path.read_bytes()
    result=c.service.preview(expected_revision=c.store.read()['revision'],target_id=c.target['target_id'])
    self.assertEqual(result['status'],'READY' if mode in ('BUY','SELL') else mode,result)
    if mode in ('BUY','SELL'):
     self.assertTrue(any(order['side']==mode for order in result['new_orders']),result)
     self.assertTrue(Path(result['evidence_archive']['complete_path']).is_file())
    else:self.assertEqual(result['new_orders'],[])
    self.assertEqual(c.store.path.read_bytes(),before)
 def test_unapproved_control_and_post_archive_drift_return_no_signal(self):
  with TemporaryDirectory() as folder:
   c,root,reader,options=self.setup(folder,False)
   with self.assertRaisesRegex(ValueError,'AUTHORIZATION_REQUIRED'):
    reader(c.store.read(),c.target,c.clock[0])
   self.assertFalse((root/'explicit-policy-archive').exists())
  with TemporaryDirectory() as folder:
   c,root,reader,options=self.setup(folder)
   import data.strategy_daily_domain_policy_reader_v1 as module
   original=module.archive_rebound_evidence
   def mutate(**kwargs):
    result=original(**kwargs);(root/'policy-review-config.json').write_bytes(b'{}');return result
   with patch.object(module,'archive_rebound_evidence',mutate),self.assertRaises(ValueError):
    reader(c.store.read(),c.target,c.clock[0])
   self.assertTrue(list((root/'explicit-policy-archive').glob('*/complete.json')))
 def test_terminal_changed_after_strict_admission_cannot_bind_old_packets(self):
  with TemporaryDirectory() as folder:
   c,root,reader,options=self.setup(folder)
   original=reader._authorization
   def mutate(*args):
    value=original(*args)
    path=root/'dynamic-runs/2026-11-02/terminal.json'
    terminal=json.loads(path.read_bytes());terminal['packets']['B']['receipt_reference']['sha256']='0'*64
    path.write_bytes(canonical(terminal));return value
   with patch.object(reader,'_authorization',mutate),self.assertRaisesRegex(ValueError,'ADMITTED_PACKET_RACE'):
    reader(c.store.read(),c.target,c.clock[0])
   self.assertFalse((root/'explicit-policy-archive').exists())

if __name__=='__main__':unittest.main()
