import unittest,importlib.util,sys,json,os
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
from hashlib import sha256
sys.path.insert(0,str(Path('.').resolve()))
STAGE=Path(os.environ.get('NEWS_BACKGROUND_STAGE_DIRECTORY','data'))
for name in ('news_background_context_v1','news_investment_model_v1','news_event_model_v1'):
 spec=importlib.util.spec_from_file_location('data.'+name,STAGE/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);setattr(__import__('data'),name,m)
ctx=sys.modules['data.news_background_context_v1'];account=sys.modules['data.news_investment_model_v1'];event=sys.modules['data.news_event_model_v1']
NOW=datetime(2026,10,28,12,tzinfo=timezone.utc)
def synthetic_package(root):
 directory=root/'data/cache/news/background/synthetic';directory.mkdir(parents=True)
 rows=[];pins={}
 for index,(ticker,period) in enumerate([('MRNA','Synthetic Q2'),('SNDK','Synthetic FY2027 Q1'),('SNDK','Synthetic FY2028-2030')]):
  text=('Explicitly synthetic background body, no issuer claim. '+str(index)+' ')*40
  body=directory/('body'+str(index)+'.txt');body.write_text(text,encoding='utf-8');key=body.relative_to(root).as_posix();h=sha256(body.read_bytes()).hexdigest();pins[key]=h
  rows.append(dict(id='background-'+str(index),role='BACKGROUND',ticker=ticker,issuer='Synthetic issuer',title='Synthetic old release',url='https://example.test/background',body_path=key,text_sha256=h,observed_at='2026-10-28T09:00:00Z',published_at=None,publication_date='2026-08-05',publication_time_candidates=[{'source':'synthetic-a','value':'2026-08-05T13:00:00Z'},{'source':'synthetic-b','value':'2026-08-05T20:00:00Z'}],publication_time_quality='CONFLICTING_SYNTHETIC_MINUTES',reference_period=period,limitations=['Synthetic periods are not comparable; not a replacement for FY2027 Q1.'],eligible_as_new_trigger=False,may_refresh_event_window=False))
 manifest=directory/'manifest.json';manifest.write_text(json.dumps({'events':[],'background_sources':rows,'source_hashes':pins}),encoding='utf-8')
 config={'manifest_path':manifest.relative_to(root).as_posix(),'manifest_sha256':sha256(manifest.read_bytes()).hexdigest()}
 (root/'data/cache/news/background_index_v1.json').write_text(json.dumps(config),encoding='utf-8')
 return config

def inputs(ticker='SNDK'):
 text='Synthetic current trigger; not a historical investment claim.'
 source=dict(id='trigger',title='synthetic',url='https://example.test',published_at='2026-10-27T12:00:00Z',observed_at='2026-10-28T10:00:00Z',security_ids=['sid'],tickers=[ticker],text=text,text_sha256=sha256(text.encode()).hexdigest(),content_kind='FULL_TEXT')
 positions=[dict(security_id='sid',ticker=ticker,original_qty=10,target_qty=10)]
 return [source],positions
