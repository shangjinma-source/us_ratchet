"""Read-only halt evidence: explains minute gaps, never grants trade eligibility."""
from datetime import datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

SOURCE_URL = 'https://www.cboe.com/us/equities/market_statistics/halts/'
HEADER = ['Symbol', 'Company', 'Market', 'Halt', 'Reason', 'Resume Date', 'Quote Time', 'Resume Time']
NY = ZoneInfo('America/New_York')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row:
            self.rows.append(self.row)


def diagnose_halt_gaps(*, raw, receipt, ticker, session, missing_minutes, now):
    """All timestamps are aware; only wholly halted minutes may be explained.

    This snapshot is a current observation, not historical point-in-time proof.
    It cannot verify a security identity or authorize a resumed buy automatically.
    """
    require(type(raw) is bytes and 0 < len(raw) <= 2*1024*1024, 'HALT_RAW_BUDGET')
    require(receipt['url'] == SOURCE_URL and receipt['http_status'] == 200
            and receipt['raw_sha256'] == sha256(raw).hexdigest()
            and receipt['bytes'] == len(raw), 'HALT_SOURCE_BINDING')
    started = datetime.fromisoformat(receipt['started_at'])
    received = datetime.fromisoformat(receipt['received_at'])
    require(all(value.utcoffset() is not None for value in (started, received, now))
            and started <= received <= now, 'HALT_SOURCE_CLOCK')
    require(0 <= (now-received).total_seconds() < 300, 'HALT_SOURCE_STALE')
    require(type(ticker) is str and ticker and ticker == ticker.upper(), 'HALT_SYMBOL_REQUIRED')
    text = raw.decode('utf-8')
    require('All times are Eastern Time' in text, 'HALT_TIMEZONE_UNCONFIRMED')
    parser = TableRows()
    parser.feed(text)
    require(HEADER in parser.rows, 'HALT_TABLE_UNRECOGNIZED')
    events = []
    for row in parser.rows:
        if not row or row[0] != ticker:
            continue
        require(len(row) == len(HEADER) and row[2] == 'NASDAQ', 'HALT_ROW_DOMAIN')
        halted = datetime.strptime(row[3], '%m/%d/%Y %H:%M:%S').replace(tzinfo=NY)
        if halted.date().isoformat() != session:
            continue
        require(halted <= received, 'HALT_EVENT_FUTURE')
        resumed = None
        if row[7]:
            require(bool(row[5]), 'HALT_RESUME_DATE_REQUIRED')
            resumed = datetime.strptime(row[5]+' '+row[7], '%m/%d/%Y %H:%M:%S').replace(tzinfo=NY)
            require(halted < resumed <= received, 'HALT_RESUME_FUTURE_OR_INVERTED')
        events.append(dict(halted_at=halted.isoformat(), resumed_at=resumed.isoformat() if resumed else None,
                           reason=row[4], company=row[1]))
    explained, unexplained = [], []
    require(type(missing_minutes) is list and len(missing_minutes) <= 390
            and len(set(missing_minutes)) == len(missing_minutes), 'HALT_MINUTES_DOMAIN')
    for value in missing_minutes:
        minute = datetime.fromisoformat(value)
        require(minute.utcoffset() is not None and minute.second == 0 and minute.microsecond == 0
                and minute.astimezone(NY).date().isoformat() == session
                and minute+timedelta(minutes=1) <= received, 'HALT_MINUTE_INVALID')
        covered = any(datetime.fromisoformat(event['halted_at']) <= minute
                      and minute+timedelta(minutes=1) <= (datetime.fromisoformat(event['resumed_at'])
                          if event['resumed_at'] else received) for event in events)
        (explained if covered else unexplained).append(value)
    return dict(schema='HALT_GAP_DIAGNOSTIC_V1', ticker=ticker, session=session,
                source_url=SOURCE_URL, raw_sha256=receipt['raw_sha256'], observed_at=received.isoformat(),
                events=events, halt_explained_minutes=explained, unexplained_minutes=unexplained,
                all_gaps_explained=bool(missing_minutes) and not unexplained,
                trade_eligibility_granted=False, synthetic_bars_created=False,
                historical_pit_evidence=False, identity_verified=False,
                account_mutated=False, orders_created=False)
