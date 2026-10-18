"""Append one supplied, independently read-back observation; no IO or authority."""
from copy import deepcopy
from datetime import date
import hashlib
import json

SCHEMA = 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V2'
ENTRY_SCHEMA = 'COMPACT_OBSERVATION_REFERENCE_ENTRY_V1'
GENESIS_READBACK_SCHEMA = 'GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V1'  # Proposed interface, not an existing receipt.
OBSERVATION_READBACK_V2 = 'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2'  # Future variable-prefix reader interface.
HISTORY_READBACK_SCHEMA = 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2'
POLICY = 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
FLAGS = dict.fromkeys(('source_authenticity_verified', 'filesystem_attempt_inventory_authenticated',
    'clock_authenticity_verified', 'candidate_seal_allowed', 'cohort_registration_allowed',
    'point_in_time_verified', 'promotion_allowed', 'live_mutation_allowed',
    'future_independent_oos', 'production_generator_authorized', 'seal_event_created',
    'partial_recovery_performed', 'old_calendar_mutated'), False)

def require(ok, message):
    if not ok: raise ValueError(message)

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def exact(a, b, message):
    require(encoded(a) == encoded(b), message)

def ref(value, sources):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Exact reference')
    p, h = value['path'], value['sha256']
    require(type(p) is str and bool(p) and p == p.strip(), 'Reference path')
    require(type(h) is str and len(h) == 64 and all(c in '0123456789abcdef' for c in h), 'Reference SHA')
    require(p not in sources or sources[p] == h, 'Source conflict')
    sources[p] = h

def rows_check(rows, sources):
    require(type(rows) is list and 0 < len(rows) < 20000, 'Complete bounded typed history')
    prior = ''; pointers = set(); months = {}
    for i, row in enumerate(rows):
        require(type(row) is dict and set(row) == {'sequence','session','kind','evidence_reference','seal_status'}, 'Typed row')
        s = row['session']; require(type(s) is str and date.fromisoformat(s).isoformat() == s and date.fromisoformat(s).weekday() < 5 and s > prior, 'Ordered weekday dates')
        require(type(row['sequence']) is int and row['sequence'] == i+1, 'Exact sequence')
        require(row['kind'] in ('SEALED_PARENT_OBSERVED_SESSION','PROSPECTIVE_OBSERVED_SESSION','MISSED_OBSERVATION'), 'Typed kind')
        require(row['seal_status'] in ('NOT_ATTEMPTED','UNKNOWN','FAILED','SEALED'), 'Seal state')
        require(row['kind'] != 'MISSED_OBSERVATION' or row['seal_status'] == 'NOT_ATTEMPTED', 'Gap seal')
        r = row['evidence_reference']; require(type(r) is dict and set(r) == {'path','sha256','json_pointer'}, 'Typed pointer')
        ref({k:r[k] for k in ('path','sha256')}, sources)
        pointer = r['json_pointer']; require(type(pointer) is str and pointer.startswith('/') and len(pointer)>1, 'Evidence pointer')
        key = (r['path'],r['sha256'],pointer); require(key not in pointers, 'Duplicate pointer'); pointers.add(key)
        if row['kind'] != 'MISSED_OBSERVATION': months.setdefault(s[:7], s)
        prior = s
    return months

