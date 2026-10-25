"""Current halt-source validation for a trusted security/session mapping.

This evidence permits coverage checks only; it does not authorize orders or
establish point-in-time historical data or security identity.
"""
from datetime import datetime
from hashlib import sha256
from html.parser import HTMLParser

from data.strategy_halt_gap_diagnostic_v1 import HEADER, NY, SOURCE_URL, require


class HaltTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.stack = []
        self.heading = ''
        self.heading_parts = None

    def handle_starttag(self, tag, attrs):
        if tag == 'h3': self.heading_parts = []
        if tag == 'table':
            self.stack.append(dict(rows=[], row=None, cell=None, heading=self.heading))
        elif self.stack:
            table = self.stack[-1]
            if tag == 'tr': table['row'] = []
            if tag in ('td', 'th') and table['row'] is not None: table['cell'] = []

    def handle_data(self, value):
        if self.heading_parts is not None: self.heading_parts.append(value)
        if self.stack and self.stack[-1]['cell'] is not None:
            self.stack[-1]['cell'].append(value)

    def handle_endtag(self, tag):
        if tag == 'h3' and self.heading_parts is not None:
            self.heading = ' '.join(' '.join(self.heading_parts).split())
            self.heading_parts = None
        if not self.stack: return
        table = self.stack[-1]
        if tag in ('td', 'th') and table['cell'] is not None:
            table['row'].append(' '.join(' '.join(table['cell']).split()))
            table['cell'] = None
        elif tag == 'tr' and table['row'] is not None:
            table['rows'].append(table['row']); table['row'] = None
        elif tag == 'table':
            self.tables.append(self.stack.pop())


def aware(value):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    require(isinstance(parsed, datetime) and parsed.utcoffset() is not None, 'HALT_AWARE_TIME')
    return parsed


def verified_halt_intervals(*, raw, receipt, security_id, ticker, session,
                            session_open, session_close, now):
    require(type(raw) is bytes and 0 < len(raw) <= 2*1024*1024, 'HALT_RAW_BUDGET')
    require(receipt['url'] == SOURCE_URL and receipt['http_status'] == 200
            and receipt['raw_sha256'] == sha256(raw).hexdigest()
            and receipt['bytes'] == len(raw), 'HALT_SOURCE_BINDING')
    started, received, current, opening, closing = map(aware,
        (receipt['started_at'], receipt['received_at'], now, session_open, session_close))
    require(started <= received <= current and 0 <= (current-received).total_seconds() < 300,
            'HALT_SOURCE_CLOCK_OR_STALE')
    require(opening < closing and all(value.astimezone(NY).date().isoformat() == session
            for value in (opening, closing, received, current)), 'HALT_SESSION_MISMATCH')
    require(type(security_id) is str and bool(security_id) and type(ticker) is str
            and ticker and ticker == ticker.upper(), 'HALT_IDENTITY_REQUIRED')
    text = raw.decode('utf-8')
    require('All times are Eastern Time' in text, 'HALT_TIMEZONE_UNCONFIRMED')
    parser = HaltTables(); parser.feed(text); parser.close()
    require(not parser.stack, 'HALT_TABLE_UNCLOSED')
    tables = [table['rows'] for table in parser.tables
              if table['heading'] == 'Non-Cboe Listed Halts' and HEADER in table['rows']]
    require(len(tables) == 1, 'HALT_TABLE_AMBIGUOUS_OR_MISSING')
    rows = tables[0]
    require(rows.count(HEADER) == 1, 'HALT_HEADER_DUPLICATE')
    intervals = []
    for row in rows[rows.index(HEADER)+1:]:
        if not row or row[0] != ticker: continue
        require(len(row) == len(HEADER) and row[2] == 'NASDAQ', 'HALT_ROW_DOMAIN')
        halted = datetime.strptime(row[3], '%m/%d/%Y %H:%M:%S').replace(tzinfo=NY)
        if halted.date().isoformat() != session: continue
        require(opening <= halted < closing and halted <= received, 'HALT_OUTSIDE_SESSION_OR_FUTURE')
        require(bool(row[5]) and bool(row[7]), 'HALT_ACTIVE_OR_RESUME_UNCONFIRMED')
        resumed = datetime.strptime(row[5]+' '+row[7], '%m/%d/%Y %H:%M:%S').replace(tzinfo=NY)
        require(halted < resumed < closing and resumed <= received, 'HALT_RESUME_DOMAIN')
        intervals.append(dict(security_id=security_id, ticker=ticker, session=session,
            halted_at=halted.isoformat(), resumed_at=resumed.isoformat(),
            observed_at=received.isoformat(), source_sha256=receipt['raw_sha256']))
    intervals.sort(key=lambda item: item['halted_at'])
    require(len(intervals) <= 100, 'HALT_INTERVAL_BUDGET')
    for previous, following in zip(intervals, intervals[1:]):
        require(aware(previous['resumed_at']) <= aware(following['halted_at']),
                'HALT_DUPLICATE_OR_OVERLAP')
    return intervals
