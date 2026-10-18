"""Only synthetic plans; independent module never imports or calls production code."""
import copy,unittest,tempfile,json
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from scripts import ndx_variable_prefix_capture_independent_readback_20261003 as r
from test_ndx_variable_prefix_capture_research import fixture,csv,resign,m

def arguments(a,plan):
 return dict(plan=plan,parent=a['parent'],source_bytes=a['source_bytes'],source_references=a['source_references'],baseline_bytes=a['baseline_bytes'],tzif_bytes=a['tzif_bytes'],tzif_reference=a['tzif_reference'],start=a['capture_started_at'],end=a['capture_completed_at'])

def file_fixture(root):
 a=fixture();legacy=a['parent'];h=copy.deepcopy(legacy['document']);files=root/'sources';files.mkdir()
 mapped={}
 for n,(path,digest)in enumerate(legacy['readback']['source_hashes'].items()):
  b=path.encode()
  for t in ('QQQ','SPY'):
   if path==h['baseline_references'][t]['path']:b=a['baseline_bytes'][t]
  p=files/str(n);p.write_bytes(b);mapped[path]=dict(path=str(p),sha256=r.sha(b))
 def rewrite(v):
  if type(v)is list:return [rewrite(x)for x in v]
  if type(v)is dict:
   if 'path'in v and 'sha256'in v and v['path']in mapped:return dict(v,**mapped[v['path']])
   return {mapped[k]['path']if k in mapped else k:mapped[k]['sha256']if k in mapped and type(x)is str else rewrite(x)for k,x in v.items()}
  return v
 h=rewrite(h)
 for e,attempt in zip(h['observations'],h['parent_attempt_inventory']):
  e['observation_id']=r.sha(r.encode(e['observation_identity']));attempt['observation_id']=e['observation_id']
 history=root/'history';history.mkdir();(history/'started.json').write_text('{}')
 def write(p,d):p.write_bytes(r.encode(d));return dict(path=str(p),sha256=r.sha(p.read_bytes()))
 hr=write(history/'history.json',h);pub=copy.deepcopy(legacy['publication']);pub.update(history_reference=hr,source_hashes=h['source_hashes']);pr=write(history/'publication.json',pub)
 reader=files/'reader.py';reader.write_bytes(b'# inert history reader');rr=dict(path=str(reader),sha256=r.sha(reader.read_bytes()))
 audit=copy.deepcopy(legacy['readback']);audit.update(history_reference=hr,publication_reference=pr,reader_sha256=rr['sha256'],source_hashes=dict(h['source_hashes']))
 for v in (hr,pr,rr):audit['source_hashes'][v['path']]=v['sha256']
 ar=write(files/'audit.json',audit);parents=dict(reference=hr,publication_reference=pr,readback_reference=ar,reader_reference=rr);a['parent']=dict(parents,document=h,publication=pub,readback=audit)
 pins={}
 for role in ('producer','core','scoped','base','tzif'):
  p=files/(role+'.source');p.write_bytes(a['tzif_bytes']if role=='tzif'else ('# inert '+role).encode());pins[role]=(str(p),r.sha(p.read_bytes()))
 cap=root/'capture';cap.mkdir();snap={}
 for t in ('QQQ','SPY'):
  p=cap/(t+'.csv');p.write_bytes(a['source_bytes'][t]);snap[t]=dict(path=str(p),sha256=r.sha(p.read_bytes()))
 tz=cap/'New_York.tzif';tz.write_bytes(a['tzif_bytes']);tr=dict(path=str(tz),sha256=r.sha(tz.read_bytes()));a['source_references']=snap;a['tzif_reference']=tr
 plan=m.plan_history_capture(**a)
 base={path:digest for path,digest in pins.values()}
 for v in parents.values():base[v['path']]=v['sha256']
 for obj in (h,pub,audit):base.update(obj['source_hashes'])
 for v in h['baseline_references'].values():base[v['path']]=v['sha256']
 inputs={k:dict(path=v[0],sha256=v[1])for k,v in pins.items()if k!='producer'};flags=dict.fromkeys(r.WRAPPER_FALSE,False)
 write(cap/'started.json',dict(schema='VARIABLE_PREFIX_CAPTURE_STARTED_V1',parent_references=parents,input_references=inputs,source_hashes=base,retry_allowed=False,**flags))
 sources=dict(base)
 for v in list(snap.values())+[tr]:sources[v['path']]=v['sha256']
 live={t:dict(path=str(root/'data/cache'/f'{t}.csv'),sha256=snap[t]['sha256'])for t in snap}
 cr=write(cap/'capture.json',dict(schema='SOURCE_BOUND_VARIABLE_PREFIX_CAPTURE_V1',plan=plan,parent_references=parents,input_references=inputs,captured_artifacts=dict(snap,tzif=tr),current_cache_references=live,current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',source_hashes=sources,capture_started_at=a['capture_started_at'],capture_completed_at=a['capture_completed_at'],clock_captured_by_runner=True,external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',**flags))
 pp=write(cap/'publication.json',dict(schema='VARIABLE_PREFIX_CAPTURE_PUBLICATION_V1',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=cr,source_hashes=sources,**flags))
 return dict(ROOT=root,PARENT=cap,OUTPUT=root/'readback',CAPTURE_SHA=cr['sha256'],PUBLICATION_SHA=pp['sha256'],PARENT_BOUND={k:(v['path'],v['sha256'])for k,v in parents.items()},PINS=pins),live

