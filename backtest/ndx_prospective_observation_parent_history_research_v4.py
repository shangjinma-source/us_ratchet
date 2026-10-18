"""Pure compact-history append and shared V3/V4 parent view; no IO or authority.

Reference declarations and readback assertions are structural inputs. Consumers
must authenticate saved bytes, CSV scope and full byte prefixes independently.
Only actual append is supported here; future gap append requires its own kernel.
"""
import base64
import csv
from copy import deepcopy
import hashlib
import io

from backtest import ndx_prospective_observation_parent_history_research as compact

SCHEMA='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4'
WRAPPER_SCHEMA='SOURCE_BOUND_PROSPECTIVE_OBSERVATION_HISTORY_V4'
PUBLICATION_SCHEMA='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V4'
PUBLICATION_STATUS='PUBLISHED_OBSERVATION_HISTORY_NO_SEAL'
READBACK_SCHEMA='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V4'
READBACK_STATUS='PURE_COMPACT_HISTORY_READBACK_PASS'
VIEW_SCHEMA='PROSPECTIVE_HISTORY_PARENT_VIEW_V4'
DEPENDENCY_SHA256='1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'
POLICY=compact.POLICY
ROLES=('reference','publication_reference','readback_reference','reader_reference')
OBSERVATION_ROLES=('payload_reference','receipt_reference','audit_reference','reader_reference')
WRAPPER_FALSE=('candidate_seal_allowed','clock_authenticity_verified','cohort_registration_allowed',
 'filesystem_attempt_inventory_authenticated','full_transitive_source_closure_reverified',
 'future_independent_oos','live_mutation_allowed','network_capture_performed','observation_created',
 'old_calendar_mutated','point_in_time_verified','promotion_allowed','source_authenticity_verified')
FLAGS=dict.fromkeys(WRAPPER_FALSE+('parent_history_authenticated_by_this_module','timeliness_verified',
 'production_generator_authorized','seal_event_created','partial_recovery_performed',
 'canonical_calendar_append_allowed','retrospective_backfill_allowed','decision_eligible',
 'accounted_baseline_scope_verified','full_source_byte_prefix_verified','gap_append_supported'),False)
OPTIONAL_FALSE=set(FLAGS)|{'receipt_published','exchange_holidays_verified','early_closes_verified',
    'parent_attempt_inventory_completeness_verified','seal_status_event_created','final_durable_completion_time_verified'}
BASELINE_ROLE='LAST_ACTUAL_OBSERVATION_BASELINE_NOT_LAST_ACCOUNTED'
ACCOUNTED_ROLE='FULL_SAVED_CSV_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS'


def require(ok,message):
    if not ok:raise ValueError(message)


def exact(left,right,message='Exact V4 structural association'):
    compact.exact(left,right,message)


def ref(item,sources):compact.ref(item,sources)


def declarations(value,sources):
    if type(value)is dict:
        if 'path'in value and 'sha256'in value:ref({key:value[key]for key in ('path','sha256')},sources)
        for key,item in value.items():
            if key in ('source_hashes','source_reference_claims'):
                require(type(item)is dict,'Source claim map')
                for path,digest in item.items():ref(dict(path=path,sha256=digest),sources)
            else:declarations(item,sources)
    elif type(value)is list:
        for item in value:declarations(item,sources)


def flags(value,mandatory):
    for key in mandatory:require(value.get(key)is False,'Strict false flag '+key)
    for key in OPTIONAL_FALSE.intersection(value):require(value[key]is False,'Contradictory optional flag '+key)


def integer(value,expected):require(type(value)is int and value==expected,'Exact integer count')


def history_counts_v4(history):
    return {key:deepcopy(history[key])for key in ('parent_typed_row_count','parent_actual_observation_count',
        'typed_row_count','observation_count','new_observation_count','gap_count','last_observed_session',
        'last_accounted_session','first_actual_observed_session_by_month')}


