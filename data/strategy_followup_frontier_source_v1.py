"""Independent frontier archive source re-review and monthly exit replay."""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from datetime import datetime
import json
from core.strategy_account_ledger import require, canonical
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.monthly_peak_exit import advance_monthly_exit
from data.monthly_peak_exit_history import monthly_exit_observations
from data.strategy_advice_followup_plan_v3 import resolve_policy_binding, FRONTIER_POLICY
from data.strategy_followup_execution_binding_v1 import validate_execution_shape
from data.strategy_followup_price_basis_v2 import review_price_basis
from data.strategy_followup_historical_reader_v1 import read_historical_frontier_capture
from data.strategy_unified_server_preparation_v7 import _read


LEGACY_SOURCE_REVIEW = 'efc85a1b4d4282342a12bcbdbb19904e1c61b2ecef662ae3b4497dc0e9cd2df9'


SCOPED_SOURCE_REVIEW='cf523efbf215dffcbc4a7def9d84d4e6041cdc7bc67e2236fcabaec9859c1e4e'
SCOPED_LEAF='77658671f1b03d3d26295be50d2ab2dc4c58d8d51bbf3ea194c2c0ed6cf470fe'

def compare_source_review(original, current, historical_source_pin, historical_leaf_pin=None, historical_scope=None):
    def valid(value):
        body={key:item for key,item in value.items() if key!='review_id'}
        return value.get('review_id')==sha256(canonical(body)).hexdigest()
    require(valid(original) and valid(current),'FOLLOWUP_SOURCE_REVIEW_ID_INVALID')
    if original==current:return dict(mode='EXACT_CURRENT_INDEPENDENT_REVIEW',current_review_id=current['review_id'])
    if historical_source_pin==SCOPED_SOURCE_REVIEW:
        require(historical_leaf_pin==SCOPED_LEAF and isinstance(historical_scope,dict) and
                bool(historical_scope) and historical_scope==original.get('future_notice_scope') and
                set(historical_scope)==set(current.get('future_notice_scope',{})),
                'FOLLOWUP_HISTORICAL_SCOPE_NOT_REPRODUCED')
        projected=deepcopy(current);projected['future_notice_scope']=deepcopy(historical_scope)
        projected.pop('review_id');projected['review_id']=sha256(canonical(projected)).hexdigest()
        require(projected==original,'FOLLOWUP_FRONTIER_SOURCE_REVIEW_CHANGED')
        return dict(mode='HISTORICAL_LEAF_SCOPE_REPRODUCED_CURRENT_INDEPENDENT_SCOPE_RETAINED',
                    original_review_id=original['review_id'],current_review_id=current['review_id'],
                    historical_future_notice_scope=deepcopy(historical_scope),
                    current_future_notice_scope=deepcopy(current['future_notice_scope']),
                    historical_source_review_sha256=historical_source_pin,historical_leaf_sha256=historical_leaf_pin,
                    original_evidence_modified=False)
    require(historical_source_pin==LEGACY_SOURCE_REVIEW and 'future_notice_scope' not in original and
            set(current)==set(original)|{'future_notice_scope'} and isinstance(current['future_notice_scope'],dict),
            'FOLLOWUP_SOURCE_REVIEW_SCHEMA_UNSUPPORTED')
    projected={key:item for key,item in current.items() if key not in ('review_id','future_notice_scope')}
    projected['review_id']=sha256(canonical(projected)).hexdigest()
    require(projected==original,'FOLLOWUP_FRONTIER_SOURCE_REVIEW_CHANGED')
    return dict(mode='HISTORICAL_LEAF_CURRENT_REVIEW_EXPLICIT_LEGACY_SCHEMA_PROJECTION',
                original_review_id=original['review_id'],current_review_id=current['review_id'],
                added_future_notice_scope=deepcopy(current['future_notice_scope']),
                historical_source_review_sha256=historical_source_pin,original_evidence_modified=False)


