import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_cash_combined_readable_report_20261008 as m

def fixture():
 ratio=dict(numerator='-123456789012345678901',denominator='987654321098765432101')
 metrics={k:dict(cumulative_return=copy.deepcopy(ratio),maximum_drawdown=dict(numerator='1',denominator='3'),annualized_return_diagnostic_decimal='0.123456789012345678901234567890') for k in m.ROLES}
 day=dict(session='2023-05-01',buy_shares={'sid:one':7,'sid:zero':0})
 row=dict(scenario_index=0,scenario_id='RETURN|2023-04-28|2023-05-01|1000',candidate_status='AVAILABLE_NEW',metrics=metrics,candidate_minus_references={k:copy.deepcopy(v) for k,v in metrics.items() if k!='candidate'},original_case_evidence=dict(input_row=dict(lane='RETURN',cash_event=dict(decision_date='2023-04-28',execution_date='2023-05-01',amount_usd='1000'),securities={'sid:one':dict(ticker='REAL',issuer_id='issuer:one')}),candidate=dict(account=dict(rows=[copy.deepcopy(day)]),accounting_inputs=dict(sessions=[copy.deepcopy(day)]))),policy_asymmetry='SAVED_POLICY',nav_currency='CNY',nav_is_same_flow_executable_account=False,short_and_unequal_windows_not_aggregated=True)
 row.update(dict.fromkeys(('account_executed','point_in_time_verified','formal_dual_benchmark_admission','cross_window_ranking_performed','currency_fx_equivalence_verified','nav_dataset_currency_binding_certified','nav_publication_time_verified','candidate_decision_time_executability_verified'),False))
 return row,dict(scenario_index=0,scenario_id=row['scenario_id'],byte_start=0,byte_stop=99,row_sha256='a'*64)

