"""Actual NewsInvestmentService HOLD projection on the native protected path."""
from copy import deepcopy
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
import json,unittest
import test_split_native_capture_configuration_20261105 as fixture
from core.strategy_account_ledger import canonical
from data.news_investment_service_v1 import NewsInvestmentService
from docs.candidates.split_native_capture_configuration_20261105 import ConfiguredNativeAdmission,digest
from docs.candidates.split_native_news_hold_20261105 import install_native_hold_risk_plan

class Tests(unittest.TestCase):
 def test_actual_news_hold_provider_reduces_without_mutating_risk_or_account(self):
  helper=fixture.Tests();self.addCleanup(helper.doCleanups);case=helper.case()
  service=case['service'];f=case['f'];view=case['view'];provider=case['provider']
  with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
   initial=service.preview(**case['request']);self.assertEqual(initial['status'],'READY')
   target=view.current();proposal=view.require_proposal(target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
   desired=proposal['payload']['proposed_target_quantities']
   for sid in sorted(set(desired)|set(f.store.read()['shares'])):
    held=f.store.read()['shares'].get(sid,0);gap=desired.get(sid,0)-held
    if not gap:continue
    ticker=provider.market.identity(next(r['ticker'] for r in f.f.identity['candidates'] if r['security_id']==sid))['ticker']
    identity=provider.market.identity(ticker)
    f.store.append(dict(event_id='hold-position-'+sid,kind='DIRECT_FILL',security_id=sid,side='BUY' if gap>0 else 'SELL',quantity=abs(gap),price='10',fees='0',executed_at=f.now.isoformat(),identity_evidence=identity),expected_revision=f.store.read()['revision'])
   f.store.append(dict(event_id='hold-cash',kind='CASH_CONFIRM',amount='100',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=f.store.read()['revision'])
   # Add the actual newly recorded identity source closure to the synthetic server
   # authorization; no source is inferred from browser input or model output.
   config=json.loads(case['configraw']);ref=config['authorizations'][target['target_id']];grant=json.loads((f.root/ref['path']).read_bytes())
   for event in f.store.read()['events']:
    for name,h in event['payload'].get('identity_evidence',{}).get('source_hashes',{}).items():
     raw=(f.root/name).read_bytes();self.assertEqual(digest(raw),h)
     path=f.root/'hold-authority'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);ref['files'][name]=path.relative_to(f.root).as_posix();grant['source_sha256'][name]=h
   (f.root/ref['path']).write_bytes(canonical(grant));ref['sha256']=digest(canonical(grant));(f.root/'native-config.json').write_bytes(canonical(config))
   service=ConfiguredNativeAdmission(**dict(case['arguments'],configuration_sha256=digest(canonical(config))))
   f.now+=timedelta(minutes=1);state=f.store.read();request=dict(expected_revision=state['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
   original=service.preview(**request);self.assertEqual(original['status'],'HOLD',original)
   names={s:next(r['ticker'] for r in f.f.identity['candidates'] if r['security_id']==s) for s in desired}
   news=NewsInvestmentService(cache=f.root/'hold-news',context=lambda:(f.store.read(),view.current(),names),preview=service.preview,validate=service.validate_code,input_operation=view.snapshot_operation)
   install_native_hold_risk_plan(service=news,configured=service,validate=service.validate_code)
   chosen=next(s for s,q in state['shares'].items() if q>0)
   effective={s:desired.get(s,0) for s in set(desired)|set(state['shares'])};rows=[]
   for sid in effective:
    held=state['shares'].get(sid,0)
    if not(held or effective[sid]):continue
    rows.append(dict(security_id=sid,action='REDUCE_HOLDING' if sid==chosen else 'KEEP',held_quantity=held,original_target_quantity=effective[sid],proposed_target_quantity=max(0,held-1) if sid==chosen else held,reviewed=True))
   review=dict(schema='NEWS_INVESTMENT_REVIEW_PROPOSAL_V1',status='REVIEW_PROPOSAL_ONLY',review_id='controlled-native-hold-review',original_binding={k:original[k] for k in ('account_revision','target_id','proposal_id')},review_created_at=f.now.isoformat(),review_valid_until=(f.now+timedelta(seconds=60)).isoformat(),executable=False,orders_created=False,rows=rows)
   frozen_review=deepcopy(review)
   before=deepcopy(original);risk=service.risk.read(state['account_id']);target_before=view.current()
   # New quote timestamp while original risk/review remain live.
   f.now+=timedelta(seconds=2)
   result=news.risk_plan_provider(original=original,proposal=review,account=state,target=target_before,now=f.now.isoformat())
   self.assertEqual(result['status'],'READY',result);self.assertTrue(result['candidate_orders']);self.assertTrue(all(o['side']=='SELL' for o in result['candidate_orders']))
   self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['candidate_orders']],[(chosen,'SELL',1)])
   from data.news_risk_execution_bridge_v1 import digest as review_digest
   binding=result['binding'];lineage=json.loads(Path(binding['path']).read_bytes())
   self.assertEqual(digest(Path(binding['path']).read_bytes()),binding['sha256'])
   self.assertEqual(lineage['review_sha256'],review_digest(review));self.assertEqual(lineage['review_id'],review['review_id'])
   self.assertEqual(lineage['signal']['effective_target_quantities'],effective)
   self.assertEqual(lineage['projected_target_quantities'],{s:q-(1 if s==chosen else 0) for s,q in effective.items()})
   self.assertFalse(lineage['original_signal_mutated']);self.assertEqual(review,frozen_review)
   self.assertEqual(original,before);self.assertEqual(f.store.read(),state);self.assertEqual(view.current(),target_before);self.assertEqual(service.risk.read(state['account_id']),risk)
   self.assertFalse(result['executable']);self.assertFalse(result['orders_created'])
   bad=deepcopy(review);next(r for r in bad['rows'] if r['security_id']==chosen)['proposed_target_quantity']=state['shares'][chosen]+1
   refused=news.risk_plan_provider(original=original,proposal=bad,account=state,target=target_before,now=f.now.isoformat())
   self.assertEqual(refused['status'],'WAIT');self.assertEqual(refused['reason'],'NEWS_SELL_ONLY_REQUIRED')
   # An actual factory subclass gate must execute, not the legacy base assemble.
   f.now+=timedelta(seconds=2)
   with patch.object(type(provider),'_assemble',side_effect=AssertionError('NATIVE_HOLD_SUBCLASS_REQUIRED')) as checked:
    refused=news.risk_plan_provider(original=original,proposal=review,account=state,target=target_before,now=f.now.isoformat())
    self.assertEqual(refused['status'],'WAIT');self.assertEqual(refused['reason'],'NATIVE_HOLD_SUBCLASS_REQUIRED');self.assertEqual(checked.call_count,1)
   self.assertEqual(f.store.read(),state)
if __name__=='__main__':unittest.main()
