"""Pure membership evidence horizon gate; authenticates no sources or historical facts.

External attestations are inputs, not certificates created by this module.  A saved
case end is a scope boundary, never evidence that an unresolved removal occurred.
This module is intentionally not connected to any existing panel or live consumer.
"""
from copy import deepcopy
from datetime import date, timedelta
import re

SCHEMA = 'NDX_MEMBERSHIP_EVIDENCE_HORIZON_RESEARCH_V1'
CHECKS = {'identity', 'liquidity', 'risk'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def iso(value, label):
    require(type(value) is str, label + ' must be an ISO date string')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(label + ' must be an ISO date') from error
    require(parsed.isoformat() == value, label + ' must be canonical YYYY-MM-DD')
    return value


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Exact external source reference required')
    require(type(value['path']) is str and value['path'].strip() == value['path'] and value['path'], 'Nonblank source path required')
    require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None, 'Canonical source SHA256 required')


def attestation(value, fields, label):
    if value is None:
        return
    require(type(value) is dict and set(value) == set(fields) | {'source_reference', 'available_date', 'authenticated'}, label + ' exact schema required')
    reference(value['source_reference'])
    iso(value['available_date'], label + '.available_date')
    require(type(value['authenticated']) is bool, label + '.authenticated must be bool')


def evaluate_membership_evidence_horizon(*, security_id, issuer_id,
        decision_cutoff, decision_session, required_start, required_end,
        baseline_evidence, event_coverage_evidence, membership_evidence,
        unresolved_cases, eligibility_checks):
    """Evaluate supplied attestations without reading bytes, inferring events or fitting.

    required_start/end describes the membership evidence horizon, not a return-price
    calendar.  availability is compared with the decision data cutoff; membership
    effectiveness is compared with the decision session.  None means not supplied.
    eligibility_checks contains separately adjudicated identity/liquidity/risk
    bool-or-None results; none of these can establish index membership.
    """
    for label, value in (('security_id', security_id), ('issuer_id', issuer_id)):
        require(type(value) is str and value.strip() == value and value, label + ' must be nonblank')
    for label, value in (('decision_cutoff', decision_cutoff), ('decision_session', decision_session), ('required_start', required_start), ('required_end', required_end)):
        iso(value, label)
    require(decision_cutoff <= decision_session and required_start <= decision_session <= required_end, 'Invalid decision or required horizon ordering')
    require(type(eligibility_checks) is dict and set(eligibility_checks) == CHECKS and all(v is None or type(v) is bool for v in eligibility_checks.values()), 'Exact independent bool-or-None eligibility checks required')
    attestation(baseline_evidence, {'index_symbol', 'as_of', 'complete'}, 'baseline')
    attestation(event_coverage_evidence, {'index_symbol', 'start', 'end', 'complete', 'covered_intervals'}, 'event coverage')
    attestation(membership_evidence, {'index_symbol', 'security_id', 'issuer_id', 'status', 'effective_start', 'effective_end'}, 'membership')
    require(type(unresolved_cases) is list, 'Explicit unresolved case inventory required')
    # Cross-input path/hash conflicts are invalid even if the evidence later fails.
    source_hashes = {}
    def add_source(ref):
        reference(ref)
        require(ref['path'] not in source_hashes or source_hashes[ref['path']] == ref['sha256'], 'Conflicting supplied source SHA')
        source_hashes[ref['path']] = ref['sha256']
    for evidence in (baseline_evidence, event_coverage_evidence, membership_evidence):
        if evidence is not None:
            add_source(evidence['source_reference'])
    reasons = []
    baseline_ok = False
    coverage_ok = False
    out_of_horizon = False
    if baseline_evidence is None:
        reasons.append('BASELINE_NOT_SUPPLIED')
    else:
        b = baseline_evidence
        iso(b['as_of'], 'baseline.as_of')
        require(b['index_symbol'] == 'NDX' and type(b['complete']) is bool, 'Explicit NDX complete-baseline claim required')
        baseline_ok = b['authenticated'] and b['complete'] and b['available_date'] <= decision_cutoff and b['as_of'] <= required_start
        if not baseline_ok:
            reasons.append('BASELINE_NOT_AUTHENTICATED_COMPLETE_AVAILABLE_AND_PRIOR')
    if event_coverage_evidence is None:
        reasons.append('EVENT_COVERAGE_NOT_SUPPLIED')
    else:
        e = event_coverage_evidence
        iso(e['start'], 'coverage.start'); iso(e['end'], 'coverage.end')
        require(e['index_symbol'] == 'NDX' and type(e['complete']) is bool and e['start'] <= e['end'], 'Explicit ordered NDX event coverage required')
        intervals = e['covered_intervals']
        require(type(intervals) is list, 'Explicit covered intervals required')
        last = None
        gap = not intervals
        for interval in intervals:
            require(type(interval) is dict and set(interval) == {'start', 'end'}, 'Exact covered interval required')
            left = iso(interval['start'], 'interval.start'); right = iso(interval['end'], 'interval.end')
            require(e['start'] <= left <= right <= e['end'] and (last is None or last < left), 'Intervals must be ordered, disjoint and within declared coverage')
            if last is None:
                gap = gap or left != e['start']
            else:
                gap = gap or date.fromisoformat(left) - date.fromisoformat(last) != timedelta(days=1)
            last = right
        gap = gap or last != e['end']
        if gap:
            reasons.append('EVENT_COVERAGE_HAS_UNCOVERED_INTERVAL')
        # The chain must start at the baseline, not merely at the requested date.
        chain_start = baseline_evidence['as_of'] if baseline_evidence is not None else required_start
        out_of_horizon = e['start'] > chain_start or e['end'] < required_end
        coverage_ok = e['authenticated'] and e['complete'] and e['available_date'] <= decision_cutoff and not out_of_horizon and not gap
        if out_of_horizon:
            reasons.append('OUTSIDE_CERTIFIED_EVENT_HORIZON')
        if not e['authenticated'] or not e['complete'] or e['available_date'] > decision_cutoff:
            reasons.append('EVENT_DENOMINATOR_NOT_AUTHENTICATED_COMPLETE_AND_AVAILABLE')
    active = []
    outside_saved = []
    blocking_cases = []
    seen = set()
    for wrapped in unresolved_cases:
        require(type(wrapped) is dict and set(wrapped) == {'original_case', 'source_reference'}, 'Exact saved case wrapper required')
        add_source(wrapped['source_reference'])
        case = wrapped['original_case']
        require(type(case) is dict, 'Original case mapping required')
        cid = case.get('case_id')
        require(type(cid) is str and cid.strip() == cid and cid and cid not in seen, 'Unique nonblank case ID required'); seen.add(cid)
        start = iso(case.get('blocked_selection_start'), 'case.start')
        end = iso(case.get('blocked_selection_end'), 'case.end')
        require(start <= end and case.get('promotion_allowed') is False, 'Saved case bounds or permissions invalid')
        scope = case.get('scope_lock')
        require(scope in {'exclude_effective_day_until_source_available', 'exact_addition_supported_removal_unresolved', 'proxy_extra_is_not_membership_evidence'}, 'Unknown unresolved case policy')
        intersects = start <= required_end and end >= required_start
        if intersects:
            active.append(cid); blocking_cases.append(cid)
        if scope == 'exact_addition_supported_removal_unresolved':
            require(case.get('exact_addition_supported') is True and case.get('exact_removal_date_supported') is False, 'Unresolved removal must retain original evidence limits')
            if required_end > end and required_end >= start:
                outside_saved.append(cid)
                if cid not in blocking_cases:
                    blocking_cases.append(cid)
    if active:
        reasons.append('KNOWN_CASE_INTERSECTS_REQUIRED_MEMBERSHIP_HORIZON')
    if outside_saved:
        reasons.append('UNRESOLVED_REMOVAL_OUTSIDE_SAVED_SCOPE')
    membership_ok = False
    claimed = None
    if membership_evidence is None:
        reasons.append('MEMBERSHIP_ASSERTION_NOT_SUPPLIED')
    else:
        m = membership_evidence
        iso(m['effective_start'], 'membership.effective_start'); iso(m['effective_end'], 'membership.effective_end')
        require(m['index_symbol'] == 'NDX' and m['security_id'] == security_id and m['issuer_id'] == issuer_id, 'Identity-bound NDX membership assertion required')
        require(m['status'] in {'MEMBER', 'NONMEMBER'} and m['effective_start'] <= m['effective_end'], 'Explicit member or nonmember evidence interval required')
        claimed = m['status']
        membership_ok = m['authenticated'] and m['available_date'] <= decision_cutoff and m['effective_start'] <= decision_session <= m['effective_end']
        if not membership_ok:
            reasons.append('MEMBERSHIP_ASSERTION_NOT_AUTHENTICATED_AVAILABLE_OR_EFFECTIVE')
    complete = baseline_ok and coverage_ok and membership_ok and not blocking_cases
    membership_status = ('MEMBER_UNDER_SUPPLIED_ATTESTATIONS' if claimed == 'MEMBER' else 'NONMEMBER_UNDER_SUPPLIED_ATTESTATIONS') if complete else 'UNKNOWN'
    if membership_status == 'NONMEMBER_UNDER_SUPPLIED_ATTESTATIONS':
        eligible = False; eligibility_status = 'INELIGIBLE_NONMEMBER'
    elif membership_status == 'UNKNOWN':
        eligible = None; eligibility_status = 'UNKNOWN_MEMBERSHIP'
    elif any(v is False for v in eligibility_checks.values()):
        eligible = False; eligibility_status = 'INELIGIBLE_OTHER_REQUIREMENT'
    elif any(v is None for v in eligibility_checks.values()):
        eligible = None; eligibility_status = 'UNKNOWN_OTHER_REQUIREMENT'
    else:
        eligible = True; eligibility_status = 'ELIGIBLE_UNDER_SUPPLIED_ATTESTATIONS'
    return dict(schema=SCHEMA, scope='PURE_SUPPLIED_EVIDENCE_HORIZON_RESEARCH_ONLY',
        security_id=security_id, issuer_id=issuer_id, decision_cutoff=decision_cutoff, decision_session=decision_session,
        required_start=required_start, required_end=required_end, membership_status=membership_status,
        evidence_status='COMPLETE_UNDER_SUPPLIED_ATTESTATIONS' if complete else 'INCOMPLETE_OR_OUTSIDE_HORIZON',
        eligibility_status=eligibility_status, eligible=eligible, formal_eligibility_authorized=False,
        baseline_usable=baseline_ok, event_coverage_usable=coverage_ok, out_of_certified_horizon=out_of_horizon,
        authentication_claims_origin='SUPPLIED_EXTERNAL_ASSERTIONS_NOT_AUTHENTICATED_BY_THIS_MODULE',
        supplied_authentication_claims={name: (value['authenticated'] if value is not None else None) for name, value in (('baseline', baseline_evidence), ('events', event_coverage_evidence), ('membership', membership_evidence))},
        known_active_gap_ids=active, unresolved_removal_outside_saved_scope_ids=outside_saved,
        blocking_case_ids=blocking_cases, reasons=reasons, eligibility_checks=deepcopy(eligibility_checks),
        supplied_evidence=deepcopy(dict(baseline=baseline_evidence, event_coverage=event_coverage_evidence, membership=membership_evidence)),
        original_unresolved_cases=deepcopy(unresolved_cases), supplied_source_hashes=source_hashes,
        saved_case_intervals_modified=False, membership_interval_extended_from_gap=False,
        source_bytes_read=False, source_authenticity_reverified=False, event_denominator_independently_recomputed=False,
        point_in_time_certification_created=False, full_pool_completeness_certified=False,
        fit_performed=False, http_performed=False, promotion_allowed=False, execution_authorized=False)
