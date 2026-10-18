"""Offline WDC rights mapping proposal; deliberately not an event admission."""
from datetime import datetime
from fractions import Fraction
import hashlib
import json


def build_candidate(*, facts_bytes, readback_bytes, official_bytes,
                    facts_path, readback_path, parent_sid, child_sid,
                    previous_close_at, next_open_at):
    facts=json.loads(facts_bytes);readback=json.loads(readback_bytes)
    if facts.get('schema')!='WDC_SNDK_DISTRIBUTION_EVIDENCE_CANDIDATE_V1':raise ValueError('FACT_SCHEMA')
    pins=facts['source_hashes']
    if set(official_bytes)!=set(pins):raise ValueError('EXACT_OFFICIAL_SOURCE_SET_REQUIRED')
    for path,digest in pins.items():
        if hashlib.sha256(official_bytes[path]).hexdigest()!=digest:raise ValueError('OFFICIAL_BYTES_HASH_MISMATCH')
    if readback.get('status')!='ROOT_OFFICIAL_EXCERPT_AND_HASH_READBACK_NOT_EXECUTION_ADMISSION':raise ValueError('READBACK_SCOPE')
    if not parent_sid or not child_sid or parent_sid==child_sid:raise ValueError('DISTINCT_IDENTITIES_REQUIRED')
    if facts['parent_ticker']!='WDC' or facts['child_ticker']!='SNDK' or Fraction(facts['child_ratio'])!=Fraction(1,3) or Fraction(facts['parent_ratio'])!=1:
        raise ValueError('FACT_IDENTITY_OR_RATIO_CHANGED')
    def instant(value):
        t=datetime.fromisoformat(value)
        if t.tzinfo is None or t.utcoffset() is None:raise ValueError('AWARE_CLOCK_REQUIRED')
        return t
    legal=instant(facts['distribution_at']);ny=instant(facts['distribution_at_new_york'])
    close=instant(previous_close_at);opening=instant(next_open_at)
    if legal!=ny or not close<legal<opening:raise ValueError('LEGAL_CLOCK_NOT_BETWEEN_SESSIONS')
    # This proposal is specifically the reviewed Friday-after-close mapping;
    # clocks are supplied calendar evidence, not an automatic holiday resolver.
    if close.isoformat()!='2025-02-21T16:00:00-05:00' or opening.isoformat()!='2025-02-24T09:30:00-05:00':
        raise ValueError('EXPECTED_EXPLICIT_SESSION_BOUNDARIES_REQUIRED')
    if facts['regular_way_child_start']!='2025-02-24':raise ValueError('CHILD_START_CHANGED')
    source_hashes=dict(pins)
    source_hashes[facts_path]=hashlib.sha256(facts_bytes).hexdigest()
    source_hashes[readback_path]=hashlib.sha256(readback_bytes).hexdigest()
    event=dict(event_id='WDC_SNDK_WEEKEND_DISTRIBUTION_20250222_NY',
        effective_date='2025-02-21',date='2025-02-21',timing='AFTER_CLOSE',
        legal_distribution_at=facts['distribution_at'],legal_distribution_at_new_york=facts['distribution_at_new_york'],
        parent_sid=parent_sid,post_parent_sid=parent_sid,child_sid=child_sid,
        child_ratio='1/3',parent_ratio='1',
        eligibility_rule='ACTUAL_HOLDINGS_IMMEDIATELY_BEFORE_EVENT',
        eligibility_scope='REGULAR_WAY_PARENT_ONLY_NO_EX_DISTRIBUTION_NO_DETACHED_RIGHTS_TRADES',
        eligibility_confirmed=None,ordered_steps_confirmed=None,parent_delivered_units_confirmed=None,
        child_delivery_confirmed=False,source_references=list(source_hashes),
        fractional_cash_values={},ordered_steps=['CHILD_ENTITLEMENT_FROM_PRE_ACTION_PARENT','PARENT_RATIO_AND_IDENTITY'])
    return dict(schema='WDC_SNDK_DAILY_EVENT_MAPPING_CANDIDATE_V1',status='PENDING_INDEPENDENT_ADMISSION_NOT_EXECUTABLE',
        source_hashes=source_hashes,event_candidate=event,
        calendar_mapping=dict(classification='INFERENCE_NOT_LITERAL_LEGAL_DATE',
            preceding_close_at=previous_close_at,following_open_at=next_open_at,
            rule='Record Friday regular close first, then create nontradable rights before Monday open. Actual legal distribution remains Saturday NewYork, not Friday16:00.'),
        schema_bridge=dict(prepared_fields=['distribution_events','distribution_fractional_cash_values','metadata','ohlc','source_provenance','source_hashes'],
            source_rule='Every candidate source_references entry must be pinned in prepared.source_hashes; explicit parent/child identities and child Monday valuation source required.',
            blocker='Null confirmation fields intentionally fail existing apply_distribution; no promotion from hash consistency or root readback into execution eligibility.'),
        admission_requirements=[
            'Independent readback of official clauses and complete source linkage; local hashes bind bytes but do not authenticate external facts.',
            'Parent WDC daily OHLC must be proven regular-way with attached child entitlement through distribution; exclude ex-distribution/detached-rights trades. Record-date quantity alone is insufficient.',
            'Verify child ordinary regular-way identity and first-trading date/price channel; exclude Feb13-Feb21 when-issued observations from ordinary execution. Announced expected start is not actual first-trade evidence.',
            'Register the explicit supplied market-calendar session boundaries and weekend mapping as a modeling inference; do not relabel the legal timestamp.',
            'Parent ratio1 means existing parent units remain; independently review this step and identity continuity before setting engine confirmations.',
            'No public start-of-trading statement proves account-specific child delivery. Keep whole child rights nontradable pending separate delivery evidence.',
            'For nonmultiples of3 preserve fractional cash rights; unknown agent sale net proceeds/payment/fees block complete valuation. Never use Monday open as invented fractional settlement.'
        ],economic_calls=0,production_adoption=False,source_authenticity_verified=False,
        identities_externally_certified=False,broker_delivery_verified=False)
