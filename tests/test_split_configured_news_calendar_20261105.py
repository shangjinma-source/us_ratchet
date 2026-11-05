"""Actual composed news pipeline calendar, current-target authority and tamper refusal."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,unittest
import test_split_native_capture_configuration_20261105 as fixture
from data.news_risk_skill_v1 import PINS
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from docs.candidates.split_runtime_routes_20261105 import build_routes
from docs.candidates.split_configured_news_calendar_20261105 import attach_configured_event_calendar

class Tests(unittest.TestCase):
 def test_actual_pipeline_uses_current_authorized_calendar_every_time(self):
  builder=fixture.Tests();self.addCleanup(builder.doCleanups);case=builder.case();service=case['service'];f=case['f'];view=case['view'];provider=case['provider']
  for name in PINS:
   path=f.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((fixture.fixture.ROOT/name).read_bytes())
  self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.start_worker'));self.enterContext(patch('data.news_event_pipeline_v1.EventNewsPipeline.stop_worker'))
  prepared=build_routes(root=f.root,monthly_view=view,daily_service=service,journal=DailyAdviceJournalV1(f.root/'calendar-journal.sqlite3'),clock=lambda:f.now,validate_sources=service.validate_code,policy_references={'scope':'CONFIGURED_CALENDAR_FIXTURE'},timing_bundles=case['timing'],account_arguments=dict(database_path=f.store.path,account_id=f.store.read()['account_id'],resolver=provider.market.identity,clock=lambda:f.now))
  prepared=attach_configured_event_calendar(prepared=prepared,service=service);pipeline=prepared['event_pipeline'];target=service.monthly.current();before=f.store.read()
  result=pipeline.calendar_window(f.now.isoformat())
  self.assertEqual(result['target_id'],target['target_id']);self.assertEqual(result['session'],f.now.date().isoformat())
  config=service.validate_code();reference=config['authorizations'][target['target_id']];grant=json.loads(service._read(reference['path']))
  self.assertEqual(result['calendar_sha256'],grant['source_sha256'][grant['calendar']])
  path=f.root/reference['files'][grant['calendar']];original=path.read_bytes();path.write_bytes(original+b' ')
  try:
   with self.assertRaisesRegex(ValueError,'NATIVE_CONFIG_AUTH_SOURCE_CHANGED'):pipeline.calendar_window(f.now.isoformat())
  finally:path.write_bytes(original)
  # Real new target generation, not mocking the current-target lookup.
  fresh=view.generate(event_id='calendar-new-target',reason='EXPLICIT_RECONFIGURE',expected_revision=before['revision'],previous_target_id=target['target_id'])
  self.assertNotEqual(fresh['target_id'],target['target_id'])
  with self.assertRaisesRegex(ValueError,'NATIVE_CONFIG_NEW_TARGET_AUTHORIZATION_REQUIRED'):pipeline.calendar_window(f.now.isoformat())
  self.assertEqual(f.store.read(),before)
class BoundsTests(unittest.TestCase):
 def test_authority_expiry_clips_window_and_rejects_preopen_expiry(self):
  from docs.candidates.split_configured_news_calendar_20261105 import authorized_window
  from tempfile import TemporaryDirectory
  from types import SimpleNamespace
  from hashlib import sha256
  from core.strategy_account_ledger import canonical
  from data.news_event_calendar_v1 import window
  with TemporaryDirectory() as folder:
   raw=canonical(dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date='2026-12-01',open='2026-12-01T14:30:00+00:00',close='2026-12-01T21:00:00+00:00')]))
   (Path(folder)/'calendar.json').write_bytes(raw)
   reader=SimpleNamespace(root=Path(folder),source={'calendar':dict(path='calendar.json',sha256=sha256(raw).hexdigest())},validate=lambda:None)
   original=window(reader=reader,discovered_at='2026-12-01T14:20:00+00:00')
  clipped=authorized_window(original,'2026-12-01T14:32:00+00:00')
  self.assertEqual(clipped['valid_until'],'2026-12-01T14:32:00+00:00')
  self.assertEqual(original['valid_until'],'2026-12-01T14:40:00+00:00')
  for deadline in ('2026-12-01T14:29:00+00:00','2026-12-01T14:30:00+00:00'):
   with self.assertRaisesRegex(ValueError,'NATIVE_EVENT_AUTH_WINDOW_EMPTY'):authorized_window(original,deadline)
if __name__=='__main__':unittest.main()