class BackgroundTests(unittest.TestCase):
 def setUp(self):
  guard=patch('subprocess.Popen',side_effect=AssertionError('REAL_PROCESS_FORBIDDEN_IN_BACKGROUND_TEST'));self.no_process=guard.start();self.addCleanup(guard.stop);self.addCleanup(self.no_process.assert_not_called)
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.config=synthetic_package(self.root)
 def test_synthetic_full_bodies_and_conflict_periods_preserved(self):
  sources,positions=inputs();rows=ctx.load_background(self.root,self.config,sources,positions,NOW)
  self.assertEqual(len(rows),2);self.assertTrue(all(r['published_at'] is None for r in rows));self.assertTrue(all(len(r['text'])>2000 for r in rows))
  self.assertIn('FY2028',rows[1]['reference_period']);self.assertIn('FY2027 Q1',' '.join(rows[1]['limitations']))
  payload=ctx.attach_background({'sources':sources,'positions':positions},rows,NOW);self.assertEqual(payload['sources'][0]['role'],'TRIGGER');self.assertEqual(sources[0].get('role'),None)
 def test_observed_today_is_not_usable_in_historical_replay(self):
  sources,positions=inputs()
  with self.assertRaisesRegex(ValueError,'NOT_OBSERVED'):ctx.load_background(self.root,self.config,sources,positions,datetime(2026,10,1,tzinfo=timezone.utc))
 def test_wrong_sid_later_date_false_exact_time_and_hash_rejected(self):
  sources,positions=inputs();rows=ctx.load_background(self.root,self.config,sources,positions,NOW)
  for field,value in [('security_ids',['wrong']),('publication_date','2026-10-28'),('published_at','2026-08-05T13:00:00Z'),('text','truncated')]:
   bad=deepcopy(rows);bad[0][field]=value
   with self.assertRaises(ValueError):ctx.attach_background({'sources':sources,'positions':positions},bad,NOW)
 def test_background_cannot_be_action_quote(self):
  sources,positions=inputs();background=ctx.load_background(self.root,self.config,sources,positions,NOW)
  payload=ctx.attach_background({'sources':sources,'positions':positions},background,NOW)
  row=dict(security_id='sid',ticker='SNDK',reason='synthetic',action='EXIT',buy_fraction='0/1',holding_fraction='0/1',counterevidence=[],uncertainty=[],evidence=[dict(source_id=background[0]['id'],quote=background[0]['text'][:50])])
  with self.assertRaisesRegex(ValueError,'QUOTE_NOT_IN_SOURCE'):account._validate({'rows':[row]},payload)
  row['evidence']=[dict(source_id='trigger',quote=sources[0]['text'])];self.assertEqual(account._validate({'rows':[row]},payload)['rows'][0]['action'],'EXIT')
 def test_no_trigger_no_model_and_full_budget_no_truncation(self):
  sources,positions=inputs();background=ctx.load_background(self.root,self.config,sources,positions,NOW)
  with TemporaryDirectory() as cache,patch.object(account,'_invoke',side_effect=AssertionError('no model')),patch.object(event,'_invoke',side_effect=AssertionError('no model')):
   self.assertEqual(account.analyze_review([],positions,cache,background_sources=background)['attempts'],0)
   self.assertEqual(event.analyze_event([],positions,cache,background_sources=background)['attempts'],0)
   for model in (account.analyze_review,event.analyze_event):
    result=model(sources,positions,cache,background_sources=background,max_chars=2000);self.assertEqual(result['status'],'INPUT_BUDGET_EXCEEDED');self.assertEqual(result['attempts'],0)
 def test_cache_identity_binds_full_background_and_observation_without_model(self):
  sources,positions=inputs();background=ctx.load_background(self.root,self.config,sources,positions,NOW)
  changed=deepcopy(background);changed[0]['text']+=' New synthetic appendix.';changed[0]['text_sha256']=sha256(changed[0]['text'].encode()).hexdigest()
  changed_time=deepcopy(background);changed_time[0]['observed_at']='2026-10-28T09:22:00Z'
  for module,analyze in [(account,account.analyze_review),(event,event.analyze_event)]:
   with TemporaryDirectory() as cache,patch.object(module.ModelCoordinator,'reserve',side_effect=ValueError('TEST_BLOCK')),patch.object(module,'_invoke',side_effect=AssertionError('no model')):
    outputs=[analyze(sources,positions,cache,background_sources=value) for value in [background,changed,changed_time]]
    self.assertEqual(len({x['cache_key'] for x in outputs}),3);self.assertTrue(all(x['attempts']==0 for x in outputs))
 def test_missing_manifest_or_changed_full_text_fail_closed(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);body=root/'body';body.write_text('whole');manifest=root/'manifest';manifest.write_text(json.dumps({'events':[],'source_hashes':{'body':sha256(body.read_bytes()).hexdigest()}}));config={'manifest_path':'manifest','manifest_sha256':sha256(manifest.read_bytes()).hexdigest()};ctx.verify_manifest(root,config);body.write_text('changed')
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):ctx.verify_manifest(root,config)
if __name__=='__main__':unittest.main()
