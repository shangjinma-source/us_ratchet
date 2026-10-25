"""Bounded raw paper-source batch; one official capture, no source admission."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import reject_links, stamp
from data.current_quantity_v2_paper_action_sources import daily_url, fetch_daily_actions
from scripts.current_research_official_alert_capture import URL, fetch_official_feed, parse_official_feed


def capture(*, requests, output, clock=None, daily_fetch=None, official_fetch=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    daily_fetch = daily_fetch or fetch_daily_actions
    official_fetch = official_fetch or fetch_official_feed
    began = stamp(clock())
    require(type(requests) is list and 0 < len(requests) <= 10, 'PAPER_SHARED_LIMIT')
    require(len({r['security_id'] for r in requests}) == len(requests)
            and len({r['ticker'] for r in requests}) == len(requests), 'PAPER_SHARED_DUPLICATE')
    for row in requests:
        require(row['session'] == began.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                and stamp(row['requested_from']) < began < stamp(row['session_close']), 'PAPER_SHARED_SESSION')
    directory = Path(output).absolute(); reject_links(directory)
    directory.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        raw = value if type(value) is bytes else canonical(value)
        with (directory/name).open('xb') as stream: stream.write(raw)
    save('intent.json', dict(requests=requests, started_at=began.isoformat()))
    receipts = []; calls = 0
    try:
        def fetch(kind, row=None, ordinal=None):
            nonlocal calls
            started = stamp(clock()); calls += 1
            require(began <= started < min(stamp(r['session_close']) for r in requests), 'PAPER_SHARED_CLOCK')
            response = daily_fetch(row['ticker'], stamp(row['requested_from']), started) if kind == 'daily' else official_fetch()
            received = stamp(clock()); raw = response['body']
            require(type(raw) is bytes and 0 < len(raw) <= 4*1024*1024, 'PAPER_SHARED_BYTES')
            prefix = f'daily-{ordinal:03d}' if kind == 'daily' else 'official'
            receipt = dict(status='CAPTURED', attempts=1, http_status=response['status'],
                started_at=started.isoformat(), received_at=received.isoformat(),
                raw_sha256=sha256(raw).hexdigest(), stored_bytes=len(raw),
                url=daily_url(row['ticker'], stamp(row['requested_from']), started) if kind=='daily' else URL)
            save(prefix+'.response.bin', raw); save(prefix+'.receipt.json', receipt)
            require(started <= received < min(stamp(r['session_close']) for r in requests)
                    and response['status'] == 200, 'PAPER_SHARED_TRANSPORT')
            if kind == 'daily':
                chart=json.loads(raw)['chart']
                require(chart.get('error') is None and len(chart['result']) == 1
                        and chart['result'][0]['meta']['symbol'] == row['ticker'], 'PAPER_SHARED_IDENTITY')
            else:
                require(all(stamp(r['received_at']) <= started for r in receipts), 'PAPER_SHARED_OFFICIAL_ORDER')
                feed=parse_official_feed(raw, observed_at=received)
                require(not feed['channel']['future_publication'] and not feed['channel'].get('publication_time_issue')
                        and all(not r['future_publication'] and not r.get('publication_time_issue') for r in feed['items']),
                        'PAPER_SHARED_OFFICIAL_TIME')
            receipts.append(receipt)
        for ordinal,row in enumerate(requests): fetch('daily', row, ordinal)
        fetch('official')
        result=dict(status='SHARED_RAW_CAPTURE_NOT_ADMITTED', network_calls=calls,
            securities=len(requests), official_captures=1, account_mutated=False, registration_created=False)
        save('complete.json', result); return result
    except Exception as error:
        save('failed.json', dict(reason=str(error), network_calls=calls, retry_allowed=False))
        raise


def capture_files(directory, ordinal):
    """Preserve actual shared receipt bytes; the full reviewer validates them."""
    require(type(ordinal) is int and 0 <= ordinal < 10, 'PAPER_SHARED_ORDINAL')
    directory=Path(directory);reject_links(directory)
    require((directory/'complete.json').is_file(), 'PAPER_SHARED_INCOMPLETE')
    output={}
    for kind,prefix in [('daily',f'daily-{ordinal:03d}'),('official','official')]:
        for suffix in ('response.bin','receipt.json'):
            path=directory/(prefix+'.'+suffix);reject_links(path)
            require(path.stat().st_size<=4*1024*1024,'PAPER_SHARED_BYTES')
            output[kind+'.'+suffix]=path.read_bytes()
    return output
