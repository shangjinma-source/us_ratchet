"""Plan current journal observations durably; no HTTP, fills, or account changes."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_advice_followup_plan_v1 import plan_journal_page
from data.strategy_followup_queue_v1 import store_plans
from data.strategy_followup_capture_groups_v1 import group_due_observations


def run(root, *, group_output=None):
    root=Path(root).resolve();journal=DailyAdviceJournalV1(root/'data/strategy_account/daily_advice_v1.sqlite3')
    calendar=(root/'research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json').read_bytes()
    digest=sha256(calendar).hexdigest()
    if digest!='1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af':raise ValueError('QUEUE_CALENDAR_CHANGED')
    now=datetime.now(timezone.utc);observations=[];scanned=0
    with sqlite3.connect(journal.path.as_uri()+'?mode=ro',uri=True) as db:
        accounts=db.execute('SELECT DISTINCT account_id FROM advice_events').fetchall()
    for (account,) in accounts:
        cursor=0
        for _ in range(100):
            page=plan_journal_page(journal=journal,account_id=account,calendar_bytes=calendar,
                calendar_sha256=digest,now=now,after=cursor,limit=100)
            scanned+=len(page['items']);cursor=page['next_cursor']
            observations.extend(o for item in page['items'] for o in item.get('observations',[]))
            if len(page['items'])<100:break
        else:raise ValueError('QUEUE_SCAN_BOUND_REACHED')
    result=store_plans(root/'data/strategy_advice_followup/queue',observations)
    groups=group_due_observations(observations,now=now)
    if group_output is not None:
        with Path(group_output).open('x',encoding='utf-8') as stream:
            json.dump(groups,stream,ensure_ascii=False,indent=2)
    return dict(result,scanned=scanned,observations=len(observations),
        due=groups['due_observations'],proposed_daily_requests=groups['proposed_daily_requests'],
        proposed_official_requests=groups['proposed_official_requests'],observed_at=now.isoformat(),network_calls=0)


if __name__=='__main__':print(json.dumps(run(Path.cwd())))