def review_frontier_event(*, root, event, supplemental_directory=None):
    root=Path(root).resolve();response=event['response'];budget=0
    def read(path):
        nonlocal budget
        path=Path(path)
        if not path.is_absolute():path=root/path
        require(path.resolve().is_relative_to(root/'data/strategy_account') and
                not any(p.is_symlink() or (p.exists() and getattr(p.stat(),'st_file_attributes',0)&1024)
                        for p in (path,*path.parents)),'FOLLOWUP_CAP_SOURCE_PATH')
        require(path.stat().st_size<=32*1024*1024,'FOLLOWUP_CAP_SOURCE_SIZE')
        raw=path.read_bytes();budget+=len(raw)
        require(budget<=128*1024*1024,'FOLLOWUP_CAP_SOURCE_BUDGET')
        return raw
    def read_reference(path,digest):
        raw=read(path);require(sha256(raw).hexdigest()==digest,'FOLLOWUP_CAP_SOURCE_CHANGED')
        return json.loads(raw)
    def archive(reference):
        path=Path(reference['receipt_path']);receipt=read_reference(path,reference['receipt_sha256'])
        require(path.parent.name==reference['receipt_sha256'],'FOLLOWUP_CAP_ARCHIVE_LOCATION')
        manifest_raw=read(path.parent/'manifest.json');manifest=json.loads(manifest_raw)
        complete=json.loads(read(path.parent/'complete.json'))
        require(sha256(manifest_raw).hexdigest()==reference['manifest_sha256']==complete['manifest_sha256'] and
                manifest['receipt_sha256']==complete['receipt_sha256']==reference['receipt_sha256'] and
                manifest['source_sha256']==receipt['source_sha256'],'FOLLOWUP_CAP_ARCHIVE_INCOMPLETE')
        files={}
        require(0<len(receipt['source_sha256'])<=2000,'FOLLOWUP_CAP_SOURCE_COUNT')
        for name,pin in receipt['source_sha256'].items():
            require(type(pin)is str and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'FOLLOWUP_CAP_SOURCE_PIN')
            raw=read(path.parent/'sources'/(pin+'.bin'))
            require(sha256(raw).hexdigest()==pin,'FOLLOWUP_CAP_SOURCE_CHANGED');files[name]=raw
        require(receipt['account_id']==event['account_id'] and receipt['account_revision']==event['account_revision']
                and receipt['target_id']==event['target_id'],'FOLLOWUP_CAP_ARCHIVE_BINDING')
        return path,receipt,files
    policy, pin = resolve_policy_binding(event, root=root)
    require(policy == FRONTIER_POLICY, 'FOLLOWUP_FRONTIER_POLICY_REQUIRED')
    preparation_ref = event['policy_references'].get('frontier_preparation')
    require(type(preparation_ref) is dict, 'FOLLOWUP_FRONTIER_PREPARATION_REQUIRED')
    _, preparation = _read(root, preparation_ref)
    require(preparation.get('schema') == 'SAVED_FRONTIER_UNIFIED_PREPARATION_V27' and
        preparation['release'] == event['policy_references']['frontier_release'],
        'FOLLOWUP_FRONTIER_PREPARATION_BINDING')
    path, receipt, files = archive(response['evidence_archive'])
    require(receipt['policy_id'] == policy and receipt['proposal_id'] == response['proposal_id'],
            'FOLLOWUP_FRONTIER_RECEIPT_BINDING')
    def document(name):
        return json.loads(files['frontier/' + name + '.json'])
    require(sha256(files['frontier/release.json']).hexdigest() == pin == receipt['release_sha256'],
            'FOLLOWUP_FRONTIER_RELEASE_BINDING')
    proposal = document('proposal'); target = document('target'); state = document('account')
    require(proposal == build_frontier_proposal(target=target), 'FOLLOWUP_FRONTIER_PROPOSAL_CHANGED')
    require(proposal['proposal_id'] == response['proposal_id'] and target['target_id'] == event['target_id']
            and state['account_id'] == event['account_id'] and state['revision'] == event['account_revision'],
            'FOLLOWUP_FRONTIER_SNAPSHOT_BINDING')
    prepared = document('prepared'); previous = document('risk-before')
    require(prepared['proposal_id'] == proposal['proposal_id'] and
        prepared['risk_state_sha256'] == sha256(canonical(previous)).hexdigest(),
        'FOLLOWUP_FRONTIER_PREPARED_BINDING')
    capture = document('capture')
    capture['files'] = {name: files[name] for name in capture['source_hashes']}
    checked = read_historical_frontier_capture(root=root, preparation_reference=preparation_ref, archived_files=files, supplemental_directory=supplemental_directory, prepared=document('prepared'), capture=capture,
        state=state, target=target, proposal=proposal, risk_state=document('risk-before'),
        now=datetime.fromisoformat(receipt['valid_from']))
    source_review_comparison=compare_source_review(document('source-review'), checked['review'],
        checked['historical_provenance']['legacy_source_review_sha256'],
        checked['historical_provenance']['code_sha256']['data/saved_frontier_first_window_v1.py'],checked['historical_scope'])
    inputs = json.loads(files[receipt['normalized_inputs_path']])
    require(inputs == checked['review']['inputs'], 'FOLLOWUP_FRONTIER_INPUT_CHANGED')
    projection = document('risk-projection'); saved = projection['state']
    require(projection['policy_id'] == policy and projection['monthly_cap_view'] == dict(
        target_quantities=proposal['payload']['proposed_target_quantities'],
        base_target_id=target['target_id'], proposal_id=proposal['proposal_id']), 'FOLLOWUP_FRONTIER_VIEW_CHANGED')
    normalized = deepcopy(inputs)
    baseline = {sid: proposal['payload']['proposed_target_quantities'].get(sid, 0) for sid in inputs['histories']}
    normalized['base_target']['quantities'] = baseline
    observations = monthly_exit_observations(**normalized)
    replay = None; replay_state = None
    for row in observations:
        replay = advance_monthly_exit(state=replay_state, account_id=event['account_id'],
            decision_date=row['decision_date'], session_date=row['session_date'], closes=row['closes'],
            unit_ids=row['unit_ids'], baseline_targets=baseline)
        replay_state = replay['state']
    require(replay is not None and all(saved.get(key) == value for key, value in replay_state.items()),
            'FOLLOWUP_FRONTIER_REPLAY_CHANGED')
    require(replay['effective_target_quantities'] == projection['effective_target_quantities'] ==
            response['effective_target_quantities'] and replay['reasons'] == projection['reasons'],
            'FOLLOWUP_FRONTIER_EFFECTIVE_CHANGED')
    reference = response['execution_binding']; binding = read_reference(reference['path'], reference['sha256'])
    validate_execution_shape(binding, response)
    require(binding['account_revision'] == event['account_revision'] and
        binding['base_target_id'] == event['target_id'] == reference['base_target_id'] and
        binding['base_decision_id'] == reference['base_decision_id'] and
        binding['policy_id'] == policy and binding['effective_target_quantities'] == response['effective_target_quantities'],
        'FOLLOWUP_FRONTIER_EXECUTION_BINDING')
    require(binding['signal']['proposal_id'] == proposal['proposal_id'] and
        binding['signal']['evidence_archive'] == response['evidence_archive'] and
        binding['evidence_id'] == reference['evidence_id'] == response['evidence_archive']['receipt_sha256'],
        'FOLLOWUP_FRONTIER_EXECUTION_ARCHIVE')
    for order in response['new_orders']:
        require(order['proposal_id'] == proposal['proposal_id'] and order['source_target_id'] == target['target_id'],
                'FOLLOWUP_FRONTIER_ORDER_BINDING')
    return dict(status='FRONTIER_ARCHIVE_SOURCE_AND_REPLAY_CHECKED', policy_id=policy,
        proposal_id=proposal['proposal_id'], policy_release_sha256=pin,
        price_basis=review_price_basis(inputs, files, monthly=True),
        capture_admitted=False, account_writes=False, network_calls=0,
        historical_provenance=checked['historical_provenance'],source_review_comparison=source_review_comparison,current_independent_source_review=checked['review'])