def inspect_parent_history_v4(parent):
    """Normalize V3/V4 declarations; scope_verified=False is a mandatory boundary."""
    require(type(parent)is dict and set(parent)==set(ROLES)|{'document','publication','readback'},'Full parent envelope')
    sources={}
    for role in ROLES:ref(parent[role],sources)
    d,p,a=(parent[key]for key in ('document','publication','readback'));h=d['history']
    v3=h['schema']=='PROSPECTIVE_GAP_EXTENSION_HISTORY_V3'
    require(v3 or h['schema']==SCHEMA,'Supported V3 or V4 history')
    exact(d['schema'],'SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3'if v3 else WRAPPER_SCHEMA)
    exact(p['schema'],'PROSPECTIVE_GAP_HISTORY_PUBLICATION_V3'if v3 else PUBLICATION_SCHEMA)
    exact(p['status'],'PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK'if v3 else PUBLICATION_STATUS)
    exact(a['schema'],'PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V3'if v3 else READBACK_SCHEMA)
    exact(a['status'],'PURE_GAP_HISTORY_READBACK_PASS'if v3 else READBACK_STATUS)
    for item in (d,p,a):flags(item,WRAPPER_FALSE);declarations(item,sources)
    for item in (p,a):exact(item['history_reference'],parent['reference'])
    exact(a['publication_reference'],parent['publication_reference']);exact(a['reader_sha256'],parent['reader_reference']['sha256'])
    exact(d['input_references'],p['input_references']);exact(d['input_references'],a['input_references'])
    exact(d['source_hashes'],p['source_hashes'])
    nested={};declarations(d,nested)
    for path,digest in nested.items():exact(d['source_hashes'].get(path),digest,'Wrapper source closure')
    for path,digest in d['source_hashes'].items():exact(a['source_hashes'].get(path),digest,'Audit source closure')
    for role in ('reference','publication_reference','reader_reference'):
        item=parent[role];exact(a['source_hashes'].get(item['path']),item['sha256'])
    require(a['entire_history_independently_reconstructed']is True and a['publisher_called']is False and
        a['new_pure_called']is False and a['current_live_cache_read_or_reverified']is False,'History readback roles')
    flags(h,WRAPPER_FALSE)
    exact(h['policy_id'],POLICY);exact(h['baseline_role'],BASELINE_ROLE)
    known=h['known_typed_rows'];months=compact.rows_check(known,sources)
    original_genesis=h['genesis_preserved']['document']['projection_inputs']['known_rows']
    require(type(original_genesis)is list and original_genesis,'Complete original genesis rows')
    exact(known[:len(original_genesis)],original_genesis,'Original genesis unchanged')
    actual=[row for row in known if row['kind']=='PROSPECTIVE_OBSERVED_SESSION']
    entries=h['observations'];attempts=h['parent_attempt_inventory']
    require(type(entries)is list and type(attempts)is list and len(entries)==len(attempts)==len(actual),'Actual entry/attempt bijection')
    integer(h['typed_row_count'],len(known));integer(h['observation_count'],len(actual))
    exact(h['first_actual_observed_session_by_month'],months);exact(h['last_accounted_session'],known[-1]['session'])
    last_actual=next(row['session']for row in reversed(known)if row['kind']!='MISSED_OBSERVATION')
    exact(h['last_observed_session'],last_actual)
    identities=set();actual_keys={(row['session'],row['sequence']):row for row in actual};used=set()
    require([entry['sequence']for entry in entries]==[row['sequence']for row in actual],'Actual entries ordered by typed sequence')
    for entry,attempt in zip(entries,attempts):
        exact(sorted(entry),sorted(compact.COMPACT_KEYS));exact(entry['schema'],compact.ENTRY_SCHEMA)
        require(entry['original_payload_embedded']is False,'Compact entry only')
        require(type(entry['sequence'])is int,'Actual sequence integer')
        key=(entry['session'],entry['sequence']);require(key in actual_keys and key not in used,'Actual entry/typed row exact bijection');used.add(key)
        exact(actual_keys[key]['evidence_reference'],dict(entry['payload_reference'],json_pointer='/observation_identity'))
        exact(attempt,compact.attempt_for(entry))
        identity=entry['observation_identity'];exact(identity['session'],entry['session'])
        exact(sorted(identity),['capture_reference','parent_reference','session'])
        identifier=hashlib.sha256(compact.encoded(identity)).hexdigest()
        exact(identifier,entry['observation_id']);require(identifier not in identities,'Unique actual identity');identities.add(identifier)
        first=months[entry['session'][:7]];exact(entry['first_actual_observed_session_of_month'],first)
        exact(entry['month_first_actual_observation'],entry['session']==first)
        exact(entry['initial_seal_status'],'NOT_ATTEMPTED')
        require(entry['timing_classification']in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')and
            entry['payload_timing_classification']in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),'Timing class')
        require(entry['payload_timing_classification']!='LATE_OBSERVATION'or entry['timing_classification']=='LATE_OBSERVATION','No late upgrade')
        exact(sorted(entry['original_source_hash_claims']),['audit','payload','receipt'])
        exact(entry['original_source_hash_claims']['payload'],entry['original_source_hash_claims']['receipt'])
        for path,digest in entry['original_source_hash_claims']['payload'].items():
            exact(entry['original_source_hash_claims']['audit'].get(path),digest)
        for role in ('payload_reference','receipt_reference','reader_reference'):
            item=entry[role];exact(entry['original_source_hash_claims']['audit'].get(item['path']),item['sha256'])
        for role in ('captured_baseline_references','previous_baseline_references'):
            require(type(entry[role])is dict and set(entry[role])=={'QQQ','SPY'},'Compact source pair')
            for item in entry[role].values():exact(entry['original_source_hash_claims']['payload'].get(item['path']),item['sha256'])
        for role in ('parent_reference','capture_reference'):
            item=identity[role];exact(entry['original_source_hash_claims']['payload'].get(item['path']),item['sha256'])
    require(used==set(actual_keys),'No omitted actual entry')
    if entries:exact(h['baseline_references'],entries[-1]['captured_baseline_references'])
    require(set(h['baseline_references'])=={'QQQ','SPY'},'Last actual baseline pair')
    if v3:
        for key in ('pending_source_sessions','excluded_not_completed_source_sessions'):
            require(type(h[key])is list and not h[key],'BASELINE_HAS_UNACCOUNTED_SUFFIX')
        exact(h['captured_sources_are_exact_accounted_prefix'],False)
        accounted=h['captured_source_references']
        for key,role in [('parent_history_reference','reference'),('parent_publication_reference','publication_reference'),('parent_readback_reference','readback_reference')]:
            exact(h[key],d['input_references']['parent'][role])
        for key,role in [('capture_reference','reference'),('capture_publication_reference','publication_reference'),('capture_readback_reference','readback_reference')]:
            exact(h[key],d['input_references']['capture'][role])
        original=h['known_typed_rows_preserved'];integer(h['parent_typed_row_count'],len(original))
        exact(known[:len(original)],original)
        added=known[len(original):];require(all(row['kind']=='MISSED_OBSERVATION'for row in added),'V3 gap-only extension')
        integer(h['new_missed_observation_count'],len(added));integer(h['new_observation_count'],0)
        exact([row['session']for row in added],[value['session']for value in h['gap_classifications']])
        exact(a['counts'],{key:h[key]for key in ('parent_typed_row_count','typed_row_count','observation_count','new_observation_count',
            'new_missed_observation_count','last_observed_session','last_accounted_session','first_actual_observed_session_by_month')})
    else:
        flags(h,FLAGS)
        accounted=h['accounted_baseline_references'];exact(h['accounted_baseline_role'],ACCOUNTED_ROLE)
        original=h['known_typed_rows_preserved'];integer(h['parent_typed_row_count'],len(original))
        exact(known[:-1],original);require(known[-1]['kind']=='PROSPECTIVE_OBSERVED_SESSION','V4 actual append only')
        exact(known[-1]['seal_status'],'NOT_ATTEMPTED','No V4 append seal event')
        integer(h['new_observation_count'],1);integer(h['parent_actual_observation_count'],len(actual)-1)
        integer(h['gap_count'],sum(row['kind']=='MISSED_OBSERVATION'for row in known))
        exact(accounted,h['baseline_references'])
        exact(h['parent_references'],d['input_references']['parent']);exact(h['observation_references'],d['input_references']['observation'])
        exact(h['observation_references'],{role:entries[-1][role]for role in OBSERVATION_ROLES})
        exact(entries[-1]['observation_identity']['parent_reference'],h['parent_references']['reference'])
        exact(a['counts'],history_counts_v4(h))
    require(type(accounted)is dict and set(accounted)=={'QQQ','SPY'},'Accounted baseline pair')
    for item in (*accounted.values(),*h['baseline_references'].values()):ref(item,sources)
    ref(h['tzif_reference'],sources)
    return dict(schema=VIEW_SCHEMA,policy_id=POLICY,parent_schema=h['schema'],parent_references={role:deepcopy(parent[role])for role in ROLES},
        known_typed_rows=deepcopy(known),observations=deepcopy(entries),parent_attempt_inventory=deepcopy(attempts),
        first_actual_observed_session_by_month=deepcopy(months),baseline_references=deepcopy(h['baseline_references']),
        baseline_role=BASELINE_ROLE,accounted_baseline_references=deepcopy(accounted),accounted_baseline_role=ACCOUNTED_ROLE,
        last_observed_session=last_actual,last_accounted_session=known[-1]['session'],genesis_preserved=deepcopy(h['genesis_preserved']),
        typed_row_count=len(known),observation_count=len(actual),gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in known),
        tzif_reference=deepcopy(h['tzif_reference']),
        source_hashes=sources,scope_and_complete_byte_prefix_require_independent_io_verification=True,**FLAGS)