def parent_evidence(envelope, sources, *, genesis):
    for k in ('reference','publication_reference','readback_reference','reader_reference'): ref(envelope[k], sources)
    doc, pub, audit = (envelope[k] for k in ('document','publication','readback'))
    key = 'policy_reference' if genesis else 'history_reference'
    require(pub['schema'] == ('GAP_MONTHLY_POLICY_PUBLICATION_V1' if genesis else 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2'), 'Parent publication schema')
    require(pub['status'] == ('PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL' if genesis else 'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL'), 'Parent publication status')
    require(audit['schema'] == (GENESIS_READBACK_SCHEMA if genesis else HISTORY_READBACK_SCHEMA) and audit['status'] == 'PASS', 'Versioned parent readback contract')
    for obj in (pub,audit): exact(obj[key],envelope['reference'],'Parent document anchor')
    exact(audit['publication_reference'],envelope['publication_reference'],'Parent receipt anchor')
    exact(pub['source_hashes'],doc['source_hashes'],'Parent publication source claims')
    require(audit['reader_sha256'] == envelope['reader_reference']['sha256'],'Parent reader source')
    for k in ('reference','publication_reference','reader_reference'):
        r=envelope[k]; require(audit['source_hashes'].get(r['path']) == r['sha256'],'Parent audit fixed input')
    for claims in (doc['source_hashes'],audit['source_hashes']):
        require(type(claims) is dict,'Parent source claims')
        for path,h in claims.items(): ref(dict(path=path,sha256=h),sources)
    for obj in (pub,audit):
        for f in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'): require(obj[f] is False,'Parent no authority')

def append_observation_history(*, genesis, previous_history, observation):
    """Envelopes are caller-bound evidence, never authentication by this pure function.

    genesis: document, publication, readback, reader_reference, reference,
             publication_reference, readback_reference,
             baseline_references {QQQ,SPY}.
    previous_history: None or document, publication, readback, reader_reference,
                      reference, publication_reference, readback_reference.
    Genesis adapter and V2 readback schemas are proposed version interfaces; no
    such actual PASS receipt is created by this module. Existing V1 observation
    readback is first-only and cannot certify a later variable-length prefix.
    observation: payload, receipt, audit, payload_reference, receipt_reference,
                 audit_reference, reader_reference.
    """
    sources = {}
    parent_evidence(genesis, sources, genesis=True)
    g = genesis['document']
    require(g['schema'] == 'SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1' and g['policy_id'] == POLICY, 'Frozen first-actual policy')
    require(type(g['new_observation_count']) is int and g['new_observation_count'] == 0, 'Genesis no new observation')
    exact(g['projection_inputs']['new_prospective_observations'], [], 'Genesis new rows')
    original = g['projection_inputs']['known_rows']; rows_check(original, sources)
    require(all(r['kind'] != 'PROSPECTIVE_OBSERVED_SESSION' for r in original), 'Genesis only original prefix')
    for f in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'): require(g[f] is False, 'Genesis authority')
    baseline = genesis['baseline_references']; require(type(baseline) is dict and set(baseline) == {'QQQ','SPY'}, 'Both genesis baselines')
    exact(baseline, genesis['readback']['baseline_references'], 'Genesis audited QQQ/SPY roles')
    for r in baseline.values():
        ref(r, sources)
        require(genesis['readback']['source_hashes'].get(r['path']) == r['sha256'], 'Genesis audited baseline bytes')
    parent_ref, parent_audit = genesis['reference'], genesis['readback_reference']
    known = deepcopy(original); entries = []; inventory = []
    if previous_history is not None:
        parent_evidence(previous_history, sources, genesis=False)
        old = previous_history['document']; require(old['schema'] == SCHEMA and old['policy_id'] == POLICY, 'V2 history parent')
        for f in FLAGS: require(old[f] is False, 'No parent authority upgrade')
        exact(old['genesis_preserved'], genesis, 'Same complete genesis')
        known = deepcopy(old['known_typed_rows']); old_months = rows_check(known, sources)
        exact(old['first_actual_observed_session_by_month'], old_months, 'Recomputed parent month coordinates')
        exact(old['last_accounted_session'], known[-1]['session'], 'Recomputed parent last session')
        exact(known[:len(original)], original, 'Original prefix preserved')
        entries = deepcopy(old['observations']); inventory = deepcopy(old['parent_attempt_inventory'])
        require(type(entries) is list and type(inventory) is list and len(entries) == len(inventory) == len(known)-len(original), 'Complete observation inventory')
        require(type(old['observation_count']) is int and old['observation_count'] == len(entries), 'Exact parent count')
        for j, (entry, attempt) in enumerate(zip(entries, inventory)):
            require(entry['schema'] == ENTRY_SCHEMA and entry['original_payload_embedded'] is False, 'Compact entry version')
            require(set(entry) == COMPACT_KEYS, 'Exact compact entry fields, no raw payload')
            p = entry; r = known[len(original)+j]
            require(r['kind'] == 'PROSPECTIVE_OBSERVED_SESSION' and r['session'] == p['session'] and type(p['sequence']) is int and p['sequence'] == r['sequence'], 'No omitted observation')
            require(p['observation_id'] == hashlib.sha256(encoded(p['observation_identity'])).hexdigest(), 'Compact observation identity')
            require(set(entry['original_source_hash_claims']) == {'payload','receipt','audit'}, 'Complete source claim roles')
            exact(r['evidence_reference'],dict(entry['payload_reference'],json_pointer='/observation_identity'), 'Original payload pointer')
            exact(attempt, attempt_for(entry), 'Complete previous receipt inventory')
            for k in ('payload_reference','receipt_reference','audit_reference','reader_reference'): ref(entry[k], sources)
            for claims in entry['original_source_hash_claims'].values():
                for path,h in claims.items(): ref(dict(path=path,sha256=h),sources)
        baseline = old['baseline_references']
        require(type(baseline) is dict and set(baseline) == {'QQQ','SPY'}, 'Parent baselines')
        if entries:
            exact(baseline, entries[-1]['captured_baseline_references'], 'Parent baseline is last original capture')
        parent_ref, parent_audit = previous_history['reference'], previous_history['readback_reference']
    for r in baseline.values(): ref(r, sources)
    for k in ('payload_reference','receipt_reference','audit_reference','reader_reference'): ref(observation[k], sources)
    p, receipt, audit = (observation[k] for k in ('payload','receipt','audit'))
    exact(p['source_hashes'], receipt['source_hashes'], 'Payload and receipt identical source claims')
    for claims in (p['source_hashes'], receipt['source_hashes'], audit['source_hashes']):
        require(type(claims) is dict, 'Observation source claims')
        for path, h in claims.items(): ref(dict(path=path,sha256=h), sources)
    for path, h in p['source_hashes'].items(): require(audit['source_hashes'].get(path) == h, 'Audit includes every payload source')
    # Independent reader authenticates these bytes; this pure only checks linkage.
    for t in ('QQQ','SPY'):
        for role in ('sources','baseline_sources'):
            r = p['full_original_sources_preserved'][t][role]['reference']; ref(r,sources)
            require(p['source_hashes'].get(r['path']) == r['sha256'] and audit['source_hashes'].get(r['path']) == r['sha256'], 'Captured/baseline bytes bound by payload and audit')
    capture_ref = p['observation_identity']['capture_reference']; ref(capture_ref,sources)
    require(p['source_hashes'].get(capture_ref['path']) == capture_ref['sha256'] and audit['source_hashes'].get(capture_ref['path']) == capture_ref['sha256'], 'Capture identity source binding')

    require(p['schema'] == 'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1', 'Actual payload schema')
    require(receipt['schema'] == 'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1' and receipt['status'] == 'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY', 'Complete successful receipt only')
    require(audit['schema'] == ('PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1' if previous_history is None else OBSERVATION_READBACK_V2) and audit['status'] == 'PASS', 'Explicit versioned independent PASS')
    if previous_history is not None: exact(audit['parent_history_reference'],parent_ref,'Variable-prefix reader parent')
    require(type(audit['counts']['new_observation_count']) is int and audit['counts']['new_observation_count'] == 1,'Exactly one audited observation')
    observed_count = sum(r['kind'] != 'MISSED_OBSERVATION' for r in known)
    gap_count = sum(r['kind'] == 'MISSED_OBSERVATION' for r in known)
    for key, expected in (('parent_observed_count', observed_count), ('parent_gap_count', gap_count)):
        require(type(audit['counts'][key]) is int and audit['counts'][key] == expected, 'Actual reader parent count')
    if previous_history is None:
        require(len(known) == 65 and observed_count == 60 and gap_count == 5, 'V1 reader fixed65 observed60 gap5 boundary')

    exact(audit['counts']['month_first_actual_observation'],receipt['month_first_actual_observation'],'Audited coordinate')
    exact(audit['counts']['timing_classification'],receipt['timing_classification'],'Audited timing')
    exact(receipt['payload_reference'], observation['payload_reference'], 'Receipt payload')
    exact(audit['payload_reference'], observation['payload_reference'], 'Audit payload')
    exact(audit['receipt_reference'], observation['receipt_reference'], 'Audit receipt')
    require(audit['reader_sha256'] == observation['reader_reference']['sha256'], 'Reader source identity')
    for k in ('payload_reference','receipt_reference','reader_reference'):
        r = observation[k]; require(audit['source_hashes'].get(r['path']) == r['sha256'], 'Audit bound source')
    for doc in (p,receipt,audit):
        for f in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed'): require(doc[f] is False, 'No observation authority')
    require(audit['writer_called'] is False and audit['old_audit_repeated'] is False, 'Independent reader role')
    exact(p['known_typed_rows_preserved'], known, 'Complete original typed prefix')
    exact(p['parent_attempt_inventory_preserved'], inventory, 'No unresolved or omitted attempt')
    exact(p['parent_readback_reference'], parent_audit, 'Parent readback')
    identity = p['observation_identity']; exact(identity, dict(parent_reference=parent_ref,capture_reference=identity['capture_reference'],session=p['session']), 'Exact parent observation identity')
    ref(identity['capture_reference'], sources)
    identifier = hashlib.sha256(encoded(identity)).hexdigest()
    require(p['observation_id'] == receipt['observation_id'] == identifier and identifier not in {e['observation_id'] for e in entries}, 'Unique immutable observation')
    require(type(p['sequence']) is int and p['sequence'] == len(known)+1 and p['session'] > known[-1]['session'], 'Exactly next observation')
    require(p['kind'] == 'PROSPECTIVE_OBSERVED_SESSION' and p['initial_seal_status'] == 'NOT_ATTEMPTED', 'No seal event')
    for t in ('QQQ','SPY'): exact(p['full_original_sources_preserved'][t]['baseline_sources']['reference'],baseline[t], 'Same captured baseline bytes')
    month_first = rows_check(known,sources).get(p['session'][:7],p['session'])
    for obj in (p,receipt): require(type(obj['month_first_actual_observation']) is bool and obj['month_first_actual_observation'] == (month_first == p['session']), 'Actual month first independent of seal/timing')
    exact(p['first_actual_observed_session_of_month'],month_first,'First actual date')
    allowed=('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
    require(p['timing_classification'] in allowed and receipt['timing_classification'] in allowed, 'Saved timing class')
    require(p['timing_classification'] != 'LATE_OBSERVATION' or receipt['timing_classification'] == 'LATE_OBSERVATION','Never upgrade late')
    known.append(dict(sequence=p['sequence'],session=p['session'],kind=p['kind'],seal_status=p['initial_seal_status'],evidence_reference=dict(observation['payload_reference'],json_pointer='/observation_identity')))
    months = rows_check(known,sources); entries.append(compact_entry(observation));inventory.append(attempt_for(observation))
    new_baseline = captured_baselines(p)
    for r in new_baseline.values(): ref(r,sources)
    return dict(schema=SCHEMA,policy_id=POLICY,genesis_preserved=deepcopy(genesis),parent_history_reference=deepcopy(parent_ref),parent_readback_reference=deepcopy(parent_audit),known_typed_rows=known,observations=entries,parent_attempt_inventory=inventory,baseline_references=new_baseline,observation_count=len(entries),last_accounted_session=p['session'],first_actual_observed_session_by_month=months,source_hashes=deepcopy(sources),source_reference_claims=sources,observation_storage='COMPACT_EXTERNAL_REFERENCES_NO_CSV_ROWS_OR_BASE64',authentication_role='CALLER_SUPPLIED_EXTERNALLY_AUTHENTICATED_EVIDENCE_NOT_AUTHENTICATED_BY_PURE',**FLAGS)

def captured_baselines(payload):
    return {t:deepcopy(payload['full_original_sources_preserved'][t]['sources']['reference']) for t in ('QQQ','SPY')}

def attempt_for(entry):
    p = entry['payload'] if 'payload' in entry else entry
    return dict(observation_id=p['observation_id'],session=p['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=deepcopy(entry['payload_reference']),receipt_reference=deepcopy(entry['receipt_reference']),independent_readback_reference=deepcopy(entry['audit_reference']))


COMPACT_KEYS = {'schema','original_payload_embedded','observation_id','session','sequence',
    'observation_identity','initial_seal_status','timing_classification','payload_timing_classification',
    'month_first_actual_observation','first_actual_observed_session_of_month',
    'payload_reference','receipt_reference','audit_reference','reader_reference',
    'captured_baseline_references','previous_baseline_references','original_source_hash_claims'}

def compact_entry(observation):
    p, receipt = observation['payload'], observation['receipt']
    entry = {k:deepcopy(p[k]) for k in ('observation_id','session','sequence','observation_identity',
        'initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month')}
    entry.update(schema=ENTRY_SCHEMA,original_payload_embedded=False,
        timing_classification=receipt['timing_classification'],payload_timing_classification=p['timing_classification'],
        captured_baseline_references=captured_baselines(p),
        previous_baseline_references={t:deepcopy(p['full_original_sources_preserved'][t]['baseline_sources']['reference']) for t in ('QQQ','SPY')},
        original_source_hash_claims={k:deepcopy(observation[k]['source_hashes']) for k in ('payload','receipt','audit')})
    entry.update({k:deepcopy(observation[k]) for k in ('payload_reference','receipt_reference','audit_reference','reader_reference')})
    return entry
