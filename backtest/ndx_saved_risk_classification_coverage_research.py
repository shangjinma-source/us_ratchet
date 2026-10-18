"""Pure coverage of supplied saved classifications, never source authentication."""
from copy import deepcopy
import re

SCHEMA = 'SAVED_CONDITIONAL_CLASSIFICATION_COVERAGE_V1'
FALSE_FLAGS = ('point_in_time_verified', 'source_bytes_authenticated',
               'formal_classification_verified', 'historical_pool_eligibility_verified',
               'legal_training_input_admitted', 'execution_authorized',
               'promotion_allowed', 'fit_performed', 'risk_reclassified')


def require(value, message):
    if not value:
        raise ValueError(message)


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256', 'json_pointer'}, 'Reference shape')
    require(type(value['path']) is str and value['path'].strip() == value['path'] and value['path'], 'Reference path')
    require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'Reference SHA')
    require(type(value['json_pointer']) is str and (value['json_pointer'] == '' or value['json_pointer'].startswith('/')), 'Reference pointer')
    return deepcopy(value)


def at(ref, pointer):
    return dict(ref, json_pointer=ref['json_pointer'] + pointer)


def resolve(document, pointer):
    current = document
    for token in pointer.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        current = current[int(token)] if type(current) is list else current[token]
    return current


