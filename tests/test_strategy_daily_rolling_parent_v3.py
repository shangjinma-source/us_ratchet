from copy import deepcopy
from datetime import datetime,timedelta,date
from hashlib import sha256
import json
import unittest
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_daily_rolling_parent_v3 import previous_session_parent,normalize_with_archived_parent
from data.strategy_daily_session_capture import encoded
import test_strategy_daily_continuity_normalizer as fixtures

class RollingParentTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ContinuityTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  f=self.f;self.root=f.root
  calendar=json.loads((self.root/f.capture.configuration['calendar']['path']).read_bytes())
  day=date(2026,10,21)
  for i in range(45):
   d=day+timedelta(days=i)
   if d.weekday()<5:
    opening=datetime.combine(d,datetime.min.time()).replace(hour=9,minute=30,tzinfo=ZoneInfo('America/New_York'))
    calendar['sessions'].append(dict(date=d.isoformat(),open=opening.isoformat(),close=opening.replace(hour=16,minute=0).isoformat()))
  self.calendar=self.put('long-fixture-calendar.json',canonical(calendar))
  f.capture.configuration['calendar']=self.calendar
  self.sessions=calendar['sessions']
  self.seed=json.loads((self.root/f.parent['path']).read_bytes())
  self.seed_paths={name:name for name in self.seed['source_sha256']}
  normalized=json.loads((self.root/self.seed['normalized_inputs_path']).read_bytes())
  sid=f.capture.configuration['security']['security_id']
  self.prices={row['date']:row['close'] for row in normalized['histories'][sid]['closes']}
  self.template=json.loads(f.capture.daily)
  self.configsha='a'*64
 def put(self,name,raw):
  path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as stream:stream.write(raw)
  return dict(path=name,sha256=sha256(raw).hexdigest())
 def parent(self,now):
  return previous_session_parent(root=self.root,calendar_reference=self.calendar,runs_root='runs',
   accepted_configuration_sha256={self.configsha},seed_receipt_reference=self.f.parent,
   seed_source_paths=self.seed_paths,now=now)
 def run_day(self,row):
  f=self.f;today=row['date'];f.now=datetime.fromisoformat(row['open'])-timedelta(minutes=30)
  index=self.sessions.index(row);window=self.sessions[index-20:index]
  for old in window:self.prices.setdefault(old['date'],'1000')
  body=deepcopy(self.template);series=body['chart']['result'][0]
  series['timestamp']=[int(datetime.fromisoformat(r['close']).timestamp()) for r in window]
  values=[float(self.prices[r['date']]) for r in window]
  series['indicators']['quote'][0]['close']=values;series['indicators']['adjclose'][0]['adjclose']=values
  f.capture.daily=canonical(body)
  f.target['payload']['target_month']=today[:7]
  f.target['target_id']=sha256(canonical(f.target['payload'])).hexdigest()
  parent=self.parent(f.now)
  result=f.capture.run_capture(clock=lambda:f.now)
  self.assertEqual(result['status'],'CAPTURED_TWENTY_SESSIONS_UNIT_REVIEW_REQUIRED',result)
  normalized=normalize_with_archived_parent(root=self.root,capture_directory='capture/'+today,
   expected_configuration_sha256=sha256(encoded(f.capture.configuration)).hexdigest(),parent=parent,
   state=f.accounts.read(),target=f.target,clock=lambda:f.now)
  self.assertEqual(normalized['status'],'CONDITIONAL_DAILY_EVIDENCE_READY_POLICY_UNCHANGED',normalized)
  receipt=normalized['receipt'];manifest={}
  for name,raw in normalized['files'].items():
   digest=sha256(raw).hexdigest();path='runs/'+today+'/files/'+digest+'.bin'
   if (self.root/path).exists():reference=dict(path=path,sha256=digest)
   else:reference=self.put(path,raw)
   manifest[name]=reference
  rr=self.put('runs/'+today+'/receipt.json',canonical(receipt))
  mr=self.put('runs/'+today+'/source-paths.json',canonical(manifest))
  self.put('runs/'+today+'/terminal.json',canonical(dict(status='DAILY_CONDITIONAL_PACKET_SAVED',session=today,
   configuration_sha256=self.configsha,receipt_reference=rr,manifest_reference=mr,finished_at=f.now.isoformat())))
  self.assertIsNone(receipt['release_sha256'])
  self.assertFalse(receipt['source_authenticated']);self.assertFalse(receipt['coverage_complete'])
  return receipt
 def test_twenty_two_successive_sessions_outlive_original_overlap(self):
  rows=[r for r in self.sessions if r['date']>'2026-10-20'][:22]
  before=self.f.accounts.path.read_bytes()
  for row in rows:receipt=self.run_day(row)
  latest=json.loads((self.root/('runs/'+rows[-1]['date']+'/source-paths.json')).read_bytes())
  ref=latest[receipt['normalized_inputs_path']]
  inputs=json.loads((self.root/ref['path']).read_bytes())
  self.assertTrue(all(r['date']>'2026-10-19' for r in next(iter(inputs['histories'].values()))['closes']))
  self.assertEqual(self.f.accounts.path.read_bytes(),before)
 def test_missing_previous_never_falls_back_to_seed(self):
  row=next(r for r in self.sessions if r['date']=='2026-10-22')
  with self.assertRaisesRegex(ValueError,'WAIT_PREVIOUS_SESSION_PACKET'):self.parent(datetime.fromisoformat(row['open']))

 def test_failed_or_tampered_previous_does_not_fallback(self):
  first=next(r for r in self.sessions if r['date']=='2026-10-21')
  self.run_day(first)
  now=datetime.fromisoformat(next(r for r in self.sessions if r['date']=='2026-10-22')['open'])
  manifest=json.loads((self.root/'runs/2026-10-21/source-paths.json').read_bytes())
  reference=next(iter(manifest.values()))
  (self.root/reference['path']).write_bytes(b'tampered')
  with self.assertRaisesRegex(ValueError,'SOURCE_HASH_CHANGED'):self.parent(now)
  (self.root/'runs/2026-10-21/terminal.json').write_bytes(canonical(dict(status='NEEDS_RECOVERY')))
  with self.assertRaisesRegex(ValueError,'WAIT_PREVIOUS_SESSION_RECOVERY'):self.parent(now)

if __name__=='__main__':unittest.main()
