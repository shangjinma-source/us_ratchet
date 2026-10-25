"""Unified read-only source review for legacy and cap/exit advice."""
from collections import Counter
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from scripts.audit_legacy_daily_followup_sources_v2 import audit as legacy_audit
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_advice_followup_plan_v3 import plan_journal_page
from data.strategy_followup_cap_source_v2 import review_cap_event
from data.strategy_followup_frontier_source_v1 import review_frontier_event
from data.strategy_advice_followup_plan_v3 import FRONTIER_POLICY


def audit(root):
    root=Path(root).resolve();result=legacy_audit(root);rows=result['rows'];seen={r['event_id'] for r in rows}
    journal=DailyAdviceJournalV1(root/'data/strategy_account/daily_advice_v1.sqlite3')
    calendar=(root/'research_contracts/daily_calendar_2026_extension_v1/calendar.candidate.json').read_bytes()
    digest=sha256(calendar).hexdigest()
    if digest!='1440d82ecc956baab15df4b49da444e4878459e353cf7c280dd5d3dcf2a109af':raise ValueError('CALENDAR_CHANGED')
    now=datetime.now(timezone.utc)
    with sqlite3.connect(journal.path.as_uri()+'?mode=ro',uri=True) as db:
        records=db.execute('select event_id,account_id,body,digest from advice_events').fetchall()
    frontier_ids={eid for eid,account,raw,pin in records if json.loads(raw)['response'].get('policy_id')==FRONTIER_POLICY}
    rows=[row for row in rows if row['event_id'] not in frontier_ids];seen={row['event_id'] for row in rows}
    if len(records)>10000:raise ValueError('AUDIT_BOUND_EXCEEDED')
    plans={}
    for account in {r[1] for r in records}:
        cursor=0
        for _ in range(101):
            page=plan_journal_page(journal=journal,account_id=account,calendar_bytes=calendar,
                calendar_sha256=digest,now=now,root=root,after=cursor,limit=100)
            plans.update({r['event_id']:r for r in page['items']});cursor=page['next_cursor']
            if len(page['items'])<100:break
        else:raise ValueError('AUDIT_BOUND_EXCEEDED')
    for eid,account,raw,pin in records:
        if eid in seen or plans[eid]['status']!='PLANNED_NOT_CAPTURE_ADMITTED':continue
        row=dict(event_id=eid,due=sum(o['status']=='DUE' for o in plans[eid]['observations']),capture_admitted=False)
        try:
            if sha256(raw).hexdigest()!=pin:raise ValueError('EVENT_CHANGED')
            event=json.loads(raw)
            reviewer=review_frontier_event if event['response'].get('policy_id')==FRONTIER_POLICY else review_cap_event
            checked=reviewer(root=root,event=event)
            row.update(checked,status='ARCHIVE_INTEGRITY_AND_TARGET_RECOMPUTED',
                       remaining='FOLLOWUP_CLOSE_REVIEW_REQUIRED')
        except (AssertionError,ValueError,KeyError,TypeError,OSError) as error:
            row.update(status='SOURCE_REVIEW_BLOCKED',reason=str(error))
        rows.append(row)
    return dict(observed_at=now.isoformat(),rows=rows,statuses=dict(Counter(r['status'] for r in rows)),
                capture_admitted=False,account_writes=False,network_calls=0)
