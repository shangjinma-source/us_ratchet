"""Synthetic genesis source and prefix contracts; never run the saved old reader."""
import copy,csv,io,json,sys,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ndx_gap_monthly_policy_history_input_readback_20261003 as m

def fixture():
 refs={k:m.reference('fixture/'+k,'a'*64)for k in m.BOUND};dates=[];day=date(2026,7,1)
 while day<=date(2026,10,1):
  if day.weekday()<5 and day.isoformat()not in ('2026-07-03','2026-09-07'):dates.append(day.isoformat())
  day+=timedelta(days=1)
 assert len(dates)==65
 rows=[];front=[]
 for i,d in enumerate(dates):
  kind='MISSED_OBSERVATION'if i>=60 else 'SEALED_PARENT_OBSERVED_SESSION';front.append(dict(session=d,kind=kind,counts_as_observed_session=False,decision_eligible=False,gap_event_index=i-60,gap_event_sha256='a'*64)if i>=60 else dict(session=d,kind=kind,eligibility_reverified=False,parent_session_index=i))
  rows.append(dict(sequence=i+1,session=d,kind=kind,evidence_reference=dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'),seal_status='NOT_ATTEMPTED'if i>=60 else 'UNKNOWN'))
 raws={k:b'{}'for k in refs};raws['user_choice']=(m.POLICY+'\n> 按首次实际观察延续：缺口不占月首机会（更贴近原合同）').encode()
 for t in ('QQQ','SPY'):
  buf=io.StringIO(newline='');writer=csv.writer(buf);writer.writerow(['Date','Open','High','Low','Close','Volume'])
  writer.writerow(['2026-06-30','99','98','100','99','10']) # Outside scope deliberately not price certified.
  for d in dates:writer.writerow([d,'10','12','9','11','100'])
  raws[t]=buf.getvalue().encode();refs[t]['sha256']=m.sha(raws[t])
 flags=dict.fromkeys(m.AUTH,False)
 f=dict(schema='OBSERVATION_GAP_FRONTIER_RESEARCH_V1',known_accounted_rows=front,last_observed_session='2026-09-24',last_accounted_session='2026-10-01',input_references={t:refs[t]for t in ('QQQ','SPY')},source_hashes={refs[t]['path']:refs[t]['sha256']for t in ('QQQ','SPY')},**flags)
 p=dict(schema='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1',policy_id=m.POLICY,input_references=dict(frontier=refs['frontier'],publication=refs['frontier_publication'],user_choice=refs['user_choice'],core=refs['policy_core']),frontier_reference=refs['frontier'],user_choice_reference=refs['user_choice'],projection_inputs=dict(policy_id=m.POLICY,known_rows=rows,new_prospective_observations=[]),new_observation_count=0,prospective_monthly_coordinate_count=0,saved_frontier_rows=front,source_hashes={refs[k]['path']:refs[k]['sha256']for k in ('frontier','frontier_publication','user_choice','policy_core','policy_producer')},**flags)
 months={}
 for r in rows:
  v=months.setdefault(r['session'][:7],dict(month=r['session'][:7],first_observed_session=None,observed_count=0,missed_count=0))
  if r['kind']=='MISSED_OBSERVATION':v['missed_count']+=1
  else:
   v['observed_count']+=1
   if v['first_observed_session']is None:v['first_observed_session']=r['session']
 p['projection']={'months':list(months.values())}
 u=dict(schema='GAP_MONTHLY_POLICY_PUBLICATION_V1',status='PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL',policy_reference=refs['policy'],source_hashes=p['source_hashes'],**flags)
 fu=dict(schema='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1',status='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY',frontier_reference=refs['frontier'],source_hashes=f['source_hashes'],**flags)
 docs=dict(policy=p,publication=u,frontier=f,frontier_publication=fu,policy_started=dict(source_hashes=p['source_hashes'],retry_allowed=False),frontier_started=dict(source_hashes=f['source_hashes'],retry_allowed=False))
 return docs,refs,raws

class Tests(unittest.TestCase):
 def test_original_prefix_rows_baseline_and_historical_role(self):
  d,r,b=fixture();before=copy.deepcopy((d,r,b));o=m.inspect(d,r,b);self.assertEqual((d,r,b),before);self.assertEqual(o['counts'],dict(known_rows=65,observed_rows=60,gap_rows=5,new_observation_count=0));self.assertEqual(o['baseline_details']['QQQ']['original_data_row_start'],1);self.assertEqual(o['baseline_details']['SPY']['full_csv_row_count'],66);self.assertTrue(all(o[k]is False for k in m.FLAGS));self.assertIn('NOT_A_PERSISTED',o['historical_review_evidence']['role'])
 def test_no_gap_promotion_unknown_overwrite_false_int_or_wrong_receipt(self):
  for attack in ('gap','unknown','bool','receipt','authority','baseline','invented_field','parent_index'):
   d,r,b=fixture()
   if attack=='gap':d['policy']['projection_inputs']['known_rows'][-1]['kind']='SEALED_PARENT_OBSERVED_SESSION'
   elif attack=='unknown':d['policy']['projection_inputs']['known_rows'][0]['seal_status']='SEALED'
   elif attack=='bool':d['policy']['new_observation_count']=False
   elif attack=='receipt':d['publication']['policy_reference']=m.reference('other','a'*64)
   elif attack=='authority':d['frontier']['candidate_seal_allowed']=0
   elif attack=='baseline':d['frontier']['input_references']['QQQ']=r['SPY']
   elif attack=='invented_field':d['frontier']['known_accounted_rows'][0]['counts_as_observed_session']=True
   else:d['frontier']['known_accounted_rows'][0]['parent_session_index']=False
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect(d,r,b)
 def test_full_csv_missing_duplicate_suffix_and_byte_change(self):
  d,r,b=fixture();dates=[x['session']for x in d['policy']['projection_inputs']['known_rows']]
  for attack in ('missing','duplicate','extra','unordered'):
   lines=b['QQQ'].splitlines(keepends=True)
   if attack=='missing':lines.pop(5)
   elif attack=='duplicate':lines.insert(5,lines[5])
   elif attack=='extra':lines.append(b'2026-10-02,10,12,9,11,100\r\n')
   else:lines[4],lines[5]=lines[5],lines[4]
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.csv_prefix(b''.join(lines),dates,r['QQQ'])
  b['QQQ']+=b'\n'
  with self.assertRaises(ValueError):m.inspect(d,r,b)
 def test_create_only_failure_and_explicit_gate_no_old_calls(self):
  with tempfile.TemporaryDirectory()as tmp:
   out=Path(tmp)/'out';pins={}
   for role in m.BOUND:
    f=Path(tmp)/(role+'.txt');f.write_bytes(b'{}');pins[role]=(str(f),m.sha(b'{}'))
   with patch.object(m,'OUTPUT',out),patch.object(m,'BOUND',pins),patch.object(m,'namespaces'),patch.object(m,'guard'),patch.object(m,'inspect',side_effect=ValueError('synthetic body failure')):
    with self.assertRaises(ValueError):m.readback(execute=False)
    self.assertFalse(out.exists())
    with self.assertRaisesRegex(ValueError,'synthetic body'):m.readback(execute=True)
    self.assertEqual({p.name for p in out.iterdir()},{'started.json','failure.json'})
    with self.assertRaisesRegex(ValueError,'Create-only'):m.readback(execute=True)

if __name__=='__main__':unittest.main()
