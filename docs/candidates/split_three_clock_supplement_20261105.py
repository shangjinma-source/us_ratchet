"""Unactivated three-clock supplement; actual capture checks reused unchanged.
Parent raw bytes stay in their original unit; only derived history is projected.
"""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
from hashlib import sha256
import json
from docs.candidates.split_frontier_supplement_20261105 import review_generation, prepare_request

def review_pair(*, parent, current, identities, action, timing, trusted_pair_sha256, now):
    """Each generation has its own receipt/basis. Projection is explicitly later."""
    from core.strategy_account_ledger import canonical,require
    from docs.candidates.split_three_clock_coordinates_20261105 import project_history_units, review_timing
    descriptor={key:{k:v for k,v in generation.items() if k!='capture'}|dict(capture={k:v for k,v in generation['capture'].items() if k!='files'}) for key,generation in [('parent',parent),('current',current)]}
    descriptor['action']=action
    descriptor['timing']=timing
    clocks=review_timing(action=action,timing=timing,now=now)
    require(sha256(canonical(descriptor)).hexdigest()==trusted_pair_sha256,'SPLIT_PAIR_REVIEW_HASH')
    old=review_generation(**parent,identities=identities,now=parent['capture']['finished_at'])
    new=review_generation(**current,identities=identities,now=now)
    require(parent['binding']['account_id']==current['binding']['account_id'] and parent['binding']['target_id']==current['binding']['target_id'],'SPLIT_PAIR_ACCOUNT_TARGET')
    require(parent['inputs']['base_target']['monthly_decision_date']==current['inputs']['base_target']['monthly_decision_date'],'SPLIT_PAIR_EPOCH')
    require(datetime.fromisoformat(parent['capture']['finished_at'])<datetime.fromisoformat(current['capture']['finished_at']),'SPLIT_PAIR_CLOCK_ORDER')
    boundary=datetime.fromisoformat(clocks['quote_bar_boundary_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    # Distribution does not change the source's historical quote coordinate.
    # A parent collected after D but before Q may still legitimately use old units.
    parent_review=parent['reviews'][action['security_id']]
    require(parent_review['current_unit_id']==action['old_unit_id'] and
        datetime.fromisoformat(parent_review['basis_asof'])<datetime.fromisoformat(clocks['quote_unit_effective_at']) and
        all(row['session_date']<boundary for row in old['observations']), 'SPLIT_PARENT_OLD_QUOTE_COORDINATE')
    # No future action is inserted into the old raw review or receipt.
    projected=project_history_units(observations=old['observations'],action=action,expected_sessions=[r['session_date'] for r in old['observations']],timing=timing)
    oldrows={r['session_date']:r for r in projected['payload']['normalized_observations']};newrows={r['session_date']:r for r in new['observations']}
    overlap=sorted(set(oldrows)&set(newrows));require(overlap and set(oldrows)<=set(newrows),'SPLIT_PAIR_OVERLAP_MISSING')
    for day in overlap:
        require(oldrows[day]['unit_ids']==newrows[day]['unit_ids'] and oldrows[day]['closes']==newrows[day]['closes'],'SPLIT_PAIR_PRICE_CONTINUITY')
    return dict(parent=old,current=new,history_projection=projected,overlap_dates=overlap,source_authenticated=False)


def apply_capture_pair(*, parent, current, trusted_pair_sha256, reader_arguments, read_binding, now):
    """Use reviewed transport bytes as the actual daily-reader source, then risk."""
    from core.strategy_account_ledger import canonical,require
    from docs.candidates.split_three_clock_daily_evidence_20261105 import project_split_frontier_daily
    args=deepcopy(reader_arguments);state=args['state'];review=json.loads(args['review_bytes']);files=args['files']
    identities=json.loads(files[review['documents']['identities']])['securities']
    from contextlib import closing
    import sqlite3
    from docs.candidates.split_three_clock_daily_evidence_20261105 import verify_transition_ancestry
    from data.saved_frontier_policy_archive import read_saved_frontier_policy
    with closing(sqlite3.connect(args['risk_path'].as_uri()+'?mode=ro',uri=True)) as con:
        raw,digest=con.execute('SELECT payload,digest FROM split_preparation WHERE singleton=1').fetchone()
    require(sha256(raw.encode()).hexdigest()==digest,'SPLIT_PREPARATION_CHANGED')
    prep=json.loads(raw);transition=prep['transition'];archive=read_saved_frontier_policy(research_root=args['research_root'],target_id=args['target_id'])
    verify_transition_ancestry(state=state,transition=transition,risk_before=prep['original_risk_state'],target=archive['target'],proposal_id=archive['proposal']['proposal_id'])
    from data.monthly_peak_exit_store import MonthlyPeakExitStore
    current_risk=MonthlyPeakExitStore(args['risk_path']).read(state['account_id'])
    planned=prepare_request(state=state,target=archive['target'],proposal=archive['proposal'],risk_state=current_risk,
        calendar=json.loads(files[review['documents']['calendar']]),identities=identities,now=now)
    require(current['request']==planned['request'] and current['binding']==planned['binding'],'SPLIT_CURRENT_REQUEST_CHANGED')
    matches=[r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED' and r['payload']['action_id']==transition['payload']['action_id']]
    require(len(matches)==1,'SPLIT_CAPTURE_ACTION_REQUIRED');action=matches[0]
    require(read_binding()==current['binding'] and state['revision']==current['binding']['account_revision'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    checked=review_pair(parent=parent,current=current,identities=identities,action=action,timing=transition['payload']['timing_bundle'],trusted_pair_sha256=trusted_pair_sha256,now=now)
    # Reader's separately trusted review must already bind the exact received raw,
    # normalization and clock. Never mint source approval from a successful fetch.
    received_map={}
    for sid,path in current['capture']['documents']['action_receipts'].items():
        receipt=json.loads(current['capture']['files'][path]);raw=current['capture']['files'][receipt['raw_path']]
        require(files[review['documents']['raw_by_security'][sid]]==raw,'SPLIT_CAPTURE_READER_RAW_MISMATCH')
        unit=json.loads(files[review['documents']['unit_reviews'][sid]])
        require(unit['raw_normalization']==current['reviews'][sid],'SPLIT_CAPTURE_READER_REVIEW_MISMATCH')
        received_map[sid]=receipt['received_at']
    require(review.get('source_received_by_security')==received_map and review['source_received_at']==max(received_map.values(),key=datetime.fromisoformat),'SPLIT_CAPTURE_RECEIVED_SUMMARY')
    require(json.loads(files[review['documents']['normalized_inputs']])==checked['current']['inputs'],'SPLIT_CAPTURE_READER_INPUT_MISMATCH')
    require(read_binding()==current['binding'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    result=project_split_frontier_daily(**dict(args,now=now))
    require(read_binding()==current['binding'],'SUPPLEMENT_SNAPSHOT_CHANGED')
    return dict(result,supplement_pair=checked,capture_id=current['capture']['capture_id'],automatic_source_approval=False,review_binding=planned['review_binding'])
