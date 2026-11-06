"""Bounded Jan-2027 calendar candidate from reviewed Nasdaq standing rules.
No active configuration, account, or scheduler changes; --write is create-only.
"""
import argparse
from datetime import date,datetime,time,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_daily_continuity_normalizer import extend_reviewed_calendar


def prepare(root,write=False):
 root=Path(root).resolve()
 review_name='tmp/calendar_2027_review_20261107/nasdaq_january_rule_review.json'
 review=json.loads((root/review_name).read_bytes())
 if (review['reviewed_scope_start']!='2026-12-31' or review['reviewed_scope_end']!='2027-02-01'
     or review['excluded_dates']!=['2027-01-01','2027-01-18']
     or review['regular_open_et']!='09:30' or review['regular_close_et']!='16:00'):
  raise ValueError('BOUNDED_REVIEW_REQUIRED')
 rows=[];day=date(2026,12,31);end=date(2027,2,1);ny=ZoneInfo('America/New_York')
 while day<=end:
  if day.weekday()<5 and day.isoformat() not in review['excluded_dates']:
   rows.append(dict(date=day.isoformat(),timezone='America/New_York',open_at=datetime.combine(day,time(9,30),ny).astimezone(timezone.utc).isoformat(),close_at=datetime.combine(day,time(16),ny).astimezone(timezone.utc).isoformat(),early_close=False))
  day+=timedelta(days=1)
 def reference(name):return dict(path=name,sha256=sha256((root/name).read_bytes()).hexdigest())
 old_calendar=reference('research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json')
 old_training=reference('tmp/roa_training_schedule_through_20261231_20261106.json')
 schedule=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',calendar=[r['date'] for r in rows],sessions=rows,
  status='STANDING_RULE_DERIVED_CANDIDATE_NOT_INSTALLED',start=rows[0]['date'],end=rows[-1]['date'],
  source_hashes={review_name:reference(review_name)['sha256'],'scripts/prepare_roa_january_2027_calendar.py':reference('scripts/prepare_roa_january_2027_calendar.py')['sha256']})
 prior=json.loads((root/old_training['path']).read_bytes())
 merged={row['date']:row for row in prior['sessions']}
 for row in rows:merged.setdefault(row['date'],dict(date=row['date']))
 training=dict(prior,sessions=[merged[d] for d in sorted(merged)],end=rows[-1]['date'],method='Preserve original dates; append bounded Nasdaq standing-rule projection',
  source_references=[old_training,reference(review_name)],actual_unscheduled_closure_coverage_complete=False)
 if [r for r in training['sessions'] if r['date']<='2026-12-31']!=prior['sessions']:raise ValueError('HISTORICAL_TRAINING_CHANGED')
 january=[r['date'] for r in rows if r['date'].startswith('2027-01')]
 if len(january)!=19 or january[0]!='2027-01-04' or january[-1]!='2027-01-29':raise ValueError('JANUARY_BOUNDARY_INVALID')
 result=dict(status='CANDIDATE_NOT_INSTALLED',start=rows[0]['date'],end=rows[-1]['date'],january_sessions=len(january),first_january_session=january[0],first_february_session=rows[-1]['date'],previous_training_preserved=True,annual_nasdaq_calendar_claimed=False,account_changed=False,task_changed=False)
 if not write:return result
 out=root/'tmp/roa_january_calendar_candidate_20261107';out.mkdir(exist_ok=False)
 (out/'schedule.json').write_bytes(canonical(schedule))
 extension=reference((out/'schedule.json').relative_to(root).as_posix())
 calendar=extend_reviewed_calendar(root=root,previous=old_calendar,extension=extension)
 old=json.loads((root/old_calendar['path']).read_bytes())['sessions'];new=json.loads(calendar)['sessions']
 if [r for r in new if r['date']<='2026-12-31']!=old:raise ValueError('HISTORICAL_EXECUTION_CHANGED')
 (out/'calendar.json').write_bytes(calendar);(out/'training.json').write_bytes(canonical(training))
 result['artifacts']={name:reference((out/name).relative_to(root).as_posix()) for name in ('calendar.json','training.json','schedule.json')}
 (out/'receipt.json').write_bytes(canonical(result));return result

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
 print(json.dumps(prepare(Path(__file__).resolve().parents[1],args.write)))
