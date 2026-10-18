"""Explicit server-pinned initial execution month; never infer a new target month.

Calendar adjacency is conditional on the server-reviewed saved schedule; this
validator does not independently certify exchange-calendar completeness.
"""
from datetime import date
import json


def validate_execution_month(declaration, *, decision_date, original_pins, session, files, pins):
    def require(ok, reason):
        if not ok:raise ValueError(reason)
    require(type(declaration)is dict and set(declaration)=={
        'schema','mode','decision_date','target_month','first_active_session','original_source_hashes','source_hashes','calendar_path'},
        'EXECUTION_MONTH_DECLARATION_FIELDS')
    d=declaration
    require(d['schema']=='V2_INITIAL_EXECUTION_MONTH_V1' and d['decision_date']==decision_date,
        'EXECUTION_MONTH_DECISION_MISMATCH')
    first=date.fromisoformat(d['first_active_session']).isoformat()
    require(first==d['first_active_session'] and first[:7]==d['target_month'] and decision_date<=first,
        'EXECUTION_MONTH_ACTIVE_DATE_INVALID')
    require(type(d['original_source_hashes'])is dict and bool(original_pins)
        and d['original_source_hashes']==original_pins,'EXECUTION_MONTH_INPUT_BINDING_REQUIRED')
    require(type(d['source_hashes'])is dict,'EXECUTION_MONTH_SOURCE_FIELDS')
    require(all(pins.get(p)==h and p in files for p,h in d['source_hashes'].items()),'EXECUTION_MONTH_SOURCE_MISMATCH')
    if d['mode']=='INITIAL_CURRENT_MONTH_BOOTSTRAP':
        require(decision_date[:7]==d['target_month'] and d['calendar_path'] is None,'INVALID_BOOTSTRAP_MONTH')
    elif d['mode']=='MONTH_END_NEXT_MONTH':
        require(d['calendar_path'] in d['source_hashes'],'EXECUTION_MONTH_CALENDAR_REQUIRED')
        calendar=json.loads(files[d['calendar_path']])
        require(calendar.get('schema')=='SCHEDULED_REGULAR_SESSIONS_V1','EXECUTION_MONTH_CALENDAR_SCHEMA')
        days=calendar['calendar']
        require(days==sorted(set(days)) and all(date.fromisoformat(x).isoformat()==x for x in days),
            'EXECUTION_MONTH_CALENDAR_INVALID')
        index=days.index(decision_date)
        origin=date.fromisoformat(decision_date);target=date.fromisoformat(first)
        require(target.year*12+target.month==origin.year*12+origin.month+1,'NEXT_CALENDAR_MONTH_REQUIRED')
        require(index+1<len(days) and days[index+1]==first and decision_date[:7]<d['target_month']
            and not any(x[:7]==d['target_month'] for x in days[:index+1]),'ACTIVE_NOT_ADJACENT_NEXT_MONTH')
        require(all(d['source_hashes'].get(p)==h for p,h in calendar['source_hashes'].items()),
            'EXECUTION_MONTH_CALENDAR_EVIDENCE_REQUIRED')
    else:raise ValueError('UNSUPPORTED_EXECUTION_MONTH_POLICY')
    require(session[:7]<=d['target_month'],'RESELECT_REQUIRED')
    require(session[:7]==d['target_month'] and session>=first,'EXECUTION_MONTH_NOT_ACTIVE')
    return d['target_month']