def summarize_saved_classification(*, wiring, training_panel, wiring_reference, training_reference):
    """Copy evidence supplied by caller; do not read files, classify, or calculate returns."""
    wr, tr = reference(wiring_reference), reference(training_reference)
    require(wr['path'] != tr['path'], 'Distinct source documents')
    require(wiring['schema'] == 'BULK_CONDITIONAL_IDENTITY_RISK_WIRING_V1', 'Wiring schema')
    require(training_panel['schema'] == 'DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1', 'Training schema')
    panel = training_panel['panel']
    require(panel['schema'] == 'DATED_CONDITIONAL_TRAINING_PANEL_V1', 'Inner schema')
    for document in (wiring, training_panel, panel):
        for key in ('point_in_time_verified', 'legal_training_input_admitted', 'execution_authorized', 'fit_performed', 'promotion_allowed'):
            require(document.get(key) is False, 'Supplied authority must remain false: ' + key)
    rows = wiring['rows']
    provenance = panel['original_provenance_and_missing']
    require(type(rows) is list and len(rows) == 101 and type(provenance) is list and len(provenance) == 101, 'Complete observed denominator')
    by_ticker = {}
    for index, original in enumerate(provenance):
        ticker = original['ticker']
        require(type(ticker) is str and ticker and ticker not in by_ticker, 'Unique provenance ticker')
        require(type(original['included_in_conditional_panel']) is bool, 'Inclusion bool')
        require(type(original['blocking_reasons']) is list, 'Original blocking reasons')
        by_ticker[ticker] = (index, original)
    selected = panel['fit_payload']['selected_by_security']
    require(type(selected) is dict, 'Selected SID mapping')
    output, seen_tickers, seen_sids, selected_seen = [], set(), set(), set()
    labels, issuer_labels, coordinate_issuers = {}, {}, set()
    labeled_sids, labeled_issuers = set(), set()
    for index, original in enumerate(rows):
        ticker = original['ticker']
        require(type(ticker) is str and ticker and ticker not in seen_tickers and ticker in by_ticker, 'Complete unique ticker mapping')
        seen_tickers.add(ticker)
        coordinate, label = original['coordinate'], original['risk_chain']
        require(label is None or type(label) is str and bool(label.strip()), 'Saved label literal')
        sid = issuer = None
        if coordinate is not None:
            require(type(coordinate) is dict and coordinate['ticker'] == ticker, 'Coordinate ticker')
            sid, issuer = coordinate['security_id'], coordinate['issuer_id']
            require(type(sid) is str and sid and sid not in seen_sids and type(issuer) is str and issuer, 'Distinct SID and issuer')
            seen_sids.add(sid)
            coordinate_issuers.add(issuer)
        known = label is not None and label != 'unclassified'
        if known:
            require(sid is not None, 'Conditional label requires saved coordinate')
            labeled_sids.add(sid)
            labeled_issuers.add(issuer)
            labels[label] = labels.get(label, 0) + 1
            issuer_labels.setdefault(issuer, {}).setdefault(label, []).append(sid)
        p_index, gap = by_ticker[ticker]
        chosen = selected.get(sid) if sid is not None else None
        require(gap['included_in_conditional_panel'] is (chosen is not None), 'Selected and saved inclusion disagree')
        if chosen is not None:
            require(type(chosen) is dict and set(chosen) == {'ticker', 'issuer_id', 'risk_chain'}, 'Selected three-field contract')
            require(chosen == {'ticker': ticker, 'issuer_id': issuer, 'risk_chain': label} and known, 'Selected identity and label mismatch')
            selected_seen.add(sid)
        evidence = {}
        for key, value in original.items():
            if key.endswith('_reference') and type(value) is dict and set(value) == {'json_pointer'}:
                pointer = value['json_pointer']
                require(type(pointer) is str and pointer.startswith('/'), 'Local evidence pointer')
                evidence[key] = {'reference': at(wr, pointer), 'saved_evidence': deepcopy(resolve(wiring, pointer))}
        output.append({'ticker': ticker, 'security_id': sid, 'issuer_id': issuer,
                       'saved_risk_chain': label, 'conditional_label_present': known,
                       'classification_status': 'SAVED_CONDITIONAL_LABEL' if known else 'UNKNOWN_SAVED_LABEL',
                       'formally_verified': False, 'original_wiring_row': deepcopy(original),
                       'wiring_row_reference': at(wr, '/rows/' + str(index)),
                       'local_evidence': evidence, 'training_selected': chosen is not None,
                       'training_selected_mapping': deepcopy(chosen),
                       'training_provenance': deepcopy(gap),
                       'training_provenance_reference': at(tr, '/panel/original_provenance_and_missing/' + str(p_index)),
                       'nonselection_evidence': None if chosen is not None else deepcopy(gap['blocking_reasons']),
                       'nonselection_reason_inferred': False})
    require(selected_seen == set(selected), 'No omitted training SID')
    selected_issuers = {item['issuer_id'] for item in selected.values()}
    for document, values in ((wiring, {'observed_member_count': 101, 'candidate_security_count': len(seen_sids), 'candidate_issuer_count': len(coordinate_issuers)}),
                             (panel, {'observed_security_count': 101, 'security_count': len(selected), 'issuer_count': len(selected_issuers)})):
        for key, expected in values.items():
            require(type(document[key]) is int and document[key] == expected, 'Declared count: ' + key)
    review = [{'issuer_id': issuer, 'saved_labels_and_security_ids': deepcopy(groups), 'status': 'REVIEW_REQUIRED',
               'certified_classification_conflict': False} for issuer, groups in sorted(issuer_labels.items()) if len(groups) > 1]
    return {'schema': SCHEMA, 'status': 'CONDITIONALLY_EVALUATED_SUPPLIED_EVIDENCE',
            'input_references': {'wiring': wr, 'training_panel': tr},
            'counts': {'observed_security_rows': 101, 'coordinate_security_count': len(seen_sids),
                       'coordinate_issuer_count': len(coordinate_issuers), 'conditional_labeled_security_count': len(labeled_sids),
                       'conditional_labeled_issuer_count': len(labeled_issuers), 'unknown_label_rows': 101-len(labeled_sids),
                       'training_selected_security_count': len(selected), 'training_selected_issuer_count': len(selected_issuers),
                       'training_not_selected_rows': 101-len(selected), 'formally_verified_rows': 0},
            'saved_label_counts': labels, 'issuer_label_reviews': review, 'rows': output,
            'saved_wiring_scope': {key: deepcopy(wiring[key]) for key in ('schema', 'calendar', 'candidate_cutoff', 'late_review_count', 'late_annual_tickers', 'historical_denominators_preserved')},
            'saved_training_scope': {key: deepcopy(panel[key]) for key in ('pool_scope', 'original_identity_assumed_window', 'evaluation_prior_fit_overlap_evidence', 'preserved_sidecar_references')},
            'historical_identity_window_extended': False, 'future_independent_oos': False,
            'classification_dates_inferred': False, 'source_authentication_scope': 'CALLER_SUPPLIED_VALUES_ONLY_NO_SOURCE_AUTHENTICATION',
            **{key: False for key in FALSE_FLAGS}}