def append_observation_history_v4(*,parent,observation):
    view=inspect_parent_history_v4(parent);sources=deepcopy(view['source_hashes'])
    require(type(observation)is dict and set(observation)==set(OBSERVATION_ROLES)|{'payload','receipt','audit'},'Complete independently read observation')
    for role in OBSERVATION_ROLES:ref(observation[role],sources)
    payload,receipt,audit=(observation[key]for key in ('payload','receipt','audit'))
    for obj in (payload,receipt,audit):
        declarations(obj,sources)
        flags(obj,('source_authenticity_verified','clock_authenticity_verified','filesystem_attempt_inventory_authenticated',
            'candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed',
            'future_independent_oos','production_generator_authorized'))
    exact(payload['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')
    exact(receipt['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1')
    exact(receipt['status'],'PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY')
    exact(audit['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3');exact(audit['status'],'PASS')
    require(audit['writer_called']is False and audit['payload_core_called']is False and audit['old_audit_repeated']is False,'Independent observation reader role')
    exact(receipt['payload_reference'],observation['payload_reference']);exact(audit['payload_reference'],observation['payload_reference'])
    exact(audit['receipt_reference'],observation['receipt_reference']);exact(audit['reader_sha256'],observation['reader_reference']['sha256'])
    exact(audit['parent_history_reference'],parent['reference'])
    exact(payload['source_hashes'],receipt['source_hashes'])
    for path,digest in payload['source_hashes'].items():exact(audit['source_hashes'].get(path),digest)
    for role in ('payload_reference','receipt_reference','reader_reference'):
        item=observation[role];exact(audit['source_hashes'].get(item['path']),item['sha256'])
    known=view['known_typed_rows'];attempts=view['parent_attempt_inventory'];entries=view['observations'];months=view['first_actual_observed_session_by_month']
    exact(payload['known_typed_rows_preserved'],known);exact(payload['parent_attempt_inventory_preserved'],attempts)
    exact(payload['parent_readback_reference'],parent['readback_reference'])
    for obj in (payload,receipt,audit):exact(obj['input_references']['parent'],view['parent_references'])
    capture_refs=payload['input_references']['capture'];require(set(capture_refs)==set(ROLES),'Capture four roles')
    for role in ROLES:ref(capture_refs[role],sources)
    for obj in (receipt,audit):exact(obj['input_references']['capture'],capture_refs)
    for item in (*view['parent_references'].values(),*capture_refs.values()):
        exact(payload['source_hashes'].get(item['path']),item['sha256'],'Observation input source association')
    identity=payload['observation_identity'];session=payload['session']
    exact(identity,dict(parent_reference=parent['reference'],capture_reference=capture_refs['reference'],session=session))
    identifier=hashlib.sha256(compact.encoded(identity)).hexdigest()
    exact(payload['observation_id'],identifier);exact(receipt['observation_id'],identifier)
    require(identifier not in {entry['observation_id']for entry in entries},'Unique observation')
    integer(payload['sequence'],len(known)+1);require(type(session)is str and session>known[-1]['session'],'Next unique session')
    exact(payload['kind'],'PROSPECTIVE_OBSERVED_SESSION');exact(payload['initial_seal_status'],'NOT_ATTEMPTED')
    first=months.get(session[:7],session)
    exact(payload['first_actual_observed_session_of_month'],first)
    for obj in (payload,receipt):exact(obj['month_first_actual_observation'],first==session)
    require(payload['timing_classification']in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')and
        receipt['timing_classification']in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),'Timing class')
    require(payload['timing_classification']!='LATE_OBSERVATION'or receipt['timing_classification']=='LATE_OBSERVATION','No late upgrade')
    counts=audit['counts']
    flags(counts,())
    ref(payload['tzif_reference'],sources)
    exact(payload['tzif_reference']['sha256'],view['tzif_reference']['sha256'],'Parent TZif hash continuity')
    exact(payload['source_hashes'].get(payload['tzif_reference']['path']),payload['tzif_reference']['sha256'])
    exact(hashlib.sha256(base64.b64decode(payload['tzif_bytes_base64'],validate=True)).hexdigest(),payload['tzif_reference']['sha256'])
    for key,expected in [('parent_typed_row_count',len(known)),('parent_actual_observation_count',len(entries)),
        ('parent_observed_count',sum(row['kind']!='MISSED_OBSERVATION'for row in known)),
        ('parent_gap_count',sum(row['kind']=='MISSED_OBSERVATION'for row in known)),('new_observation_count',1)]:integer(counts[key],expected)
    exact(counts['month_first_actual_observation'],receipt['month_first_actual_observation']);exact(counts['timing_classification'],receipt['timing_classification'])
    require(set(payload['full_original_sources_preserved'])=={'QQQ','SPY'},'Full source pair')
    new_baselines={}
    for ticker in ('QQQ','SPY'):
        parts=payload['full_original_sources_preserved'][ticker];exact(sorted(parts),['baseline_sources','sources'])
        for role in ('baseline_sources','sources'):
            part=parts[role];ref(part['reference'],sources)
            exact(payload['source_hashes'].get(part['reference']['path']),part['reference']['sha256'])
            require(type(part['rows'])is list and part['rows'],'Full CSV row declarations')
            exact(part['required_scope_start'],known[0]['session'])
            raw=base64.b64decode(part['original_csv_bytes_base64'],validate=True)
            require(0<len(raw)<=8_000_000,'Bounded full CSV input')
            exact(hashlib.sha256(raw).hexdigest(),part['reference']['sha256'],'Original CSV declaration hash')
            parsed=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
            exact(parsed.fieldnames,['Date','Open','High','Low','Close','Volume'])
            exact(list(parsed),part['rows'],'Raw CSV and declared rows agree')
        old,current=parts['baseline_sources'],parts['sources']
        exact(old['reference'],view['accounted_baseline_references'][ticker])
        require(base64.b64decode(current['original_csv_bytes_base64']).startswith(base64.b64decode(old['original_csv_bytes_base64'])),'Full accounted byte prefix')
        scope=lambda rows:[row['Date']for row in rows if row['Date']>=known[0]['session']]
        exact(scope(old['rows']),[row['session']for row in known],'V3/V4 accounted scope exactly known')
        exact(scope(current['rows']),[row['session']for row in known]+[session],'One new source session')
        exact(current['rows'][:-1],old['rows']);new_baselines[ticker]=deepcopy(current['reference'])
    preserved=deepcopy(known)
    known.append(dict(sequence=payload['sequence'],session=session,kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='NOT_ATTEMPTED',
        evidence_reference=dict(observation['payload_reference'],json_pointer='/observation_identity')))
    months=compact.rows_check(known,sources);entry=compact.compact_entry(observation);entries.append(entry);attempts.append(compact.attempt_for(entry))
    return dict(schema=SCHEMA,status='APPENDED_ONE_RESEARCH_OBSERVATION_NO_SEAL',policy_id=POLICY,
        parent_references=deepcopy(view['parent_references']),observation_references={role:deepcopy(observation[role])for role in OBSERVATION_ROLES},
        genesis_preserved=deepcopy(view['genesis_preserved']),known_typed_rows=known,known_typed_rows_preserved=preserved,
        observations=entries,parent_attempt_inventory=attempts,parent_typed_row_count=len(preserved),
        parent_actual_observation_count=len(entries)-1,typed_row_count=len(known),observation_count=len(entries),new_observation_count=1,
        gap_count=sum(row['kind']=='MISSED_OBSERVATION'for row in known),first_actual_observed_session_by_month=months,
        baseline_references=deepcopy(new_baselines),baseline_role=BASELINE_ROLE,accounted_baseline_references=deepcopy(new_baselines),
        accounted_baseline_role=ACCOUNTED_ROLE,last_observed_session=session,last_accounted_session=session,
        tzif_reference=deepcopy(payload['tzif_reference']),
        source_hashes=deepcopy(sources),source_reference_claims=deepcopy(sources),
        observation_storage='COMPACT_EXTERNAL_REFERENCES_NO_CSV_ROWS_OR_BASE64',
        authentication_role='STRUCTURAL_DECLARATIONS_ONLY_BYTES_AND_SCOPE_AUTHENTICATION_REMAIN_EXTERNAL',
        raw_source_bytes_embedded=False,dependency_sha256=DEPENDENCY_SHA256,**FLAGS)
