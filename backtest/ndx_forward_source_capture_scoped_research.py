"""Frontier-bound CSV scope adapter; preserve full bytes and old OHLC diagnostics.

The frozen capture kernel consumes only explicitly derived in-scope CSV bytes.
The scope comes mechanically from the supplied sealed frontier, never prices.
Source authentication and actual clock acquisition remain the caller's job.
"""
import base64
import csv
from datetime import date
from decimal import Decimal
import hashlib
import io
from backtest import ndx_forward_source_capture_research as capture

FROZEN_CAPTURE_SHA256='30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'
FIELDS=('Date','Open','High','Low','Close','Volume')
MAX_BYTES=8_000_000

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def scoped_csv(raw,scope_start):
    require(type(raw) is bytes and 0<len(raw)<=MAX_BYTES,'Bounded original CSV bytes required')
    text=raw.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(text,newline=''))
    require(reader.fieldnames==list(FIELDS),'Exact original OHLCV header required')
    previous='';all_rows=[];included=[];excluded=[];diagnostics=[]
    for index,row in enumerate(reader):
        require(index<20000,'Original row bound exceeded')
        require(set(row)==set(FIELDS) and all(type(v) is str and v and v.strip()==v for v in row.values()),'Complete original row required')
        day=row['Date'];parsed=date.fromisoformat(day)
        require(parsed.isoformat()==day and parsed.weekday()<5 and day>previous,'Canonical unique ordered original weekday dates required')
        previous=day;values={}
        for key in FIELDS[1:]:
            require(len(row[key])<=100,'Original numeric text bound')
            value=Decimal(row[key])
            require(value.is_finite() and len(value.as_tuple().digits)<=50 and -50<=value.as_tuple().exponent<=50,'Finite bounded original numeric required')
            require(value>=0 if key=='Volume' else value>0,'Invalid original price or volume')
            values[key]=value
        violations=[]
        if values['Low']>values['Open']:violations.append('LOW_EXCEEDS_OPEN')
        if values['Low']>values['Close']:violations.append('LOW_EXCEEDS_CLOSE')
        if values['High']<values['Open']:violations.append('HIGH_BELOW_OPEN')
        if values['High']<values['Close']:violations.append('HIGH_BELOW_CLOSE')
        if values['Low']>values['High']:violations.append('LOW_EXCEEDS_HIGH')
        in_scope=day>=scope_start
        require(not in_scope or not violations,'Required-scope OHLC bounds violated')
        all_rows.append(dict(original_data_row_index=index,session=day,raw_csv_row=dict(row),included_in_scoped_csv=in_scope))
        (included if in_scope else excluded).append(index)
        if violations:diagnostics.append(dict(original_data_row_index=index,session=day,raw_csv_row=dict(row),violations=violations,role='OUTSIDE_FRONTIER_SCOPE_DIAGNOSTIC_NOT_EXECUTION_PRICE'))
    require(all_rows and included,'Nonempty original and required scope rows required')
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator='\n');writer.writeheader()
    writer.writerows(all_rows[index]['raw_csv_row'] for index in included)
    derived=stream.getvalue().encode('utf-8')
    return derived,dict(scope_start=scope_start,original_sha256=sha(raw),original_byte_count=len(raw),
        original_csv_bytes_base64=base64.b64encode(raw).decode('ascii'),original_row_count=len(all_rows),
        original_rows=all_rows,included_original_row_indexes=included,excluded_original_row_indexes=excluded,
        excluded_before_scope_ohlc_diagnostics=diagnostics,scoped_sha256=sha(derived),scoped_byte_count=len(derived),
        scoped_csv_utf8=derived.decode('utf-8'),scope_selection='SESSION_GREATER_OR_EQUAL_SEALED_FRONTIER_FIRST_SESSION_NOT_PRICE_SELECTED')

def plan_scoped_forward_source_capture(*,frontier,source_csv_bytes,baseline_csv_bytes,tzif_bytes,
                                      capture_started_at_utc,observed_at_utc):
    require(type(frontier) is dict and frontier.get('schema')=='OBSERVATION_GAP_FRONTIER_RESEARCH_V1','Frontier schema')
    known=frontier.get('known_accounted_rows');require(type(known) is list and known,'Complete sealed frontier required')
    scope_start=known[0]['session'];require(type(scope_start) is str and date.fromisoformat(scope_start).isoformat()==scope_start,'Frontier first session required')
    derived={};evidence={}
    for role,mapping in [('source',source_csv_bytes),('baseline',baseline_csv_bytes)]:
        require(type(mapping) is dict and set(mapping)=={'QQQ','SPY'},'Exact original source pair required')
        derived[role]={};evidence[role]={}
        for ticker in ('QQQ','SPY'):
            derived[role][ticker],evidence[role][ticker]=scoped_csv(mapping[ticker],scope_start)
    planned=capture.plan_forward_source_capture(frontier=frontier,source_csv_bytes=derived['source'],
        baseline_csv_bytes=derived['baseline'],tzif_bytes=tzif_bytes,capture_started_at_utc=capture_started_at_utc,observed_at_utc=observed_at_utc)
    return dict(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1',scope_start=scope_start,capture_plan=planned,
        original_source_sha256={t:sha(v) for t,v in source_csv_bytes.items()},original_baseline_sha256={t:sha(v) for t,v in baseline_csv_bytes.items()},
        scoped_source_sha256={t:sha(v) for t,v in derived['source'].items()},scoped_baseline_sha256={t:sha(v) for t,v in derived['baseline'].items()},
        csv_scope_evidence=evidence,frozen_capture_source_sha256=FROZEN_CAPTURE_SHA256,
        frozen_capture_consumed_full_original_csv=False,full_original_bytes_preserved=True,
        out_of_scope_ohlc_anomalies_repaired=False,scope_chosen_from_prices=False,
        source_bytes_authenticated_by_this_module=False,old_failed_namespace_modified=False,
        original_calendar_reverified=False,source_price_execution_verified=False,
        historical_first_observation_claimed=False,fresh_observation=False,decision_eligible=False,
        candidate_seal_allowed=False,cohort_registration_allowed=False,canonical_calendar_append_allowed=False,
        point_in_time_verified=False,promotion_allowed=False,live_mutation_allowed=False,oos_recovery_completed=False)