class Tests(unittest.TestCase):
 def test_single_no_new_two_appends_cross_month_and_no_producer_calls(self):
  for second,day in ((False,None),(True,None),(True,'2026-11-02')):
   a=fixture(second,day);p=m.plan_history_capture(**a)
   with patch.object(m,'plan_history_capture',side_effect=AssertionError('independent')),patch.object(r.Path,'read_bytes',side_effect=AssertionError('pure inspection')):out=r.inspect_plan(**arguments(a,p))
   self.assertEqual(out['parent_typed_row_count'],66+int(second));self.assertEqual(out['status'],'ONE_NEW_SESSION_CANDIDATE_NOT_OBSERVED');self.assertFalse(p['timeliness_verified'])
  a=fixture();a['source_bytes']=copy.deepcopy(a['baseline_bytes'])
  for t in ('QQQ','SPY'):resign(a,t)
  self.assertEqual(r.inspect_plan(**arguments(a,m.plan_history_capture(**a)))['status'],'NO_NEW_SESSION')
 def test_full_original_prefix_revision_mismatch_multiple_and_preclose(self):
  for mode in ('oldrevision','revision','missing','mismatch','multiple','preclose'):
   a=fixture();days=[x['session']for x in a['parent']['document']['known_typed_rows']]
   if mode=='oldrevision':a['source_bytes']['QQQ']=a['source_bytes']['QQQ'].replace(b'2020-01-02,5',b'2020-01-02,6')
   elif mode=='revision':a['source_bytes']['QQQ']=a['source_bytes']['QQQ'].replace((days[0]+',10,12,8,10').encode(),(days[0]+',10,12,8,11').encode())
   elif mode=='missing':a['source_bytes']['QQQ']=csv(days[1:]+['2026-10-05'],True)
   elif mode=='mismatch':a['source_bytes']['SPY']=csv(days+['2026-10-06'],True)
   elif mode=='multiple':a['source_bytes']={t:csv(days+['2026-10-05','2026-10-06'],True)for t in ('QQQ','SPY')}
   else:a['capture_started_at']='2026-10-05T19:59:59+00:00'
   for t in ('QQQ','SPY'):resign(a,t)
   p=m.plan_history_capture(**a);out=r.inspect_plan(**arguments(a,p));self.assertEqual(out['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
   p['candidate_session']='2026-10-05'
   with self.assertRaises(ValueError):r.inspect_plan(**arguments(a,p))
 def test_parent_counts_reference_inventory_and_false_type(self):
  for mode in ('count','inventory','baseline','row','source','false'):
   a=fixture();p=m.plan_history_capture(**a)
   if mode=='count':a['parent']['readback']['counts']['new_observation_count']=True
   elif mode=='inventory':a['parent']['document']['parent_attempt_inventory'][0]['status']='STARTED_ONLY'
   elif mode=='baseline':a['parent']['document']['baseline_references']['SPY']['sha256']='b'*64
   elif mode=='row':a['parent']['document']['known_typed_rows'][0]['sequence']=True
   elif mode=='source':a['parent']['readback']['source_hashes']={}
   else:p['candidate_seal_allowed']=0
   with self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):r.inspect_plan(**arguments(a,p))
 def test_raw_hash_tzif_close_and_scoped_bounds(self):
  a=fixture();a['capture_started_at']='2026-10-05T20:00:00+00:00';p=m.plan_history_capture(**a);self.assertEqual(r.inspect_plan(**arguments(a,p))['candidate_session'],'2026-10-05')
  for mode in ('bytes','tzif','bounds','time'):
   b=copy.deepcopy(a);q=copy.deepcopy(p)
   if mode=='bytes':b['source_bytes']['QQQ']+=b'\n'
   elif mode=='tzif':b['tzif_bytes']+=b'x'
   elif mode=='bounds':b['source_bytes']['QQQ']=b['source_bytes']['QQQ'].replace(b'2026-10-05,10',b'2026-10-05,5');resign(b,'QQQ')
   else:b['capture_completed_at']='2026-10-05T19:00:00+00:00'
   with self.subTest(mode=mode),self.assertRaises(ValueError):r.inspect_plan(**arguments(b,q))
 def test_pending_before_io_and_live_cache_not_permanent(self):
  with patch.object(r,'CAPTURE_SHA',None),patch.object(r.Path,'read_bytes',side_effect=AssertionError('No IO')),patch.object(r.Path,'exists',side_effect=AssertionError('No namespace IO')):
   with self.assertRaises(ValueError):r.readback(execute=True)
  with self.assertRaises(ValueError):r.no_live({str(r.ROOT/'data/cache/QQQ.csv'):'a'*64})
  r.no_live({str(r.PARENT/'QQQ.csv'):'a'*64})

 def test_complete_files_live_refresh_and_snapshot_drift_failure(self):
  for drift in (False,True):
   with tempfile.TemporaryDirectory()as td:
    bindings,live=file_fixture(Path(td));actual_read=Path.read_bytes;actual_save=r.save
    for v in live.values():p=Path(v['path']);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'newly refreshed cache after capture')
    def checked_read(path):
     if str(path)in {x['path']for x in live.values()}:raise AssertionError('must not read current live cache')
     return actual_read(path)
    def save(path,obj):
     result=actual_save(path,obj)
     if drift and path.name=='independent_readback.json':(bindings['PARENT']/'QQQ.csv').write_bytes(b'changed after report')
     return result
    with ExitStack()as stack:
     for k,v in bindings.items():stack.enter_context(patch.object(r,k,v))
     stack.enter_context(patch.object(Path,'read_bytes',checked_read));stack.enter_context(patch.object(r,'save',side_effect=save))
     if drift:
      with self.assertRaisesRegex(ValueError,'Source drift'):r.readback(execute=True)
      self.assertTrue((bindings['OUTPUT']/'failure.json').exists())
      with self.assertRaisesRegex(ValueError,'Create-only'):r.readback(execute=True)
     else:
      ref=r.readback(execute=True);report=json.loads(actual_read(Path(ref['path'])));self.assertEqual(report['status'],'PASS');self.assertFalse(report['current_live_cache_read_or_reverified']);self.assertEqual(report['counts']['parent_typed_row_count'],66)
      self.assertTrue(all(v['path']not in report['source_hashes']for v in live.values()))

if __name__=='__main__':unittest.main()
