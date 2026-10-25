"""Group price-source requests while retaining every original observation."""
from hashlib import sha256
from data.strategy_daily_advice_journal_v1 import encoded
from data.strategy_followup_queue_v1 import IDENTITY_FIELDS
from core.strategy_account_difference import require, timestamp


def group_due_observations(observations, *, now):
    require(now.tzinfo is not None,'GROUP_AWARE_CLOCK_REQUIRED')
    groups={};seen=set();identities={};waiting=0
    for row in observations:
        key=sha256(encoded({name:row[name] for name in IDENTITY_FIELDS})).hexdigest()
        require(key==row['observation_id'] and key not in seen,'GROUP_OBSERVATION_IDENTITY')
        seen.add(key)
        if row['observation_close'] is None or timestamp(row['observation_close'])>now:
            waiting+=1;continue
        require(row['observation_session'] is not None,'GROUP_OBSERVATION_SESSION')
        sid=row['security_id'];ticker=row['ticker']
        require(type(ticker)is str and bool(ticker),'GROUP_TICKER_REQUIRED')
        require(sid not in identities or identities[sid]==ticker,'GROUP_TICKER_CONFLICT')
        identities[sid]=ticker
        require(row['side'] in {'BUY','SELL'},'GROUP_SIDE')
        group=groups.setdefault((sid,ticker),dict(security_id=sid,ticker=ticker,observations=[],sessions={}))
        day=row['observation_session'];close=row['observation_close']
        require(day not in group['sessions'] or group['sessions'][day]==close,'GROUP_SESSION_CLOSE_CONFLICT')
        group['sessions'][day]=close
        # Store references individually, not an averaged order or a net trade.
        group['observations'].append(dict(observation_id=key,event_id=row['event_id'],
            event_sha256=row['event_sha256'],side=row['side'],reference_session=row['reference_session'],
            observation_session=day,reference_limit=row['reference_limit'],reference_quantity=row['reference_quantity']))
    rows=[]
    for key in sorted(groups):
        group=groups[key]
        group['observations'].sort(key=lambda row:row['observation_id'])
        group['sessions']=dict(sorted(group['sessions'].items()))
        group['earliest_reference_session']=min(row['reference_session'] for row in group['observations'])
        rows.append(group)
    return dict(schema='DAILY_FOLLOWUP_CAPTURE_GROUPS_V1',groups=rows,
        due_observations=sum(len(g['observations']) for g in rows),waiting_observations=waiting,
        proposed_daily_requests=len(rows),proposed_official_requests=int(bool(rows)),
        capture_admitted=False,network_calls=0,performance_computed=False)
