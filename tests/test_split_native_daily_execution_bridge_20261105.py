"""Real generated native target and complete controlled minute transport."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json, unittest
from core.strategy_account_ledger import canonical
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyExecutionBridge, DailyMixedExecutionBridge, DailyBuyDataWaitExecutionBridge
import test_split_monthly_factory_20261105 as fixture

class Tests(unittest.TestCase):
 def test_real_subclass_admission_projection_and_negative_boundaries(self):
  with TemporaryDirectory() as folder:
   monthly,store,_=fixture.Tests().case(folder)
   provider=monthly.execution_provider.__self__
   market=next(c.cell_contents for c in provider.market.capture.__closure__ if hasattr(c.cell_contents,'fetch'))
   original_fetch=market.fetch
   def complete_minutes(ticker):
    document=json.loads(original_fetch(ticker));series=document['chart']['result'][0]
    opening=series['meta']['currentTradingPeriod']['regular']['start'];last=series['meta']['regularMarketTime']
    series['timestamp']=list(range(opening,last,60));count=len(series['timestamp'])
    series['indicators']['quote'][0]={key:[value]*count for key,value in dict(open=10,high=11,low=9,close=10,volume=10).items()}
    return canonical(document)
   market.fetch=complete_minutes
   before=store.read()
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')):
    target=monthly.generate(event_id='native-daily-target',reason='INITIAL',expected_revision=before['revision'],previous_target_id=None)
    frozen=deepcopy(target)
    effective={sid:0 for sid in target['payload']['target_quantities']};effective['B']=1
    signal=dict(policy_id='ISOLATED_NATIVE_DAILY_TEST',evidence_id='a'*64,effective_target_quantities=effective)
    def bridge():return DailyExecutionBridge(base_target=target,execution_provider=monthly.execution_provider,validate_sources=monthly.selection._pins,signal=signal)
    original_assemble=type(provider)._assemble;calls=[]
    def traced(self,*args,**kwargs):
     calls.append(deepcopy(kwargs));return original_assemble(self,*args,**kwargs)
    with patch.object(type(provider),'_assemble',traced):
     adapter=bridge();result=adapter(before,effective,provider.clock())
    self.assertEqual(len(calls),1);self.assertEqual(calls[0]['target_quantities'],{'B':1})
    self.assertEqual(result['marks']['B']['unit_id'],'new')
    self.assertEqual(target,frozen);self.assertEqual(store.read(),before)
    binding=adapter.last_binding
    lineage=json.loads(Path(binding['path']).read_bytes());receipt=json.loads(Path(binding['completion_path']).read_bytes())
    self.assertEqual(lineage['effective_target_quantities'],effective)
    self.assertEqual(lineage['base_target_id'],target['target_id'])
    self.assertEqual(receipt['result_sha256'],sha256(canonical(result)).hexdigest())
    for name,digest in receipt['capture_completions'].items():
     self.assertEqual(sha256((Path(binding['path']).parent/name).read_bytes()).hexdigest(),digest)
    # Unlike the old bridge, a required subclass rejection cannot be bypassed.
    with patch.object(type(provider),'_assemble',side_effect=AssertionError('REQUIRED_SUBCLASS_REVIEW')) as guard:
     with self.assertRaisesRegex(AssertionError,'REQUIRED_SUBCLASS_REVIEW'):bridge()(before,effective,provider.clock())
     self.assertEqual(guard.call_count,1)
    # A real factory source pin remains live through the projected call.
    source=provider.root/fixture.factory.PATH;old=source.read_bytes()
    source.write_bytes(old+b'\n# changed controlled source\n')
    try:
     with self.assertRaisesRegex(ValueError,'RUNTIME_SOURCE_CHANGED|SPLIT_MONTHLY_SOURCE_CHANGED'):bridge()(before,effective,provider.clock())
    finally:source.write_bytes(old)
    # The actual factory timing/history reviewer is still reached. Mutate only
    # this synthetic fixture's captured proof, never a production source.
    bundles=next(c.cell_contents for c in original_assemble.__closure__ if isinstance(c.cell_contents,dict) and 'split-B' in c.cell_contents)
    old_timing=deepcopy(bundles['split-B'])
    bundles['split-B']['review']['tradable_evidence_received_at']='2099-01-01T00:00:00+00:00'
    try:
     with self.assertRaisesRegex(ValueError,'TIMING_NOT_EXECUTABLE_YET'):bridge()(before,effective,provider.clock())
    finally:bundles['split-B']=old_timing
    self.assertEqual(store.read(),before);self.assertEqual(target,frozen)
    # The same actual subclass admission protects both sell-only fallbacks.
    for cls in (DailyBuyDataWaitExecutionBridge,DailyMixedExecutionBridge):
     if cls is DailyMixedExecutionBridge:
      store.append(dict(event_id='zero-for-mixed',kind='CASH_CONFIRM',amount='0',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=store.read()['revision'])
     current=store.read();projected={sid:min(current['shares'].get(sid,0),q) for sid,q in effective.items()}
     mixed=cls(base_target=target,execution_provider=monthly.execution_provider,validate_sources=monthly.selection._pins,signal=signal)
     calls.clear()
     with patch.object(type(provider),'_assemble',traced):
      fallback=mixed(current,effective,provider.clock(),execution_quantities=projected)
     self.assertEqual(len(calls),1)
     self.assertEqual(calls[0]['target_quantities'],{sid:q for sid,q in projected.items() if q})
     self.assertIn('limits',fallback);self.assertEqual(store.read(),current)
     line=json.loads(Path(mixed.last_binding['path']).read_bytes())
     self.assertEqual(line['schema'],mixed.lineage_schema)
     self.assertEqual(line['effective_target_quantities'],effective)
     self.assertEqual(line['execution_quantities'],projected)
     bad=dict(projected);bad['B']=projected['B']+1
     with self.assertRaisesRegex(ValueError,'DAILY_SELL_ONLY_PROJECTION_REQUIRED'):
      mixed(current,effective,provider.clock(),execution_quantities=bad)
     with patch.object(type(provider),'_assemble',side_effect=AssertionError('REQUIRED_SUBCLASS_REVIEW')) as guard:
      with self.assertRaisesRegex(AssertionError,'REQUIRED_SUBCLASS_REVIEW'):
       mixed(current,effective,provider.clock(),execution_quantities=projected)
      self.assertEqual(guard.call_count,1)
    self.assertEqual(target,frozen)

if __name__=='__main__':unittest.main()


