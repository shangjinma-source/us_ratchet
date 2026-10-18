"""Pinned root-accepted WDC model; confirmations describe assumptions, not certification."""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo
import gzip
import hashlib
import json

SCOPE='research_contracts/annual_wdc_conditional_model_scope_20261016_v1.json'
SCOPE_SHA256='1832a111827fe2a202e4c10bb42f15218b215f5eea8c927b24afa2e8decc4642'
BASE='tmp/wdc_sndk_distribution_evidence_20261016_v1/'
PARENT='security:0000106040:958102105'
CHILD='security:0002023554:80004C200'


def decode_daily_channel(raw, symbol):
    payload=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)['chart']['result'][0]
    meta=payload['meta']
    if (meta.get('symbol')!=symbol or meta.get('currency')!='USD' or meta.get('instrumentType')!='EQUITY'
        or meta.get('exchangeTimezoneName')!='America/New_York'
        or meta.get('exchangeName') not in ('NMS','NGM','NCM','NYQ','ASE','PCX')):
        raise ValueError('PRICE_CHANNEL_IDENTITY_OR_EXCHANGE_TIMEZONE')
    zone=ZoneInfo(meta['exchangeTimezoneName'])
    quotes=payload['indicators']['quote'][0]
    rows=[]
    for index,stamp in enumerate(payload['timestamp']):
        if type(stamp) is not int:raise ValueError('INVALID_TIMESTAMP')
        day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(zone).date().isoformat()
        rows.append((day,{field:quotes[field][index] for field in ('open','high','low','close')}))
    return rows


def assemble_conditional_wdc(*,root):
    root=Path(root).resolve();pins={};contents={}
    def verify(path,digest):
        canonical=path.replace('\\','/');absolute=(root/canonical).resolve()
        if not absolute.is_relative_to(root):raise ValueError('SOURCE_OUTSIDE_ROOT')
        if canonical in pins:
            if pins[canonical]!=digest:raise ValueError('CONFLICTING_PIN')
            return
        raw=absolute.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('SOURCE_HASH_MISMATCH:'+canonical)
        pins[canonical]=digest;contents[canonical]=raw
    verify(SCOPE,SCOPE_SHA256)
    scope=json.loads(contents[SCOPE])
    if scope['status']!='MODEL_SCOPE_ACCEPTED_NOT_PRODUCTION_OR_FULL_ANNUAL_ADMISSION':raise ValueError('WRONG_SCOPE')
    for path,digest in scope['source_hashes'].items():verify(path,digest)
    # Scope-approved component manifests bind their direct inputs. Embedded
    # historical review files are documentary evidence, not executable recursive
    # manifests for unrelated old portfolios or mutable price caches.
    for manifest in ('daily_event_mapping_candidate.json','channel_conditional_admission_proposal.json'):
        for path,digest in json.loads(contents[BASE+manifest])['source_hashes'].items():verify(path,digest)
    candidate=json.loads(contents[BASE+'daily_event_mapping_candidate.json'])
    event=deepcopy(candidate['event_candidate'])
    if (event['parent_sid'],event['post_parent_sid'],event['child_sid'],event['child_ratio'],event['parent_ratio'])!=(PARENT,PARENT,CHILD,'1/3','1'):
        raise ValueError('IDENTITY_OR_RATIO_MISMATCH')
    if (event['effective_date'],event['timing'],event['legal_distribution_at_new_york'])!=('2025-02-21','AFTER_CLOSE','2025-02-22T02:59:00-05:00'):
        raise ValueError('EVENT_CLOCK_MISMATCH')
    channels={};excluded=[];source_provenance={}
    for symbol,sid in [('WDC',PARENT),('SNDK',CHILD)]:
        path=f'data/cache/research/current_raw_capture_20261014_v1/{symbol}.response.bin'
        bars={}
        for day,quote in decode_daily_channel(contents[path],symbol):
            if symbol=='SNDK' and day<'2025-02-24':
                excluded.append(day);continue
            if day in bars:raise ValueError('DUPLICATE_SESSION')
            factor=Fraction(1323,1000) if symbol=='WDC' and day<'2025-02-24' else Fraction(1)
            values={}
            for field in ('open','high','low','close'):
                value=quote[field]
                if value is None or isinstance(value,bool):raise ValueError('INVALID_PRICE')
                amount=Fraction(str(value))*factor
                if amount<=0:raise ValueError('INVALID_PRICE')
                values[field]=amount
            if not values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']:raise ValueError('INVALID_OHLC')
            bars[day]={key:str(value) for key,value in values.items()}
        channels[sid]=bars
        source_provenance[sid]=dict(whole_source=path,price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',
            conditional_model=True,scope_reference=SCOPE,external_price_certified=False,
            ordinary_from='2025-02-24' if symbol=='SNDK' else None,
            price_coordinate_factors=[dict(before='2025-02-24',factor='1323/1000')] if symbol=='WDC' else [])
    if excluded!=['2025-02-13','2025-02-14','2025-02-18','2025-02-19','2025-02-20','2025-02-21']:raise ValueError('UNEXPECTED_WHEN_ISSUED_ROWS')
    event.update(eligibility_confirmed=True,ordered_steps_confirmed=True,parent_delivered_units_confirmed=True,
        conditional_model=True,confirmation_authority=SCOPE,
        confirmation_scope='ROOT_ACCEPTED_REGULAR_WAY_ACCOUNTING_ASSUMPTIONS_NOT_EXTERNAL_PRICE_OR_DELIVERY_CERTIFICATION',
        child_delivery_confirmed=False,source_references=list(pins))
    return dict(schema='WDC_SNDK_CONDITIONAL_ASSEMBLY_V1',status='CONDITIONAL_MODEL_COMPONENT_NOT_FULL_DATASET_ADMISSION',
        conditional_model=True,scope_reference=SCOPE,source_hashes=pins,distribution_events=[event],
        distribution_fractional_cash_values={},ohlc=channels,source_provenance=source_provenance,
        excluded_when_issued_sessions=excluded,true_parent_split_events=[],
        child_whole_rights_tradable=False,external_price_certified=False,broker_delivery_verified=False,
        limitations=['Whole child rights are valued only, never delivered or sold.',
            'Unknown fractional cash amounts still block total equity; no Monday-open fabrication.',
            'Conditional restored provider prices; no PIT or absolute nominal-price certification.',
            'Apply only to regular-way parent model; no detached rights/ex-distribution trades.'])
