"""Small JSON replay adapter for new-cash current-dollar-allocation proposals.

Current execution/identity/review bytes are frozen. Historical source bytes are
not duplicated; the complete original decision and historical pins are retained.
This is local reproducibility, not external source or timestamp authentication.
"""
import base64
from copy import deepcopy
from hashlib import sha256
from data.current_quantity_v2_current_cash_plan import (
    SCOPE,canonical,parse,require,rebuild_current_cash_plan,_build_current_cash_plan)

SCHEMA='V2_CURRENT_CASH_LEDGER_PROPOSAL_V1'
MAX_BYTES=16*1024*1024


def freeze_current_cash_proposal(plan,execution_package):
    original=rebuild_current_cash_plan(plan,execution_package)
    require(original['status']=='READY','READY_CURRENT_CASH_PLAN_REQUIRED')
    b=original['pinned_inputs'];files=execution_package['files'];docs=b['documents']
    # Every nonhistorical file plus any historical file used by current evidence.
    needed=set(files)-set(b['capital_decision']['binding']['source_hashes'])
    needed.update((docs['identities'],docs['current_unit_reviews']))
    if 'pullback_policy' in docs:
        needed.add(docs['pullback_policy'])
        needed.update(docs['pullback_proofs'].values())
    if 'execution_month_mandate' in docs:
        needed.add(docs['execution_month_mandate'])
        needed.update(parse(files[docs['execution_month_mandate']])['source_hashes'])
    needed.update(b['genesis_declaration']['source_references'])
    for collection in (b['current_identities'],b['current_unit_reviews']):
        for row in collection.values():needed.update(row['source_references'])
    for receiptpath in docs['quote_receipts'].values():
        needed.add(receiptpath);needed.add(parse(files[receiptpath])['raw_path'])
    require(sum(len(files[p]) for p in needed)<=MAX_BYTES,'FROZEN_EXECUTION_BYTES_LIMIT')
    frozen=dict(documents=deepcopy(docs),source_hashes=deepcopy(b['source_hashes']),
        files_base64={p:base64.b64encode(files[p]).decode('ascii') for p in sorted(needed)})
    return build_recorded_cash_proposal(capital_decision=deepcopy(b['capital_decision']),
        account_state=deepcopy(b['account_state']),genesis_declaration=deepcopy(b['genesis_declaration']),
        frozen_execution_package=frozen,now=b['created_at'],target_scope=SCOPE)


def build_recorded_cash_proposal(*,capital_decision,account_state,genesis_declaration,
        frozen_execution_package,now,target_scope):
    require(target_scope==SCOPE,'CURRENT_CASH_SCOPE_REQUIRED')
    f=frozen_execution_package
    require(type(f)is dict and set(f)=={'documents','source_hashes','files_base64'},'FROZEN_PACKAGE_FIELDS')
    require(type(f['files_base64'])is dict and len(f['files_base64'])<=2000,'FROZEN_PACKAGE_LIMIT')
    require(all(type(v)is str for v in f['files_base64'].values())
            and sum(len(v) for v in f['files_base64'].values())<=MAX_BYTES*4//3+8192,'FROZEN_EXECUTION_BYTES_LIMIT')
    files={}
    for p,value in f['files_base64'].items():
        raw=base64.b64decode(value,validate=True)
        require(base64.b64encode(raw).decode('ascii')==value,'CANONICAL_BASE64_REQUIRED');files[p]=raw
    require(sum(map(len,files.values()))<=MAX_BYTES,'FROZEN_EXECUTION_BYTES_LIMIT')
    package=dict(files=files,source_hashes=f['source_hashes'],documents=f['documents'])
    plan=_build_current_cash_plan(capital_decision=capital_decision,account_state=account_state,
        genesis_declaration=genesis_declaration,execution_package=package,now=now,recorded_historical_manifest=True)
    require(plan['status']=='READY',plan.get('reason','CURRENT_CASH_REPLAY_FAILED'))
    causal=dict(capital_decision=deepcopy(capital_decision),account_state=deepcopy(account_state),
        genesis_declaration=deepcopy(genesis_declaration),frozen_execution_package=deepcopy(f),now=now,target_scope=target_scope)
    identifier=sha256(canonical(dict(schema=SCHEMA,causal_inputs=causal))).hexdigest()
    return dict(schema=SCHEMA,status='READY',target_scope=SCOPE,proposal_id=identifier,causal_inputs=causal,
        execution_target_id=plan['execution_target_id'],account_id=plan['account_id'],
        capital_decision_id=plan['capital_decision_id'],research_id=plan['research_id'],
        target_quantities=deepcopy(plan['execution_target_quantities']),
        historical_target_quantities=deepcopy(capital_decision['target_quantities']),
        securities=deepcopy(plan['pinned_inputs']['current_identities']),orders=deepcopy(plan['orders']),
        execution_references={r['security_id']:deepcopy(r['reference']) for r in plan['rows']},rows=deepcopy(plan['rows']),
        actual_cash=plan['initial_cash'],original_residual_cash=plan['original_residual_cash'],
        remaining_cash=plan['remaining_cash'],reserved_buy_cash=plan['indicative_notional'],
        reference_valid_until=plan['reference_valid_until'],target_month=genesis_declaration['target_month'],
        research_only=True,execution_blocked=True,orders_created=False,real_account=False,
        source_authenticated=False,source_bytes_verified=False,current_execution_bytes_verified=True,
        historical_source_bytes_reverified=False,subsequent_activation_supported=False)
