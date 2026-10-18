"""First actual observed-session coordinates; missed dates do not consume them.

This is a policy projection of caller-labelled evidence, not a verifier of
timeliness or an authorization to seal. Failed seals remain in the sequence.
"""
from copy import deepcopy
from datetime import date

POLICY_ID = 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
SCHEMA = 'GAP_MONTHLY_OBSERVATION_POLICY_RESEARCH_V1'
KINDS = {'SEALED_PARENT_OBSERVED_SESSION', 'MISSED_OBSERVATION', 'PROSPECTIVE_OBSERVED_SESSION'}
MAX_ROWS = 20000


def require(value, message):
    if not value:
        raise ValueError(message)


def monthly_observation_coordinates(*, policy_id, known_rows, new_prospective_observations):
    require(policy_id == POLICY_ID and type(policy_id) is str, 'Explicit supported policy required')
    require(type(known_rows) is list and type(new_prospective_observations) is list and
            0 < len(known_rows)+len(new_prospective_observations) <= MAX_ROWS, 'Complete bounded typed sequence required')
    rows = known_rows + new_prospective_observations
    previous = ''; pointers = set(); months = {}; result = []
    for index, row in enumerate(rows):
        require(type(row) is dict and set(row) == {'sequence','session','kind','evidence_reference','seal_status'}, 'Typed row schema')
        require(type(row['sequence']) is int and row['sequence'] == index+1, 'Complete consecutive sequence required')
        session = row['session']
        require(type(session) is str, 'Date string required')
        parsed = date.fromisoformat(session)
        require(parsed.isoformat() == session and parsed.weekday() < 5 and session > previous, 'Unique ascending weekday sequence required')
        previous = session
        require(type(row['kind']) is str and row['kind'] in KINDS, 'Explicit observation type required')
        if index >= len(known_rows):
            require(row['kind'] == 'PROSPECTIVE_OBSERVED_SESSION', 'New observations require prospective observed evidence')
        require(type(row['seal_status']) is str and row['seal_status'] in {'UNKNOWN','NOT_ATTEMPTED','FAILED','SEALED'}, 'Seal status required')
        gap = row['kind'] == 'MISSED_OBSERVATION'
        require(not gap or row['seal_status'] == 'NOT_ATTEMPTED', 'Missed observation cannot have a seal attempt')
        ref = row['evidence_reference']
        require(type(ref) is dict and set(ref) == {'path','sha256','json_pointer'}, 'Evidence reference schema')
        require(type(ref['path']) is str and bool(ref['path'].strip()), 'Evidence path required')
        require(type(ref['sha256']) is str and len(ref['sha256']) == 64 and
                all(c in '0123456789abcdef' for c in ref['sha256']), 'Evidence SHA required')
        pointer = ref['json_pointer']
        require(type(pointer) is str and pointer.startswith('/') and len(pointer) > 1,
                'Explicit evidence row pointer required')
        require(all(part.replace('~0','').replace('~1','').find('~') < 0 for part in pointer.split('/')[1:]), 'Invalid JSON pointer escape')
        identity = (ref['path'], ref['sha256'], pointer)
        require(identity not in pointers, 'Duplicate evidence row pointer')
        pointers.add(identity)
        month = session[:7]
        summary = months.setdefault(month, {'month':month,'first_observed_session':None,
                                            'observed_count':0,'missed_count':0})
        eligible = not gap and summary['first_observed_session'] is None
        if gap:
            summary['missed_count'] += 1
        else:
            summary['observed_count'] += 1
            if eligible: summary['first_observed_session'] = session
        result.append({'input_row':deepcopy(row),'monthly_coordinate_eligible':eligible,
            'month_first_observed_session_as_of_row':summary['first_observed_session'],
            'seal_outcome_used_to_select_coordinate':False,
            'candidate_seal_allowed':False,'cohort_registration_allowed':False})
    return {'schema':SCHEMA,'policy_id':policy_id,'rows':result,'months':list(months.values()),
        'known_row_count':len(known_rows),'new_prospective_observation_count':len(new_prospective_observations),
        'scope':'POLICY_COORDINATES_FROM_CALLER_TYPED_SEQUENCE_NOT_TIMELINESS_OR_SEAL_AUTHORIZATION',
        'caller_source_evidence_not_verified':True,'complete_sequence_independently_verified':False,
        'input_timeliness_verified':False,'user_choice_authenticity_verified':False,
        'candidate_seal_allowed':False,'cohort_registration_allowed':False,'point_in_time_verified':False,
        'promotion_allowed':False,'live_mutation_allowed':False,'oos_recovery_completed':False}
