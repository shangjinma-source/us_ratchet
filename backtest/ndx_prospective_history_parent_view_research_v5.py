"""Pure V5 parent declarations, preserving full capture and unconsumed suffix.

Legacy V3/V4 envelopes are inspected by the frozen V4 checker. V5 envelopes
are checked directly. Prior snapshots, source bytes, CSV scopes, timing values
and raw byte spans still need independent verification against external files.
"""
from copy import deepcopy
from datetime import date,datetime,timedelta
import hashlib
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy

LEGACY_VIEW_SHA256='06b06afa15821645b336d1979cfd8b432345f359c77d065f297d1ab83c939f99'
COMPACT_HELPER_SHA256='1bc7a01e292a473fcb2fcbef7f0d833228cb4e3c94126a77d91c6d41c9c62cb0'
LEGACY_CHECKER_PATH=str(legacy.__file__)
SCHEMA='PROSPECTIVE_GAP_EXTENSION_HISTORY_V5'
GAP_SCHEMA=SCHEMA
WRAPPER_SCHEMA='SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V5'
PUBLICATION_SCHEMA='PROSPECTIVE_GAP_HISTORY_PUBLICATION_V5'
PUBLICATION_STATUS='PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK'
READBACK_SCHEMA='PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V5'
READBACK_STATUS='PURE_GAP_HISTORY_READBACK_PASS'
VIEW_SCHEMA='PROSPECTIVE_HISTORY_PARENT_VIEW_V5'
FULL_CAPTURE_ROLE='FULL_ORIGINAL_CAPTURE_INCLUDING_UNCONSUMED_SOURCE_SUFFIX'
PREFIX_ROLE='ORIGINAL_BYTE_PREFIX_SCOPE_EQUALS_ALL_KNOWN_TYPED_SESSIONS'
ACCOUNTED_PREFIX_ROLE=PREFIX_ROLE
LEGACY_PREFIX_ROLE='LEGACY_SAVED_ACCOUNTED_BASELINE_NOT_DERIVED_BY_V5'
ROLES=legacy.ROLES
POLICY=legacy.POLICY
FLAGS=dict(legacy.FLAGS,legacy_runtimes_support_this_view=False,pending_source_sessions_consumed=False,
    prior_state_authenticated=False,source_bytes_verified=False,accounted_prefix_byte_span_verified=False,
    timing_classification_recomputed_from_tzif=False)
OPTIONAL_FALSE=set(legacy.OPTIONAL_FALSE)|set(FLAGS)|{'exchange_calendar_verified'}
STATE_KEYS=('parent_schema','parent_references','known_typed_rows','observations','parent_attempt_inventory',
    'first_actual_observed_session_by_month','baseline_references','baseline_role','accounted_baseline_references',
    'accounted_baseline_role','last_observed_session','last_accounted_session','genesis_preserved',
    'typed_row_count','observation_count','gap_count','tzif_reference','source_hashes',
    'full_capture_source_references','full_capture_source_role','pending_source_sessions','excluded_not_completed_source_sessions')
HISTORY_KEYS=('schema','status','policy_id','parent_references','capture_references','parent_state_reference',
    'prior_state_preserved','known_typed_rows','known_typed_rows_preserved','observations','parent_attempt_inventory',
    'first_actual_observed_session_by_month','genesis_preserved','baseline_references','baseline_role',
    'full_capture_source_references','full_capture_source_role','accounted_prefix_references','accounted_prefix_evidence','accounted_prefix_evidence_references',
    'accounted_prefix_role','source_evidence','gap_classifications','pending_source_sessions',
    'excluded_not_completed_source_sessions','last_observed_session','last_accounted_session','typed_row_count',
    'parent_typed_row_count','parent_actual_observation_count','observation_count','gap_count','new_observation_count',
    'new_missed_observation_count','capture_started_at','capture_completed_at','tzif_reference','source_hashes',
    'source_reference_claims','raw_source_bytes_embedded')
