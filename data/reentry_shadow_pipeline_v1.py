"""Unrouted shadow orchestration. Only the explicitly isolated risk DB may change.

The authority verifier is server-owned executable code, not a browser boolean or
hash. No production verifier/activation/capture routing is supplied here. A missing
verifier returns WAIT without advancing risk. Conditional provider evidence cannot
manufacture a DISJOINT historical identity proof.
"""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
from core.strategy_account_ledger import canonical, require
from core.reentry_buy_scope_v1 import digest
from data.strategy_account_session_snapshot_v1 import account_session_snapshot
from data.reentry_reference_evidence_v1 import review_reference_interval
from data.reentry_preview_projection_v1 import project_reference_preview
from data.reentry_publication_guard_v1 import seal_projection,check_publication


def run_shadow_pipeline(*, root, shadow_directory, risk_store, account_store,
                        account, original_preview, decision_session, now,
                        source_configurations, authority_verifier=None,
                        binding_reader=None, configuration_reader=None, clock_reader=None):
    """authority_verifier returns authenticated advance/decisions for this call.

    This function never activates a store. The caller must prepare an isolated
    activated copy. Path containment is a consistency check, not proof that a
    caller-selected directory is non-production; deployment authority must ensure
    actual isolation. Account journal access is read-only. final binding_reader is
    server-owned and returns the current account/target/proposal binding.
    """
    base = dict(schema='REENTRY_SHADOW_PIPELINE_V1', executable=False,
                orders_created=False, account_mutated=False, production_connected=False)
    def wait(reason, **extra):
        return dict(base, status='WAIT', reason=reason, candidate_orders=[],
                    original_sell_policy='PRESERVE_ONLY_AFTER_ORIGINAL_GATES', **extra)
    if not callable(authority_verifier):return wait('WAIT_DECISION_AUTHORITY_UNIMPLEMENTED')
    if not callable(binding_reader):return wait('WAIT_FINAL_BINDING_AUTHORITY_UNIMPLEMENTED')
    if clock_reader is None:clock_reader=lambda:datetime.now(timezone.utc).isoformat()
    if not callable(configuration_reader) or not callable(clock_reader):return wait('WAIT_CONFIGURATION_CLOCK_AUTHORITY_UNIMPLEMENTED')
    configuration_hash=configuration_reader()
    directory=Path(shadow_directory).resolve();risk_path=Path(risk_store.path).resolve()
    require(directory != Path(root).resolve() and directory in risk_path.parents,
            'SHADOW_RISK_DATABASE_OUTSIDE_ISOLATION')
    require(risk_path != Path(account_store.path).resolve(),'SHADOW_ACCOUNT_DATABASE_REFUSED')
    binding=dict(account_id=account['account_id'], account_revision=account['revision'],
                 target_id=original_preview['target_id'], proposal_id=original_preview['proposal_id'])
    if binding_reader()!=binding:return wait('SHADOW_INITIAL_BINDING_CHANGED')
    old=risk_store.read_reference(account['account_id'])
    if old is None:return wait('WAIT_EXPLICIT_SHADOW_ACTIVATION')
    verified=authority_verifier(account=deepcopy(account), original_preview=deepcopy(original_preview),
                                decision_session=decision_session, now=now)
    if verified is None:return wait('WAIT_DECISION_AUTHORITY_UNPROVEN')
    # The callable must authenticate the original price packet, exchange calendar,
    # identity units and archived intent; these are not inferred from snapshots.
    advance=deepcopy(verified['advance']);contexts={};snapshot_audit=[]
    require(advance['account_id']==account['account_id'] and
            advance['expected_reference_version']==old['version'] and
            advance['observations'][-1]['session_date']==decision_session,
            'SHADOW_AUTHORITY_BINDING')
    for observation in advance['observations']:
        day=observation['session_date'];decision=verified['decisions'][day]
        raw=decision['decision_evidence'];require(type(raw) is bytes,'SHADOW_DECISION_BYTES')
        snapshot=account_session_snapshot(account_store,account_id=account['account_id'],
            session_date=day,expected_latest_revision=account['revision'],
            decision_evidence=raw,decision_evidence_sha256=sha256(raw).hexdigest(),
            security_ids=tuple(observation['closes']))
        snapshot_audit.append(snapshot)
        if snapshot['status']!='JOURNAL_PREFIX_VERIFIED_UNITS_NOT_CERTIFIED':
            return wait(snapshot.get('reason','WAIT_SNAPSHOT'),snapshots=snapshot_audit)
        require(decision['unit_ids']==observation['unit_ids'],'SHADOW_UNIT_AUTHORITY_CHANGED')
        holdings=dict(session_date=day,account_id=account['account_id'],
            account_revision=snapshot['account_revision'],shares=snapshot['shares'],
            unit_ids=decision['unit_ids'],evidence_sha256=snapshot['evidence_sha256'],
            event_boundary_sha256=snapshot['event_boundary_sha256'])
        contexts[day]=dict(completed_at=snapshot['session_close_at'],holdings=holdings)
    source_reviews={};recoveries=[]
    for origin,lock in old['locks'].items():
        config=source_configurations.get(origin)
        if config is None:continue
        reviewed=review_reference_interval(root=Path(root),configuration_reference=config,
            lock=lock,decision_session=decision_session,as_of=now)
        source_reviews[origin]=reviewed
        if reviewed['status']=='REFERENCE_SOURCE_REVIEWED_CONDITIONAL':
            recoveries.append(reviewed['evidence'])
    if binding_reader()!=binding:return wait('SHADOW_BINDING_CHANGED_BEFORE_COMMIT')
    advance.update(session_contexts=contexts,recovery_evidence=recoveries)
    advanced=risk_store.advance(**advance)
    if {s:q for s,q in advanced['effective_target_quantities'].items() if q} != {s:q for s,q in original_preview['effective_target_quantities'].items() if q}:
        return wait('WAIT_FRESH_ORIGINAL_RISK_PREVIEW',shadow_risk_committed=True)
    state=risk_store.read_reference(account['account_id']);state_hash=digest(state)
    buys=sorted(s for s,q in original_preview['effective_target_quantities'].items()
                if q>account['shares'].get(s,0));proofs=[]
    for origin,lock in state['locks'].items():
        reviewed=source_reviews.get(origin,{})
        if reviewed.get('status')!='REFERENCE_SOURCE_REVIEWED_CONDITIONAL':continue
        sid=reviewed['current_security_id']
        # A non-overlap in today's ticker does not certify the entire successor
        # identity universe. Leave it unresolved rather than fabricate DISJOINT.
        if sid not in buys:continue
        require(lock['verified_through']==decision_session and lock['current_security_id']==sid,
                'SHADOW_REFERENCE_COMMIT_CHANGED')
        proofs.append(dict(origin_security_id=origin,reference_version=state['version'],
            reference_state_sha256=state_hash,original_binding=binding,
            decision_session=decision_session,buy_security_ids=buys,
            status='INTERSECTS_BUY_SCOPE',current_security_ids=[sid],
            identity_evidence_sha256=reviewed['identity_evidence_sha256'],price_status='LOCKED',
            price_completed_through=decision_session,
            price_evidence_sha256=reviewed['evidence']['evidence_sha256']))
    projected=project_reference_preview(account=account,original_preview=original_preview,
        reference_state=state,decision_session=decision_session,scope_proofs=proofs,now=now)
    seal=seal_projection(projection=projected,configuration_sha256=configuration_hash)
    try:
        publication=check_publication(projection=projected,seal=seal,current_binding=binding_reader(),
            current_reference_state=risk_store.read_reference(account['account_id']),
            current_configuration_sha256=configuration_reader(),now=clock_reader())
    except ValueError as error:
        return wait(str(error),shadow_risk_committed=True)
    return dict(base,status='SHADOW_CHECKED',projection=projected,publication_seal=seal,publication_check=publication,
                candidate_orders=deepcopy(projected['candidate_orders']),
                original_sell_orders_preserved=projected['original_sell_orders_preserved'],
                source_reviews=source_reviews,snapshots=snapshot_audit,
                shadow_risk_committed=True,reference_state_sha256=state_hash,
                limitations=['Server decision authority remains an external required implementation.',
                'Source coverage is conditional, not exhaustive historical identity certification.',
                'No production routing, activation, network capture or order submission.'])
