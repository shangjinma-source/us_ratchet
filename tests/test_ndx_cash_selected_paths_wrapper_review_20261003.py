from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).parent))
from test_ndx_cash_neighbor_selected_paths_20261003 import staged
from scripts import ndx_cash_neighbor_selected_paths_20261003 as m
from backtest import ndx_cash_neighbor_selected_path_requests_research as pure

class Review(unittest.TestCase):
 def test_mismatched_signed_request_identity_never_dispatches(self):
    for field,value in [('scenario_id','wrong'),('scenario_index',1),('status','REUSE_EXISTING_PAIRED_PATH')]:
      with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES)):
        entries=staged(Path(td));p=Path(entries[0]['request_reference']['path']);d=json.loads(p.read_bytes());d['request'][field]=value;p.write_bytes(m.enc(d));entries[0]['request_reference']['sha256']=m.sha(p.read_bytes());calls=[]
        out=m.execute_requests(entries,{},dict(account_core=SimpleNamespace(account_path=lambda **k:calls.append(k)),request_core=pure));self.assertEqual(calls,[]);self.assertEqual(out['attempted_scenario_ids'],[]);self.assertEqual(len(out['undispatched_scenario_ids']),40)
 def test_none_return_persisted_as_validation_failure_not_infeasibility(self):
    with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES)):
      entries=staged(Path(td));calls=[]
      def noresult(**args):
        self.assertTrue((Path(td)/'scenario-00/started.json').exists());calls.append(args);return None
      out=m.execute_requests(entries,{},dict(account_core=SimpleNamespace(account_path=noresult),request_core=pure));self.assertEqual(len(calls),1);self.assertEqual(out['unresolved_scenario_ids'],['scenario-0']);self.assertEqual(len(out['undispatched_scenario_ids']),39);self.assertEqual(out['completed_rows'],[])
      raw=json.loads((Path(td)/'scenario-00/raw.json').read_bytes());post=json.loads((Path(td)/'scenario-00/postcheck.json').read_bytes());self.assertEqual(raw['returned_account_count'],0);self.assertEqual(post['outcome'],'VALIDATION_FAILURE');self.assertIsNone(raw['account'])
      m.execute_requests(entries,{},dict(account_core=SimpleNamespace(account_path=noresult),request_core=pure));self.assertEqual(len(calls),1)
 def test_reuse_only_reference_and_resource_stop_before_next_dispatch(self):
    with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)),patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=m.MIN_FREE_BYTES-1)):
      entries=staged(Path(td));p=Path(entries[0]['request_reference']['path']);d=json.loads(p.read_bytes());r=d['request'];r['status']='REUSE_EXISTING_PAIRED_PATH';r['accounting_request']=None;r['reused_candidate_path_reference']=r['selection']['old_selected_path']['reference'];p.write_bytes(m.enc(d));entries[0].update(status=r['status'],request_reference=m.ref(p,m.sha(p.read_bytes())))
      calls=[];out=m.execute_requests(entries,{},dict(account_core=SimpleNamespace(account_path=lambda **k:calls.append(k)),request_core=pure));self.assertEqual(calls,[]);self.assertEqual(len(out['completed_rows']),1);self.assertEqual(len(out['undispatched_scenario_ids']),39);self.assertEqual(out['unresolved_scenario_ids'],[]);self.assertFalse(out['controls_executed']);self.assertEqual(out['completed_rows'][0]['candidate_reference'],r['reused_candidate_path_reference']);self.assertFalse(list(Path(td).glob('*/raw.json')))
if __name__=='__main__':unittest.main()