SOURCE_EVIDENCE_KEYS=('source_reference','accounted_baseline_reference','actual_baseline_reference','original_row_count',
    'source_session_dates','new_session_dates','full_accounted_bytes_prefix_matches','included_original_row_indexes',
    'excluded_original_row_indexes','excluded_before_scope_ohlc_diagnostics')
CLASSIFICATION_KEYS=('session','conservative_close_utc','conservative_next_weekday_open_utc','capture_started_at_utc',
    'capture_completed_at_utc','source_session_pointer_by_ticker','counts_as_observed_session','consumes_month_first_opportunity',
    'decision_eligible','classification')
PREFIX_FALSE=('source_authenticity_verified','clock_authenticity_verified','point_in_time_verified','observation_created',
    'decision_eligible','candidate_seal_allowed','cohort_registration_allowed','future_independent_oos','promotion_allowed',
    'live_mutation_allowed','filesystem_attempt_inventory_authenticated','network_capture_performed','timeliness_verified','exchange_calendar_verified')
PREFIX_KEYS=('schema','full_source_reference','full_source_byte_count','prefix_sha256','prefix_byte_count','byte_start','byte_stop',
    'scope_start','accounted_sessions','suffix_sessions','original_row_count','retained_original_row_count',
    'accounted_original_row_indexes','suffix_original_row_indexes','excluded_before_scope_original_row_indexes',
    'excluded_before_scope_rows_count','excluded_before_scope_rows_sha256','excluded_before_scope_ohlc_diagnostics_count',
    'excluded_before_scope_ohlc_diagnostics_sha256','prefix_selection','byte_span_semantics',
    'prefix_is_original_initial_byte_range','csv_reserialized','full_source_bytes_embedded','prefix_bytes_embedded',
    'dependency_sha256','authentication_role')


def require(ok,message):
    if not ok:raise ValueError(message)


def exact(a,b,message='Exact V5 declaration'):legacy.exact(a,b,message)
def ref(item,sources):legacy.ref(item,sources)
def integer(value,expected):require(type(value)is int and value==expected,'Exact V5 integer')


def flags(item,mandatory=()):
    require(type(item)is dict,'Declaration object')
    for key in mandatory:require(item.get(key)is False,'Mandatory false '+key)
    for key in OPTIONAL_FALSE.intersection(item):require(item[key]is False,'Optional false '+key)


def pair(value):require(type(value)is dict and set(value)=={'QQQ','SPY'},'Exact ticker pair')


def sessions(value):
    require(type(value)is list,'Session list');previous=''
    for item in value:
        require(type(item)is str,'Session string');parsed=date.fromisoformat(item)
        require(parsed.isoformat()==item and parsed.weekday()<5 and item>previous,'Ordered unique weekday sessions');previous=item
    return value


def utc(value):
    require(type(value)is str,'Explicit UTC string');parsed=datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset()==timedelta(0),'Aware UTC');return parsed


def parent_state_for_gap(view):
    """Fixed-size-shape prior snapshot; never recursively embeds parent wrappers."""
    require(type(view)is dict and all(key in view for key in STATE_KEYS),'Complete normalized parent')
    return {key:deepcopy(view[key])for key in STATE_KEYS}


def prefix_evidence_summary(evidence):
    """List digests omit LF; the full evidence artifact has a separate IO SHA."""
    result=deepcopy(evidence)
    for key in ('excluded_before_scope_rows','excluded_before_scope_ohlc_diagnostics'):
        require(type(result.get(key))is list,'Full evidence list')
        values=result.pop(key);result[key+'_count']=len(values)
        result[key+'_sha256']=hashlib.sha256(legacy.compact.encoded(values)).hexdigest()
    return result


def gap_counts(history):
    keys=('parent_typed_row_count','parent_actual_observation_count','typed_row_count','observation_count',
        'gap_count','new_observation_count','new_missed_observation_count','last_observed_session',
        'last_accounted_session','first_actual_observed_session_by_month')
    return dict({key:deepcopy(history[key])for key in keys},pending_source_session_count=len(history['pending_source_sessions']),
        excluded_not_completed_source_session_count=len(history['excluded_not_completed_source_sessions']))


