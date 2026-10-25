from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_security_domain_v1 import plan_security_domain,aggregate_security_packets,locate_unit_baseline_sources
import test_strategy_profiled_daily_packet_admission as fixtures

class DynamicDomainTests(unittest.TestCase):
 def case(self,folder):
  c=fixtures.ProfiledPacketTests().setup_case(folder);root=Path(folder)
  raw=b'{}';(root/'identity-ref.json').write_bytes(raw)
  document=dict(candidates=[dict(ticker=ticker,security_id=sid,status='READY_CONDITIONAL',identity_reviewed=True,
   identity_source_references=['identity-ref.json']) for sid,ticker in [('A','AAA'),('B','BBB')]],source_hashes={'identity-ref.json':sha256(raw).hexdigest()})
  raw=canonical(document);(root/'domain-identity.json').write_bytes(raw)
  c.identity_reference=dict(path='domain-identity.json',sha256=sha256(raw).hexdigest())
  c.store.append(dict(event_id='domain-cash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
  from data.strategy_account_identity import PinnedStrategyIdentity
  resolver=PinnedStrategyIdentity(root,'domain-identity.json',sha256(raw).hexdigest())
  c.store.append(dict(event_id='new-pending',kind='ORDER_OPEN',order_id='a-pending',security_id='A',side='BUY',quantity=1,limit_price='2',fee_per_share='0',identity_evidence=resolver('AAA')),expected_revision=c.store.read()['revision'])
  c.state=c.store.read()
  mapping=locate_unit_baseline_sources(root=root,evidence_root='capture',binding=c.target['payload']['decision']['payload']['input_binding'])
  c.domain=plan_security_domain(root=root,state=c.state,target=c.target,identity_reference=c.identity_reference,source_paths=mapping)
  return c
 def packets(self,c,folder):
  root=Path(folder);base=json.loads((root/'parent.json').read_bytes());original=json.loads((root/'normalized.json').read_bytes());result={}
  for sid in ('A','B'):
   inputs=deepcopy(original);inputs['histories']={sid:deepcopy(original['histories']['B'])}
   name='normalized-'+sid+'.json';files={name:canonical(inputs),'raw.json':b'{"fixture_only":true}'}
   receipt=dict(base,normalized_inputs_path=name,source_sha256={p:sha256(raw).hexdigest() for p,raw in files.items()})
   raw=canonical(receipt);result[sid]=dict(receipt_bytes=raw,trusted_receipt_sha256=sha256(raw).hexdigest(),files=files)
  return result
 def test_actual_target_holding_and_open_order_domain(self):
  with TemporaryDirectory() as folder:
   c=self.case(folder)
   self.assertEqual(set(c.domain['securities']),{'A','B'})
   self.assertEqual(c.domain['securities']['A']['reasons'],['OPEN_ORDER'])
   self.assertEqual(c.domain['securities']['A']['status'],'WAIT_UNIT_BASELINE')
   self.assertEqual(c.domain['securities']['B']['status'],'FIRST_WINDOW_REVIEW_REQUIRED')
   self.assertEqual(c.domain['securities']['B']['reasons'],['ACTUAL_HOLDING','MONTHLY_TARGET'])
 def test_all_domain_or_wait_and_closed_sources(self):
  with TemporaryDirectory() as folder:
   c=self.case(folder);packets=self.packets(c,folder);before=c.store.path.read_bytes()
   def run(value):return aggregate_security_packets(domain=c.domain,packets=value,state=c.state,target=c.target,now=c.clock[0])
   self.assertEqual(run({'B':packets['B']})['status'],'WAIT_COMPLETE_SECURITY_DOMAIN')
   result=run(packets)
   self.assertEqual(result['status'],'COMPLETE_DOMAIN_REBOUND_POLICY_UNCHANGED',result)
   self.assertEqual(len(result['receipt']['aggregate_parents']),2)
   self.assertEqual(result['receipt']['full_domain_security_ids'],['A','B'])
   self.assertEqual(set(json.loads(result['files'][result['receipt']['full_domain_inputs_path']])['histories']),{'A','B'})
   self.assertEqual(c.store.path.read_bytes(),before)
   bad=deepcopy(packets);bad['A']['files']['raw.json']=b'bad'
   with self.assertRaisesRegex(ValueError,'AGGREGATE_SOURCE_HASH'):run(bad)
   for change,error in [(dict(schema='UNREVIEWED_WRONG_SCHEMA'),'AGGREGATE_RECEIPT_SCHEMA'),
                        (dict(raw_source_paths=['missing-source']),'AGGREGATE_RAW_SOURCE_DOMAIN'),
                        (dict(valid_until='2099-01-01T20:00:00Z'),'AGGREGATE_SESSION_CLOCK')]:
    bad=deepcopy(packets);receipt=json.loads(bad['A']['receipt_bytes']);receipt.update(change)
    bad['A']['receipt_bytes']=canonical(receipt);bad['A']['trusted_receipt_sha256']=sha256(canonical(receipt)).hexdigest()
    with self.assertRaisesRegex(ValueError,error):run(bad)

if __name__=='__main__':unittest.main()
