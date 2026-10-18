"""True V3/V4/V5 parent append adapter producing the unchanged V4 actual format.

No IO, wrapper fabrication or frozen append execution. A complete one-candidate
snapshot consumes the whole prior suffix. Cross-format original-evidence replay
and ancestor inventories remain explicit duties of future IO adapters.
"""
import base64,csv,hashlib,io
from copy import deepcopy
from datetime import datetime,timedelta
from backtest import ndx_prospective_history_parent_view_research_v5 as parent_view
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy

ADAPTER_SCHEMA='TRUE_V5_PARENT_COMPACT_ACTUAL_APPEND_ADAPTER_V1'
SCHEMA=legacy.SCHEMA
WRAPPER_SCHEMA=legacy.WRAPPER_SCHEMA
PUBLICATION_SCHEMA=legacy.PUBLICATION_SCHEMA
PUBLICATION_STATUS=legacy.PUBLICATION_STATUS
READBACK_SCHEMA=legacy.READBACK_SCHEMA
READBACK_STATUS=legacy.READBACK_STATUS
POLICY=legacy.POLICY
BASELINE_ROLE=legacy.BASELINE_ROLE
ACCOUNTED_ROLE=legacy.ACCOUNTED_ROLE
ROLES=legacy.ROLES
OBSERVATION_ROLES=legacy.OBSERVATION_ROLES
FLAGS=dict(legacy.FLAGS)
DEPENDENCY_SHA256='1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'
ADAPTER_DEPENDENCY_SHA256=dict(parent_view='32bcabfbc08a63607b650141f7295fc1ed12a3fdeeb081527c8b32d8cc250373',
    legacy_view='06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99',compact_helpers=DEPENDENCY_SHA256)
compact=legacy.compact
require=legacy.require
exact=legacy.exact
ref=legacy.ref
declarations=legacy.declarations
flags=legacy.flags
integer=legacy.integer
history_counts_v4=legacy.history_counts_v4


def utc(value):
    require(type(value)is str,'UTC string');result=datetime.fromisoformat(value)
    require(result.tzinfo is not None and result.utcoffset()==timedelta(0),'Aware UTC')
    return result


def append_observation_history(*,parent,observation):
    view=parent_view.inspect_parent_history_v5(parent);sources=deepcopy(view['source_hashes'])
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
    known=deepcopy(view['known_typed_rows']);attempts=deepcopy(view['parent_attempt_inventory']);entries=deepcopy(view['observations']);months=deepcopy(view['first_actual_observed_session_by_month'])
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
    prior_suffix=view['pending_source_sessions']+view['excluded_not_completed_source_sessions']
    require(not prior_suffix or [item['session']for item in prior_suffix]==[session],'Whole prior suffix must be the unique consumed actual candidate')
    if view['parent_schema']==parent_view.GAP_SCHEMA:
        for obj in (payload,receipt,audit):
            exact(obj.get('writer_adapter_schema'),'REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5')
            exact(obj.get('actual_parent_schema'),view['parent_schema'])
        begin=utc(payload['capture_started_at_utc'])
        require(all(begin>=utc(item['capture_completed_at_utc'])for item in prior_suffix),'No regressed prior suffix capture clock')
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
        exact(payload['selected_original_rows'][ticker],current['rows'][-1])
        exact(payload['source_row_locations'][ticker],dict(original_data_row_index=len(current['rows'])-1,reference=current['reference']))
    preserved=deepcopy(known)
    known.append(dict(sequence=payload['sequence'],session=session,kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='NOT_ATTEMPTED',
        evidence_reference=dict(observation['payload_reference'],json_pointer='/observation_identity')))
    months=compact.rows_check(known,sources)
    entry={key:deepcopy(payload[key])for key in ('observation_id','session','sequence','observation_identity','initial_seal_status',
        'month_first_actual_observation','first_actual_observed_session_of_month')}
    entry.update(schema=compact.ENTRY_SCHEMA,original_payload_embedded=False,timing_classification=receipt['timing_classification'],
        payload_timing_classification=payload['timing_classification'],captured_baseline_references=deepcopy(new_baselines),
        previous_baseline_references=deepcopy(view['accounted_baseline_references']),
        original_source_hash_claims={role:deepcopy(observation[role]['source_hashes'])for role in ('payload','receipt','audit')})
    entry.update({role:deepcopy(observation[role])for role in OBSERVATION_ROLES});entries.append(entry)
    attempts.append(dict(observation_id=identifier,session=session,status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',
        payload_reference=deepcopy(observation['payload_reference']),receipt_reference=deepcopy(observation['receipt_reference']),
        independent_readback_reference=deepcopy(observation['audit_reference'])))
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