class LiteralReportTests(unittest.TestCase):
 def test_literal_numbers_identity_and_pointers_no_input_mutation(self):
  row,d=fixture();before=copy.deepcopy(row);r=m.project(row,d)
  self.assertEqual(row,before);self.assertEqual(r['metrics'][0]['cumulative_return'],row['metrics']['candidate']['cumulative_return'])
  self.assertEqual([(b['ticker'],b['buy_shares']) for b in r['buys']],[('REAL',7)])
  self.assertEqual(r['buys'][0]['quantity_pointer'],'/original_case_evidence/candidate/account/rows/0/buy_shares/sid:one')
  text=m.render([r]);self.assertIn('-12.5000%',text);self.assertNotIn('0.123456789012345678901234567890',text)
  self.assertEqual(len(r['metrics']),4);self.assertEqual(len(r['differences']),3)
 def test_round_half_even_negative_zero_tiny_nonzero_and_huge_integer(self):
  self.assertEqual(m.percentage('0.000001225'),'0.0001%')
  self.assertEqual(m.percentage('0.000001235'),'0.0001%')
  self.assertEqual(m.percentage('0.0012345'),'0.1234%')
  self.assertEqual(m.percentage('0.0012355'),'0.1236%')
  self.assertEqual(m.percentage('-0.00000'),'0.0000%')
  self.assertEqual(m.percentage(dict(numerator='0',denominator='7'),difference=True),'0.0000 pp')
  self.assertIn('0.0001%',m.percentage('1e-1000'));self.assertNotEqual(m.percentage('1e-1000'),'0.0000%')
  self.assertIn('负',m.percentage('-1e-1000'))
  self.assertEqual(m.percentage(dict(numerator='1'+'0'*500,denominator='3'+'0'*500)),'33.3333%')
 def test_wrong_identity_quantity_calendar_rejected(self):
  for attack in ('missing_identity','different_quantity','boolean_quantity','duplicate_day','wrong_index'):
   with self.subTest(attack=attack):
    row,d=fixture();case=row['original_case_evidence']
    if attack=='missing_identity':case['input_row']['securities'].clear()
    if attack=='different_quantity':case['candidate']['account']['rows'][0]['buy_shares']['sid:one']=8
    if attack=='boolean_quantity':
     case['candidate']['account']['rows'][0]['buy_shares']['sid:one']=True;case['candidate']['accounting_inputs']['sessions'][0]['buy_shares']['sid:one']=True
    if attack=='duplicate_day':case['candidate']['account']['rows']*=2
    if attack=='wrong_index':row['scenario_index']=1
    with self.assertRaises((ValueError,KeyError)):m.project(row,d)
 def test_future_pins_refuse_before_source_io_and_output(self):
  with tempfile.TemporaryDirectory() as directory:
   target=Path(directory)/'not-created'
   with patch.object(m,'OUTPUT',target),patch.object(m,'BOUND',{'index':(Path(directory)/'missing',None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('Pending source IO')),self.assertRaisesRegex(ValueError,'Pending source anchor'):m.run()
   self.assertFalse(target.exists())

class PhysicalReportTests(unittest.TestCase):
 def test_complete_forty_create_only_literal_source_roundtrip(self):
  import json,hashlib
  with tempfile.TemporaryDirectory() as directory:
   base=Path(directory);parent=base/'comparison';auditroot=base/'audit';out=base/'report';parent.mkdir();auditroot.mkdir()
   def put(path,value):
    raw=m.enc(value);path.write_bytes(raw);return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
   fake_reader=base/'reader.py';fake_reader.write_bytes(b'# synthetic reader identity')
   readerref=dict(path=str(fake_reader),sha256=m.file_sha(fake_reader));records=[];raws=[];offset=0;counts={};expected=[]
   for i in range(40):
    row,d=fixture();lane=list(m.LANES)[i%4];decision=f'2023-0{i//8+1}-28';amount=('1000','10000')[(i//4)%2];event=row['original_case_evidence']['input_row']['cash_event'];event.update(decision_date=decision,amount_usd=amount)
    row.update(scenario_index=i,scenario_id=f'{lane}|{decision}|2023-05-01|{amount}',candidate_status='AVAILABLE_NEW' if i<22 else 'AVAILABLE_REUSED');row['original_case_evidence']['input_row']['lane']=lane
    raw=m.enc(row)+b'\n';d.update(scenario_index=i,scenario_id=row['scenario_id'],byte_start=offset,byte_stop=offset+len(raw),row_sha256=m.sha(raw));offset+=len(raw);records.append(d);raws.append(raw);expected.append(row);counts[row['candidate_status']]=counts.get(row['candidate_status'],0)+1
   journal=parent/'cases.jsonl';journal.write_bytes(b''.join(raws));put(parent/'started.json',{})
   flags=dict.fromkeys(('account_executed','point_in_time_verified','formal_dual_benchmark_admission','fresh_oos_claimed'),False)
   indexref=put(parent/'index.json',dict(schema='SOURCE_BOUND_CASH_NEIGHBOR_PATH_COMPARISON_V1',scenario_count=40,cases=records,source_hashes={},consumed_candidate_sources={},case_jsonl_reference=dict(path=str(journal),sha256=m.file_sha(journal),record_count=40,byte_count=offset),candidate_status_counts=counts,**flags))
   pubref=put(parent/'publication.json',dict(schema='CASH_NEIGHBOR_PATH_COMPARISON_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_READBACK',index_reference=indexref,source_hashes={},**flags))
   put(auditroot/'started.json',{})
   auditref=put(auditroot/'independent_readback.json',dict(schema='CASH_NEIGHBOR_PATH_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',scenario_count=40,index_reference=indexref,publication_reference=pubref,reader_sha256=readerref['sha256'],source_hashes={r['path']:r['sha256'] for r in (indexref,pubref,readerref)},consumed_candidate_sources={},cases=[{} for _ in range(40)],candidate_status_counts=counts,**flags))
   bounds={k:(Path(r['path']),r['sha256']) for k,r in dict(index=indexref,publication=pubref,audit=auditref,reader=readerref).items()}
   with patch.object(m,'BOUND',bounds),patch.object(m,'PARENT',parent),patch.object(m,'AUDIT_ROOT',auditroot),patch.object(m,'OUTPUT',out):
    m.run();projection=json.loads((out/'projection.json').read_bytes());text=(out/'report.md').read_text(encoding='utf-8')
    self.assertEqual(len(projection['rows']),40);self.assertEqual(text.count('\n## '),40)
    for source,saved in zip(expected,projection['rows']):
     self.assertEqual(saved['scenario_id'],source['scenario_id'])
     for metric in saved['metrics']:self.assertEqual(metric['cumulative_return'],source['metrics'][metric['role']]['cumulative_return'])
    self.assertEqual({p.name for p in out.iterdir()},{'started.json','projection.json','report.md','publication.json'})
    with self.assertRaisesRegex(ValueError,'Create-only'):m.run()

if __name__=='__main__':unittest.main()
