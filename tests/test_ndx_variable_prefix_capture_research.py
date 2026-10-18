"""Synthetic histories/CSV only; never captures or publishes actual observations."""
import copy,hashlib,importlib.util,struct,unittest
from pathlib import Path
from backtest import ndx_variable_prefix_capture_research as m
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('history_tests',ROOT/'tests/test_ndx_prospective_observation_parent_history_independent_readback_20261003.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def csv(days,badold=False):
    prefix='2020-01-02,5,12,8,10,100\n'if badold else ''
    return ('Date,Open,High,Low,Close,Volume\n'+prefix+''.join(d+',10,12,8,10,100\n'for d in days)).encode()
def reference(p,b):return dict(path=p,sha256=hashlib.sha256(b).hexdigest())
def replace(v,old,new):
    if isinstance(v,dict):return {k:replace(x,old,new)for k,x in v.items()}
    if isinstance(v,list):return [replace(x,old,new)for x in v]
    return new if v==old else v
def fixture(second=False,newday=None):
    h,g,previous,o=f.fixture(second);days=[r['session']for r in h['known_typed_rows']];base={t:csv(days,True)for t in ('QQQ','SPY')}
    for t in base:h=replace(h,h['baseline_references'][t]['sha256'],m.digest(base[t]))
    p=f.f.envelope(h,'history_current');p['readback']['counts']=dict(typed_row_count=len(days),observation_count=len(h['observations']),new_observation_count=1,first_actual_observed_session_by_month=copy.deepcopy(h['first_actual_observed_session_by_month']))
    newday=newday or ('2026-10-06'if second else '2026-10-05');raw={t:csv(days+[newday],True)for t in base}
    header=b'TZif2'+b'\0'*15+struct.pack('>6i',0,0,0,0,1,4);block=struct.pack('>iBB',-18000,0,0)+b'EST\0';tz=header+block+header+block+b'\nEST5EDT,M3.2.0,M11.1.0\n'
    return dict(parent=p,source_bytes=raw,source_references={t:reference('current'+t,raw[t])for t in raw},baseline_bytes=base,capture_started_at=newday+'T21:00:00+00:00',capture_completed_at=newday+'T21:00:01+00:00',tzif_bytes=tz,tzif_reference=reference('tzif',tz))
def resign(a,t):a['source_references'][t]=reference('current'+t,a['source_bytes'][t])
class Tests(unittest.TestCase):
 def test_variable_prefix_late_first_stays_first_compact(self):
    for second in (False,True):
      a=fixture(second);before=copy.deepcopy(a);out=m.plan_history_capture(**a)
      self.assertEqual(out['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED');self.assertEqual(out['candidate_sequence'],67+int(second));self.assertEqual(out['proposed_first_actual_session_of_month'],'2026-10-02');self.assertEqual(a,before)
      self.assertFalse(out['raw_bytes_embedded']);self.assertTrue(all(out[k]is False for k in m.FLAGS));self.assertEqual(len(out['source_evidence']['SPY']['excluded_before_scope_ohlc_diagnostics']),1)
    out=m.plan_history_capture(**fixture(True,'2026-11-02'));self.assertEqual(out['proposed_first_actual_session_of_month'],'2026-11-02')
 def test_revisions_prefix_and_two_sources_never_intersect(self):
    for mode in ('revision','missing','multiple','different','none'):
      a=fixture();days=[r['session']for r in a['parent']['document']['known_typed_rows']]
      if mode=='revision':a['source_bytes']['QQQ']=a['source_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10,12,8,11,100',1)
      elif mode=='missing':a['source_bytes']['QQQ']=csv(days[1:]+['2026-10-05'])
      elif mode=='multiple':a['source_bytes']={t:csv(days+['2026-10-05','2026-10-06'])for t in days and ('QQQ','SPY')}
      elif mode=='different':a['source_bytes']['SPY']=csv(days+['2026-10-06'])
      else:a['source_bytes']={t:a['baseline_bytes'][t]for t in ('QQQ','SPY')}
      for t in ('QQQ','SPY'):resign(a,t)
      out=m.plan_history_capture(**a);self.assertIsNone(out['candidate_session']);self.assertEqual(out['status'],'NO_NEW_SESSION'if mode=='none'else 'BLOCKED_SOURCE_DIAGNOSTICS')
 def test_parent_audit_inventory_and_baseline_roles_failclosed(self):
    for mode in ('unresolved','deleted','baseline','audit','source','bool','parentref'):
      a=fixture();h=a['parent']['document']
      if mode=='unresolved':h['parent_attempt_inventory'][0]['status']='STARTED_ONLY'
      elif mode=='deleted':h['known_typed_rows'].pop(0)
      elif mode=='baseline':a['baseline_bytes']['QQQ']=b'wrong'
      elif mode=='audit':a['parent']['readback']['source_hashes']={}
      elif mode=='source':a['source_references']['QQQ']['sha256']='0'*64
      elif mode=='bool':a['parent']['readback']['counts']['new_observation_count']=True
      else:a['parent']['readback']['history_reference']['sha256']='f'*64
      with self.subTest(mode=mode),self.assertRaises(ValueError):m.plan_history_capture(**a)
 def test_full_scope_ohlc_tzif_clock_close_and_late(self):
    a=fixture();a['source_bytes']['QQQ']=a['source_bytes']['QQQ'].replace(b'2026-10-05,10,12,8,10',b'2026-10-05,5,12,8,10');resign(a,'QQQ')
    with self.assertRaises(ValueError):m.plan_history_capture(**a)
    a=fixture();a['capture_started_at']='2026-10-05T19:59:59+00:00';self.assertEqual(m.plan_history_capture(**a)['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
    a=fixture();a['capture_completed_at']='2026-10-05T20:00:00+00:00'
    with self.assertRaises(ValueError):m.plan_history_capture(**a)
    a=fixture();a['capture_started_at']='2026-10-07T21:00:00+00:00';a['capture_completed_at']='2026-10-07T21:00:01+00:00';self.assertEqual(m.plan_history_capture(**a)['candidate_session'],'2026-10-05')
    a=fixture();a['tzif_bytes']+=b'changed'
    with self.assertRaises(ValueError):m.plan_history_capture(**a)
if __name__=='__main__':unittest.main()
