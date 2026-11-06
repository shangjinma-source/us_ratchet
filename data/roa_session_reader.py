"""Read the existing pinned exchange calendar before or during its session."""
import json
from pathlib import Path
from hashlib import sha256
from core.strategy_account_difference import require,timestamp
CALENDAR='tmp/roa_january_calendar_candidate_20261107/calendar.json'
SHA='c2d84ac21abdb980c8b3d054ee8269bd9b70dbff7ef4c211210e328043b0b948'
class RoaSessionReader:
 def __init__(self,root):self.root=Path(root).resolve()
 def __call__(self,session):
  raw=(self.root/CALENDAR).read_bytes();require(sha256(raw).hexdigest()==SHA,'CALENDAR_SOURCE_CHANGED')
  document=json.loads(raw);require(document['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and document['exchange']=='NASDAQ','CALENDAR_SCHEMA')
  pins={CALENDAR:SHA}
  for source in document['source_references']:
   path=(self.root/source['path']).resolve();require(path.is_relative_to(self.root),'CALENDAR_PATH')
   require(sha256(path.read_bytes()).hexdigest()==source['sha256'],'CALENDAR_EVIDENCE_CHANGED');pins[source['path']]=source['sha256']
  rows=[s for s in document['sessions'] if s['date']==session];require(len(rows)==1,'SESSION_NOT_IN_CALENDAR')
  row=rows[0];require(timestamp(row['open'])<timestamp(row['close']),'SESSION_TIMES')
  return dict(session=session,previous_session=max((r['date'] for r in document['sessions'] if r['date']<session),default=None),open_at=row['open'],close_at=row['close'],source_hashes=pins,
   actual_unscheduled_closure_coverage_complete=document['actual_unscheduled_closure_coverage_complete'])

 def sessions(self):
  raw=(self.root/CALENDAR).read_bytes();require(sha256(raw).hexdigest()==SHA,'CALENDAR_SOURCE_CHANGED')
  days=[r['date'] for r in json.loads(raw)['sessions']]
  require(days==sorted(set(days)),'CALENDAR_ORDER')
  self(days[0])
  return days
