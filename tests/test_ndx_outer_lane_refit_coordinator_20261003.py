from copy import deepcopy
import importlib.util,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[1]/'scripts/ndx_outer_lane_refit_coordinator_20261003.py'
s=importlib.util.spec_from_file_location('outercoordinator',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def fixture(free=10*1024**3,technical=False,risk=False):
 docs={};names={};calls=[];reader=dict(path=str(P),sha256='f'*64)
 def persist(name,v):
  r=dict(path=str((P.parent/'synthetic'/name).resolve()),sha256=m.sha(m.enc(v)));docs[r['path']]=deepcopy(v);names[name]=r;return r
 def read(r):
  v=deepcopy(docs[r['path']]);assert m.sha(m.enc(v))==r['sha256'];return v
 coordinates=[[f'cutoff{d}',f'mode{mode}',f'lane{lane}'] for d in range(6) for mode in range(2) for lane in range(4)]
 def resolve(priors):
  known=set()
  for entry in priors:
   refs=entry.get('references',entry);request=read(refs['request']);known.add(tuple(request['coordinate']))
  rows=[]
  for i,c in enumerate(coordinates):
   d=i//8;ready=i%8>=4 and (d==0 or (f'cutoff{d-1}',c[1],c[2]) in known);status='SOURCE_BLOCKED' if i%8<4 else ('INITIAL_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED' if ready else 'INPUTS_PREPARED_PRIOR_UNRESOLVED')
   req=dict(coordinate=c,numerical_task_id=f'{d:064x}',location_id=f'{i+1:064x}') if ready else None
   rows.append(dict(cutoff=c[0],fx_mode=c[1],lane=c[2],decision_index=d,status=status,outer_request=req,missing_latest_return_slots=[]))
  return dict(schema='MULTIDECISION_SELECTED_LATEST126_REFIT_INPUTS_V2',rows=rows,status_counts={k:sum(r['status']==k for r in rows) for k in {r['status'] for r in rows}})
 def dispatch(i,prior,origin):
  calls.append((i,origin));req=resolve(prior)['rows'][i]['outer_request'];outcome='REUSED_AUDITED_NUMERICAL_RESULT' if origin else 'REFIT_PASSED_PENDING_INDEPENDENT_READBACK'
  if technical:outcome='NUMERICAL_EXCEPTION'
  elif risk:outcome='REUSED_AUDITED_NUMERICAL_RISK_FAILURE' if origin else 'REFIT_RISK_FAILED'
  return persist(f'post{i}',dict(numerical_task_id=req['numerical_task_id'],location_id=req['location_id'],outcome=outcome,current_location_call_invoked=origin is None,request_reference=persist(f'request{i}',req),raw_result_reference=origin['raw_result'] if origin else persist(f'raw{i}',dict(result='saved'))))
 def inspect(r):
  p=read(r);success=p['outcome'] in m.SUCCESS;status='PASS' if success else ('TECHNICAL_FAILURE_RECORDED_NOT_PRIOR' if technical else 'PASS_SAVED_RISK_FAILURE')
  return persist('audit'+p['location_id'],dict(status=status,prior_eligible=success,postcheck_reference=r,reader_sha256=reader['sha256']))
 args=dict(prepared=resolve([]),expected_coordinates=coordinates,reader_reference=reader,resolve_state=resolve,dispatch=dispatch,inspect_saved=inspect,read_saved=read,guard_sources=lambda:None,resource_check=lambda:free,persist=persist)
 return args,docs,names,calls,read

class Tests(unittest.TestCase):
 def test_full48_adjacent_audits_and_numeric_reuse(self):
  a,docs,names,calls,read=fixture();r=read(m.execute_full48(**a));self.assertEqual(len(calls),24);self.assertEqual(sum(origin is None for _,origin in calls),6);self.assertEqual(r['summary']['explicit_reuse_count'],18);self.assertEqual(r['summary']['outcome_counts']['SOURCE_BLOCKED'],24);self.assertEqual(r['summary']['unprocessed_coordinate_count'],0);self.assertEqual(len(read(names['prepared48.json'])['prepared']['rows']),48)
 def test_failed_numeric_reused_no_later_prior_no_reexecution(self):
  a,docs,names,calls,read=fixture(risk=True);r=read(m.execute_full48(**a));self.assertEqual([i for i,_ in calls],[4,5,6,7]);self.assertEqual(sum(origin is None for _,origin in calls),1);self.assertEqual(r['summary']['outcome_counts']['AUDITED_REUSED_RISK_FAILURE'],3);self.assertEqual(r['summary']['outcome_counts']['NO_REFIT_INPUT_OR_ADJACENT_PRIOR'],20);self.assertEqual(r['status'],'COMPLETED_REGISTERED_COORDINATES')
 def test_technical_resource_unknown_partitions(self):
  a,_,_,calls,read=fixture(technical=True);r=read(m.execute_full48(**a));self.assertEqual(len(calls),1);self.assertEqual(r['rows'][4]['outcome'],'AUDITED_TECHNICAL_FAILURE');self.assertEqual(r['status'],'STOPPED_NO_RETRY')
  for free in (5*1024**3-1,True):
   a,_,_,calls,read=fixture(free=free);r=read(m.execute_full48(**a));self.assertFalse(calls);self.assertEqual(r['summary']['unprocessed_coordinate_count'],48);self.assertEqual(len(r['rows']),48)
 def test_real_failure_directory_current_post_is_terminal_not_unknown(self):
  a,_,_,_,read_memory=fixture(technical=True)
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);worker=root/'worker';auditdir=root/'reader';auditdir.mkdir();old_dispatch=a['dispatch']
   def dispatch(i,prior,origin):
    post=read_memory(old_dispatch(i,prior,origin));post.update(schema='OUTER_LANE_CUTOFF_REFIT_POSTCHECK_V1',**dict.fromkeys(('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'),False));folder=worker/'locations'/post['location_id'];folder.mkdir(parents=True);b=m.enc(post);path=folder/'postcheck.json';path.write_bytes(b);(folder/'failure.json').write_text('{"status":"FAILED_NO_RETRY"}')
    return m.ref(path,m.sha(b))
   def inspect(r):
    post=m.read_current_attempt_post(r);report=dict(status='TECHNICAL_FAILURE_RECORDED_NOT_PRIOR',prior_eligible=False,postcheck_reference=r,reader_sha256=a['reader_reference']['sha256']);b=m.enc(report);p=auditdir/'independent_readback.json';p.write_bytes(b);return m.ref(p,m.sha(b))
   def read_actual(r):
    if Path(r['path']).name=='postcheck.json':return m.read_current_attempt_post(r)
    if Path(r['path']).name=='independent_readback.json':return m.read(r)
    return read_memory(r)
   a.update(dispatch=dispatch,inspect_saved=inspect,read_saved=read_actual)
   with patch.object(m,'WORKER_OUTPUT',worker):
    result=read_memory(m.execute_full48(**a));row=result['rows'][4];self.assertEqual(row['outcome'],'AUDITED_TECHNICAL_FAILURE');self.assertEqual(result['summary']['unresolved_dispatch_count'],0)
    with self.assertRaisesRegex(ValueError,'Failed source'):m.read(row['postcheck_reference'])
    bad=dict(row['postcheck_reference'],sha256='0'*64)
    with self.assertRaisesRegex(ValueError,'bytes'):m.read_current_attempt_post(bad)
 def test_future_pins_before_read(self):
  with patch.object(m,'WORKER_SHA',None),patch.object(m,'FRESH_CLI',True),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'exists',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):m.run(receipt_contract_reference=dict(path=str(P),sha256='a'*64),execute=True)
if __name__=='__main__':unittest.main()