def check_state(state,sources):
    """Validate a compact state directly; this never fabricates a legacy wrapper."""
    known=state['known_typed_rows'];months=legacy.compact.rows_check(known,sources)
    require(type(known)is list and known,'Nonempty typed history')
    genesis=state['genesis_preserved']['document']['projection_inputs']['known_rows']
    require(type(genesis)is list and genesis,'Original genesis');exact(known[:len(genesis)],genesis)
    actual=[row for row in known if row['kind']=='PROSPECTIVE_OBSERVED_SESSION']
    entries,attempts=state['observations'],state['parent_attempt_inventory']
    require(type(entries)is list and type(attempts)is list and len(entries)==len(attempts)==len(actual),'Actual/attempt bijection')
    integer(state['typed_row_count'],len(known));integer(state['observation_count'],len(actual))
    integer(state['gap_count'],sum(row['kind']=='MISSED_OBSERVATION'for row in known))
    exact(state['first_actual_observed_session_by_month'],months);exact(state['last_accounted_session'],known[-1]['session'])
    last_actual=next(row['session']for row in reversed(known)if row['kind']!='MISSED_OBSERVATION')
    exact(state['last_observed_session'],last_actual);exact(state['baseline_role'],legacy.BASELINE_ROLE)
    exact(state['accounted_baseline_role'],legacy.ACCOUNTED_ROLE)
    identities=set()
    for row,entry,attempt in zip(actual,entries,attempts):
        exact(sorted(entry),sorted(legacy.compact.COMPACT_KEYS));exact(entry['schema'],legacy.compact.ENTRY_SCHEMA)
        require(entry['original_payload_embedded']is False and type(entry['sequence'])is int,'Compact actual entry')
        exact((entry['session'],entry['sequence']),(row['session'],row['sequence']))
        exact(row['evidence_reference'],dict(entry['payload_reference'],json_pointer='/observation_identity'))
        exact(attempt,legacy.compact.attempt_for(entry));identity=entry['observation_identity']
        exact(sorted(identity),['capture_reference','parent_reference','session']);exact(identity['session'],entry['session'])
        identifier=hashlib.sha256(legacy.compact.encoded(identity)).hexdigest();exact(entry['observation_id'],identifier)
        require(identifier not in identities,'Unique actual identity');identities.add(identifier)
        first=months[entry['session'][:7]];exact(entry['first_actual_observed_session_of_month'],first)
        exact(entry['month_first_actual_observation'],entry['session']==first);exact(entry['initial_seal_status'],'NOT_ATTEMPTED')
        for key in ('timing_classification','payload_timing_classification'):
            require(entry[key]in ('LATE_OBSERVATION','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),'Timing class')
        require(entry['payload_timing_classification']!='LATE_OBSERVATION'or entry['timing_classification']=='LATE_OBSERVATION','No late upgrade')
        claims=entry['original_source_hash_claims'];exact(sorted(claims),['audit','payload','receipt']);exact(claims['payload'],claims['receipt'])
        for path,digest in claims['payload'].items():exact(claims['audit'].get(path),digest)
        for role in ('payload_reference','receipt_reference','reader_reference'):
            item=entry[role];exact(claims['audit'].get(item['path']),item['sha256'])
        for key in ('captured_baseline_references','previous_baseline_references'):
            pair(entry[key])
            for item in entry[key].values():exact(claims['payload'].get(item['path']),item['sha256'])
        for role in ('parent_reference','capture_reference'):
            item=identity[role];exact(claims['payload'].get(item['path']),item['sha256'])
    pair(state['baseline_references']);pair(state['accounted_baseline_references'])
    if entries:exact(state['baseline_references'],entries[-1]['captured_baseline_references'])
    for item in (*state['baseline_references'].values(),*state['accounted_baseline_references'].values(),state['tzif_reference']):ref(item,sources)
    pair(state['full_capture_source_references'])
    for item in state['full_capture_source_references'].values():ref(item,sources)
    pending,unfinished=state['pending_source_sessions'],state['excluded_not_completed_source_sessions']
    require(type(pending)is list and type(unfinished)is list and len(pending)<=1,'Explicit prior suffix classification lists')
    suffix=sessions([item['session']for item in pending+unfinished]);require(not suffix or suffix[0]>known[-1]['session'],'Unaccounted suffix strictly follows known')
    if state.get('parent_schema',SCHEMA)!=SCHEMA:
        require(not suffix,'Legacy view cannot certify a pending suffix')
        exact(state['full_capture_source_role'],'LEGACY_COMPLETE_ACCOUNTED_SNAPSHOT_NO_SUFFIX_DECLARED')
        exact(state['full_capture_source_references'],state['accounted_baseline_references'])
    else:
        exact(state['full_capture_source_role'],FULL_CAPTURE_ROLE)
        for values,classification in ((pending,'DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL'),(unfinished,'SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START')):
            for item in values:
                require(type(item)is dict and set(item)==set(CLASSIFICATION_KEYS),'Exact prior suffix record')
                exact(item['classification'],classification)
                for key in ('counts_as_observed_session','consumes_month_first_opportunity','decision_eligible'):require(item[key]is False,'Prior suffix unconsumed')
                start,end=utc(item['capture_started_at_utc']),utc(item['capture_completed_at_utc']);require(start<=end,'Prior capture clock order')
                close,deadline=utc(item['conservative_close_utc']),utc(item['conservative_next_weekday_open_utc']);require(close<deadline,'Prior timing order')
                require(start<close if values is unfinished else close<=start<deadline,'Prior suffix timing class')
    return months


def check_prefix(evidence,full,prefix,known,suffix,source):
    require(type(evidence)is dict and set(evidence)==set(PREFIX_KEYS)|set(PREFIX_FALSE),'Exact prefix evidence fields')
    flags(evidence,PREFIX_FALSE);exact(evidence['schema'],'ACCOUNTED_SOURCE_BYTE_PREFIX_EVIDENCE_V1')
    exact(evidence['full_source_reference'],full);exact(evidence['prefix_sha256'],prefix['sha256'])
    exact(evidence['accounted_sessions'],known);exact(evidence['suffix_sessions'],suffix);exact(evidence['scope_start'],known[0])
    integer(evidence['byte_start'],0)
    for key in ('full_source_byte_count','prefix_byte_count','byte_stop','original_row_count','retained_original_row_count'):
        require(type(evidence[key])is int and evidence[key]>0,'Positive byte/count integer')
    exact(evidence['byte_stop'],evidence['prefix_byte_count']);require(evidence['prefix_byte_count']<=evidence['full_source_byte_count'],'Original byte range')
    if suffix:require(evidence['prefix_byte_count']<evidence['full_source_byte_count'],'Unconsumed suffix bytes')
    else:
        exact(evidence['prefix_byte_count'],evidence['full_source_byte_count']);exact(prefix['sha256'],full['sha256'])
    excluded=evidence['excluded_before_scope_original_row_indexes'];require(type(excluded)is list,'Excluded index list')
    exact(excluded,list(range(len(excluded))))
    count=source['original_row_count'];integer(evidence['original_row_count'],count)
    expected_accounted=list(range(len(excluded),len(excluded)+len(known)));expected_suffix=list(range(len(excluded)+len(known),count))
    exact(evidence['accounted_original_row_indexes'],expected_accounted);exact(evidence['suffix_original_row_indexes'],expected_suffix)
    require(len(expected_suffix)==len(suffix),'Complete source suffix indexes');integer(evidence['retained_original_row_count'],len(excluded)+len(known))
    integer(evidence['excluded_before_scope_rows_count'],len(excluded))
    for key in ('excluded_before_scope_rows_sha256','excluded_before_scope_ohlc_diagnostics_sha256'):
        ref(dict(path='declared-list-digest/'+key,sha256=evidence[key]),{})
    diagnostics=source['excluded_before_scope_ohlc_diagnostics'];require(type(diagnostics)is list,'Declared outside diagnostics')
    integer(evidence['excluded_before_scope_ohlc_diagnostics_count'],len(diagnostics))
    exact(evidence['excluded_before_scope_ohlc_diagnostics_sha256'],hashlib.sha256(legacy.compact.encoded(diagnostics)).hexdigest())
    exact(evidence['prefix_selection'],'COMPLETE_ACCOUNTED_SESSION_PREFIX_NOT_PRICE_OR_TIMELINESS_SELECTED')
    exact(evidence['byte_span_semantics'],'ZERO_BASED_START_INCLUSIVE_STOP_EXCLUSIVE_ORIGINAL_BYTES')
    require(evidence['prefix_is_original_initial_byte_range']is True,'Declared initial byte range')
    for key in ('csv_reserialized','full_source_bytes_embedded','prefix_bytes_embedded'):require(evidence[key]is False,'No reserialized/embedded bytes')
    exact(evidence['dependency_sha256'],dict(scoped='9723d79f6187003457e96c439f1f4c0949701727881dfb6bb59fb0da8bc8efee',base='30db1a7ada86a8ee710e3681aecd406ecfb866ce9f270ae50eb8e60742e51642'))
    exact(evidence['authentication_role'],'SUPPLIED_BYTES_DERIVATION_NOT_EXTERNAL_SOURCE_OR_CLOCK_AUTHENTICATION')


def inspect_parent_history_v5(parent):
    require(type(parent)is dict and set(parent)==set(ROLES)|{'document','publication','readback'},'Complete parent envelope')
    if parent['document']['history']['schema']!=SCHEMA:
        old=legacy.inspect_parent_history_v4(parent);view=deepcopy(old);view.update(schema=VIEW_SCHEMA,
            full_capture_source_references=deepcopy(old['accounted_baseline_references']),full_capture_source_role='LEGACY_COMPLETE_ACCOUNTED_SNAPSHOT_NO_SUFFIX_DECLARED',
            accounted_prefix_references=deepcopy(old['accounted_baseline_references']),accounted_prefix_evidence={},accounted_prefix_evidence_references={},accounted_prefix_role=LEGACY_PREFIX_ROLE,
            pending_source_sessions=[],excluded_not_completed_source_sessions=[],legacy_checker_reference=dict(path=LEGACY_CHECKER_PATH,sha256=LEGACY_VIEW_SHA256),
            legacy_checker_called=True,**FLAGS)
        return view
    sources={}
    for role in ROLES:ref(parent[role],sources)
    d,p,a=(parent[key]for key in ('document','publication','readback'));h=d['history']
    for obj,schema in ((d,WRAPPER_SCHEMA),(p,PUBLICATION_SCHEMA),(a,READBACK_SCHEMA)):
        exact(obj['schema'],schema);flags(obj,legacy.WRAPPER_FALSE);legacy.declarations(obj,sources)
    exact(p['status'],PUBLICATION_STATUS);exact(a['status'],READBACK_STATUS)
    for obj in (p,a):exact(obj['history_reference'],parent['reference'])
    exact(a['publication_reference'],parent['publication_reference']);exact(a['reader_sha256'],parent['reader_reference']['sha256'])
    exact(d['input_references'],p['input_references']);exact(d['input_references'],a['input_references']);exact(d['source_hashes'],p['source_hashes'])
    nested={};legacy.declarations(d,nested)
    for path,digest in nested.items():exact(d['source_hashes'].get(path),digest,'Full wrapper source closure')
    for path,digest in d['source_hashes'].items():exact(a['source_hashes'].get(path),digest,'Readback source closure')
    for role in ('reference','publication_reference','reader_reference'):
        item=parent[role];exact(a['source_hashes'].get(item['path']),item['sha256'])
    require(a['entire_history_independently_reconstructed']is True and a['publisher_called']is False and a['new_pure_called']is False and
        a['current_live_cache_read_or_reverified']is False,'Readback roles')
    require(type(h)is dict and set(HISTORY_KEYS)|set(legacy.WRAPPER_FALSE)<=set(h)and not(set(h)-set(HISTORY_KEYS)-OPTIONAL_FALSE),'Exact V5 history fields')
    flags(h,legacy.WRAPPER_FALSE);exact(h['policy_id'],POLICY);require(h['raw_source_bytes_embedded']is False,'No new raw bytes embedded')
    prior=h['prior_state_preserved'];require(type(prior)is dict and set(prior)==set(STATE_KEYS),'Fixed nonrecursive prior state')
    require(prior['parent_schema']in ('PROSPECTIVE_GAP_EXTENSION_HISTORY_V3',legacy.SCHEMA,SCHEMA),'True supported prior schema')
    require(type(prior['parent_references'])is dict and set(prior['parent_references'])==set(ROLES),'Prior four references')
    exact(h['parent_references'],prior['parent_references']);exact(h['parent_references'],d['input_references']['parent'])
    exact(h['capture_references'],d['input_references']['capture']);require(set(h['capture_references'])==set(ROLES),'Capture four references')
    exact(h['parent_state_reference'],h['parent_references']['reference']);check_state(prior,sources)
    for key in ('observations','parent_attempt_inventory','first_actual_observed_session_by_month','genesis_preserved','baseline_references','baseline_role','last_observed_session'):
        exact(h[key],prior[key],'Prior state preserved '+key)
    original=prior['known_typed_rows'];known=h['known_typed_rows'];exact(h['known_typed_rows_preserved'],original);exact(known[:len(original)],original)
    integer(h['parent_typed_row_count'],len(original));integer(h['parent_actual_observation_count'],prior['observation_count']);integer(h['new_observation_count'],0)
    added=known[len(original):];integer(h['new_missed_observation_count'],len(added))
    exact(h['status'],'GAP_EXTENSION_RESEARCH_ONLY'if added else'NO_EXPIRED_SESSION_TO_APPEND')
    state=dict(h,accounted_baseline_references=h['accounted_prefix_references'],accounted_baseline_role=legacy.ACCOUNTED_ROLE)
    check_state(state,sources)
    exact(h['full_capture_source_role'],FULL_CAPTURE_ROLE);exact(h['accounted_prefix_role'],PREFIX_ROLE)
    pair(h['full_capture_source_references']);pair(h['accounted_prefix_references']);pair(h['accounted_prefix_evidence']);pair(h['accounted_prefix_evidence_references']);pair(h['source_evidence'])
    begin,end=utc(h['capture_started_at']),utc(h['capture_completed_at']);require(begin<=end,'Capture clock order')
    prior_suffix=prior['pending_source_sessions']+prior['excluded_not_completed_source_sessions']
    if prior_suffix:
        require(begin>=max(utc(item['capture_completed_at_utc'])for item in prior_suffix),'Capture clock regressed behind previously captured suffix')
    original_dates=[row['session']for row in original];days=[row['session']for row in known]
    prior_full_dates=original_dates+[item['session']for item in prior['pending_source_sessions']+prior['excluded_not_completed_source_sessions']]
    categories=[h[key]for key in ('gap_classifications','pending_source_sessions','excluded_not_completed_source_sessions')]
    require(all(type(values)is list for values in categories),'Explicit complete classification lists')
    classifications=categories[0]+categories[1]+categories[2];new=sessions([item['session']for item in classifications]);suffix=new[len(added):]
    exact([row['session']for row in added],[item['session']for item in categories[0]]);require(len(categories[1])<=1,'At most one completed pending session')
    for index,item in enumerate(classifications):
        require(type(item)is dict and set(item)==set(CLASSIFICATION_KEYS),'Exact source-session classification')
        close,deadline=utc(item['conservative_close_utc']),utc(item['conservative_next_weekday_open_utc']);require(close<deadline,'Conservative timing order')
        exact(close.date().isoformat(),item['session']);following=date.fromisoformat(item['session'])+timedelta(days=1)
        while following.weekday()>4:following+=timedelta(days=1)
        exact(deadline.date().isoformat(),following.isoformat(),'Next weekday open date')
        exact(item['capture_started_at_utc'],h['capture_started_at']);exact(item['capture_completed_at_utc'],h['capture_completed_at'])
        exact(item['source_session_pointer_by_ticker'],{t:'/plan/source_evidence/'+t+'/new_session_dates/'+str(index)for t in ('QQQ','SPY')})
        for key in ('counts_as_observed_session','consumes_month_first_opportunity','decision_eligible'):require(item[key]is False,'No suffix/first-month consumption')
        expected='SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START'if begin<close else'MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE'if begin>=deadline and end>=deadline else'DEADLINE_NOT_PASSED_FOR_ENTIRE_CAPTURE_INTERVAL'
        exact(item['classification'],expected)
        category=0 if expected=='MISSED_CONSERVATIVE_NEXT_OPEN_DEADLINE'else 2 if expected=='SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START'else 1
        require(item in categories[category],'Correct timing partition')
    for index,row in enumerate(added):
        exact(row,dict(sequence=len(original)+index+1,session=new[index],kind='MISSED_OBSERVATION',seal_status='NOT_ATTEMPTED',
            evidence_reference=dict(h['capture_references']['reference'],json_pointer='/plan/source_evidence/QQQ/new_session_dates/'+str(index))))
    for ticker in ('QQQ','SPY'):
        source=h['source_evidence'][ticker];require(type(source)is dict and set(source)==set(SOURCE_EVIDENCE_KEYS),'Exact capture source evidence')
        exact(source['source_reference'],h['full_capture_source_references'][ticker]);exact(source['accounted_baseline_reference'],prior['accounted_baseline_references'][ticker])
        exact(source['actual_baseline_reference'],h['baseline_references'][ticker]);require(source['full_accounted_bytes_prefix_matches']is True,'Declared original baseline byte prefix')
        exact(source['new_session_dates'],new);exact(source['source_session_dates'],original_dates+new);exact(source['source_session_dates'],days+suffix)
        exact(source['source_session_dates'][:len(prior_full_dates)],prior_full_dates,'Previously captured source sessions cannot disappear')
        count=source['original_row_count'];require(type(count)is int and count>=len(days+suffix),'Full original row count')
        excluded=count-len(days+suffix);exact(source['excluded_original_row_indexes'],list(range(excluded)))
        exact(source['included_original_row_indexes'],list(range(excluded,count)))
        check_prefix(h['accounted_prefix_evidence'][ticker],h['full_capture_source_references'][ticker],h['accounted_prefix_references'][ticker],days,suffix,source)
        ref(h['accounted_prefix_evidence_references'][ticker],sources)
    exact(h['tzif_reference']['sha256'],prior['tzif_reference']['sha256'],'TZif hash continuity')
    exact(h['source_hashes'],h['source_reference_claims']);inner={};legacy.declarations(h,inner)
    for path,digest in inner.items():exact(h['source_hashes'].get(path),digest,'Pure declaration closure')
    exact(a['counts'],gap_counts(h))
    result=parent_state_for_gap(dict(state,parent_schema=SCHEMA,parent_references={role:deepcopy(parent[role])for role in ROLES},source_hashes=sources))
    result.update(schema=VIEW_SCHEMA,policy_id=POLICY,full_capture_source_references=deepcopy(h['full_capture_source_references']),
        full_capture_source_role=FULL_CAPTURE_ROLE,accounted_prefix_references=deepcopy(h['accounted_prefix_references']),
        accounted_prefix_evidence=deepcopy(h['accounted_prefix_evidence']),accounted_prefix_evidence_references=deepcopy(h['accounted_prefix_evidence_references']),accounted_prefix_role=PREFIX_ROLE,
        pending_source_sessions=deepcopy(h['pending_source_sessions']),excluded_not_completed_source_sessions=deepcopy(h['excluded_not_completed_source_sessions']),
        scope_and_complete_byte_prefix_require_independent_io_verification=True,
        legacy_checker_reference=dict(path=LEGACY_CHECKER_PATH,sha256=LEGACY_VIEW_SHA256),legacy_checker_called=False,**FLAGS)
    return result
