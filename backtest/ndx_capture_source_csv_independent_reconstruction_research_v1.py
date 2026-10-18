"""Independent capture CSV rows; 8MB and 20000 data rows, blanks excluded.

No producer parser imports, IO, row repair or source/clock authentication.
Physical record count is bounded only by source bytes, matching scoped capture.
"""
import csv
from datetime import date
from decimal import Decimal,InvalidOperation
from io import StringIO

SCHEMA='INDEPENDENT_CAPTURE_SOURCE_CSV_READER_V1'
FIELDS=('Date','Open','High','Low','Close','Volume')
MAX_BYTES=8_000_000
MAX_DATA_ROWS=20000
RESOURCE_SEMANTICS='MAX_8000000_SOURCE_BYTES_MAX_20000_DATA_ROWS_BLANK_RECORDS_EXCLUDED_NO_EXTRA_PHYSICAL_LINE_LIMIT'


def require(ok,message):
    if not ok:raise ValueError(message)


def csv_rows(raw,scope):
    """Return complete original rows and pre-scope OHLC diagnostics, no authority."""
    require(type(raw)is bytes and 0<len(raw)<=MAX_BYTES,'Bounded original CSV bytes')
    require(type(scope)is str and date.fromisoformat(scope).isoformat()==scope,'Canonical scope date')
    rows=[];diagnostics=[];previous=''
    try:
        reader=csv.reader(StringIO(raw.decode('utf-8-sig'),newline=''),strict=True)
        require(next(reader)==list(FIELDS),'Exact complete original CSV header')
        for cells in reader:
            if not cells:continue
            require(len(rows)<MAX_DATA_ROWS and len(cells)==len(FIELDS) and
                all(type(value)is str and value and value.strip()==value for value in cells),'Bounded complete canonical CSV record')
            session=cells[0];parsed=date.fromisoformat(session)
            require(parsed.isoformat()==session and parsed.weekday()<5 and session>previous,'Original unique ordered weekday dates')
            previous=session;values={}
            for field,text in zip(FIELDS[1:],cells[1:]):
                require(len(text)<=100,'Numeric text bound')
                value=Decimal(text)
                require(value.is_finite()and len(value.as_tuple().digits)<=50 and -50<=value.as_tuple().exponent<=50 and
                    (value>=0 if field=='Volume'else value>0),'Bounded positive original OHLCV')
                values[field]=value
            issues=[reason for left,right,reason in (('Low','Open','LOW_EXCEEDS_OPEN'),('Low','Close','LOW_EXCEEDS_CLOSE'),
                ('Open','High','HIGH_BELOW_OPEN'),('Close','High','HIGH_BELOW_CLOSE'),('Low','High','LOW_EXCEEDS_HIGH'))if values[left]>values[right]]
            require(session<scope or not issues,'Required-scope OHLC bounds')
            row=dict(zip(FIELDS,cells));rows.append(row)
            if issues:diagnostics.append(dict(original_data_row_index=len(rows)-1,session=session,raw_csv_row=row,
                violations=issues,role='OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE'))
    except (csv.Error,UnicodeError,StopIteration,InvalidOperation)as error:
        raise ValueError('Invalid complete original CSV')from error
    require(rows and any(row['Date']>=scope for row in rows),'Nonempty original required scope')
    return rows,diagnostics
