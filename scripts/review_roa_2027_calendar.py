"""Audit saved 2027 planning sessions against pinned NYSE publication.
This does not certify Nasdaq 2027 or install any production calendar.
"""
from datetime import datetime,date,timedelta,time,timezone
from hashlib import sha256
import json,re
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup


def review(root):
 root=Path(root);directory=root/'tmp/calendar_2027_review_20261107'
 receipt=json.loads((directory/'receipt.json').read_bytes());raw=(directory/'nyse.html').read_bytes()
 if receipt['status']!=200 or sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('NYSE_SOURCE_CHANGED')
 soup=BeautifulSoup(raw.decode('utf-8'),'html.parser')
 table=next(t for t in soup.find_all('table') if '2027' in t.get_text())
 rows=[[c.get_text(' ',strip=True) for c in row.find_all(['th','td'])] for row in table.find_all('tr')]
 column=rows[0].index('2027');holidays=[]
 for row in rows[1:]:
  match=re.search(r', ([A-Za-z]+ \d+)',row[column])
  holidays.append(datetime.strptime('2027 '+match.group(1),'%Y %B %d').date().isoformat())
 if len(set(holidays))!=10:raise ValueError('HOLIDAY_TABLE_INCOMPLETE')
 saved_path=root/'tmp/forward_regular_calendar_20261016_v1/schedule.json'
 saved=json.loads(saved_path.read_bytes())
 for name,digest in saved['source_hashes'].items():
  if sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('SAVED_SOURCE_CHANGED')
 projected=[row for row in saved['sessions'] if row['date'].startswith('2027-')]
 first=date(2027,1,1);last=date.fromisoformat(projected[-1]['date']);expected=[];ny=ZoneInfo('America/New_York')
 day=first
 # This saved projection ends in October, before the published November early close.
 if last>=date(2027,11,1):raise ValueError('EARLY_CLOSE_REVIEW_REQUIRED')
 while day<=last:
  if day.weekday()<5 and day.isoformat() not in holidays:
   expected.append(dict(date=day.isoformat(),open_at=datetime.combine(day,time(9,30),ny).astimezone(timezone.utc).isoformat(),close_at=datetime.combine(day,time(16),ny).astimezone(timezone.utc).isoformat()))
  day+=timedelta(days=1)
 if [{k:r[k] for k in ('date','open_at','close_at')} for r in projected]!=expected:raise ValueError('SAVED_PROJECTION_MISMATCH')
 return dict(status='NYSE_PROJECTION_MATCHED_NASDAQ_2027_NOT_CONFIRMED',sessions=len(projected),first_2027_session=projected[0]['date'],end=projected[-1]['date'],
  january_sessions=[r['date'] for r in projected if r['date'].startswith('2027-01')],production_calendar_changed=False,eligible_for_production_adoption=False,
  sources={str((directory/'nyse.html').relative_to(root)).replace('\\','/'):receipt['sha256'],str(saved_path.relative_to(root)).replace('\\','/'):sha256(saved_path.read_bytes()).hexdigest()},
  nyse_url=receipt['url'],nasdaq_reviewed_urls=['https://www.nasdaq.com/market-activity/stock-market-holiday-schedule','https://www.nasdaq.com/holidayandtradinghours'])

if __name__=='__main__':
 root=Path(__file__).resolve().parents[1];result=review(root)
 (root/'tmp/calendar_2027_review_20261107/review.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result))
