"""Server-owned, explicit-basis capture review. Conditional content, never source authentication.
No production caller installs this candidate automatically.
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical, require
from data.saved_frontier_policy_archive import read_saved_frontier_policy
from data.strategy_daily_session_capture import stamp
from docs.candidates.split_native_month_daily_20261105 import verify_native_units, validate_raw_schedule
from docs.candidates.split_frontier_supplement_20261105 import review_generation


def digest(raw): return sha256(raw).hexdigest()


class NativeCaptureReview:
    """Grant hash must come from server configuration, NOT the capture/browser.

    Grant files contain reviewed identities/calendar, exact basis permissions and
    normalized baseline prices. A hash proves binding, not vendor authenticity.
    Known provider dividends require exact authorization; their presence does not
    credit cash or certify settlement. Unresolved rights remain explicit.
    """
    def __init__(self, *, research_root, authorization_bytes, authorization_sha256, files):
        require(digest(authorization_bytes)==authorization_sha256,'CAPTURE_AUTH_HASH')
        grant=json.loads(authorization_bytes)
        require(grant['schema']=='NATIVE_CAPTURE_SOURCE_AUTHORIZATION_V1','CAPTURE_AUTH_SCHEMA')
        require(set(files)==set(grant['source_sha256']) and all(digest(v)==grant['source_sha256'][k] for k,v in files.items()),'CAPTURE_AUTH_FILES')
        self.root=research_root;self.raw=bytes(authorization_bytes);self.expected=authorization_sha256
        self.files={k:bytes(v) for k,v in files.items()}

    def __call__(self, *, capture, prepared, state, target, proposal, risk_state, now):
        require(digest(self.raw)==self.expected,'CAPTURE_AUTH_HASH')
        grant=json.loads(self.raw);files=dict(self.files)
        require(all(digest(v)==grant['source_sha256'][k] for k,v in files.items()),'CAPTURE_AUTH_FILES')
        require(grant['target_id']==target['target_id'] and grant['proposal_id']==proposal['proposal_id'],'CAPTURE_AUTH_TARGET')
        require(stamp(grant['reviewed_at'])<=stamp(now)<stamp(grant['valid_until']),'CAPTURE_AUTH_TIME')
        calendar=json.loads(files[grant['calendar']]);identity_raw=files[grant['identities']]
        identities=json.loads(identity_raw)['securities'];permissions=grant['securities']
        require(set(permissions)==set(identities)==set(prepared['request']['securities']),'CAPTURE_AUTH_DOMAIN')
        require(digest(canonical(calendar))==prepared['calendar_sha256'],'CAPTURE_AUTH_CALENDAR')
        review=dict(schema='SPLIT_NATIVE_MONTH_DAILY_REVIEW_V1',target_id=target['target_id'],proposal_id=proposal['proposal_id'],account_id=state['account_id'],account_revision=state['revision'],risk_state_sha256=digest(canonical(risk_state)),normalization_reviewed=True,unresolved_units=deepcopy(grant['unresolved_units']),pending_rights=deepcopy(grant['pending_rights']),review_scope='FULL_WINDOW_NATIVE_POST_SPLIT_UNITS',reviewed_at=stamp(now).isoformat(),monthly_decision_date=prepared['decision_date'],timing_bundles=grant['timing_bundles'])
        native=verify_native_units(state=state,target=target,archived=read_saved_frontier_policy(research_root=self.root,target_id=target['target_id']),review=review,now=stamp(now).isoformat())
        sessions=calendar['sessions'];index=next(i for i,r in enumerate(sessions) if r['date']==prepared['session']['date'])
        completed=sessions[:index];epoch=prepared['decision_date'];window=[r for r in completed if r['date']>=epoch]
        require(bool(window),'CAPTURE_AUTH_WINDOW')
        quantities=proposal['payload']['proposed_target_quantities'];histories={};normalizations={};rawpaths={};unitpaths={};received={};units={}
        for sid,permission in permissions.items():
            require(permission['price_basis'] in {'AS_TRADED','SPLIT_ADJUSTED_TO_CURRENT_UNIT'},'EXPLICIT_RAW_PRICE_BASIS_REQUIRED')
            require(stamp(permission['basis_asof'])<=stamp(grant['reviewed_at']),'CAPTURE_BASIS_FUTURE_AUTHORIZATION')
            receipt=json.loads(capture['files'][capture['documents']['action_receipts'][sid]])
            raw=capture['files'][receipt['raw_path']];received[sid]=receipt['received_at']
            require(stamp(grant['reviewed_at'])<=stamp(receipt['requested_through']) and stamp(permission['basis_asof'])<=stamp(received[sid]),'CAPTURE_BASIS_TIME')
            rawpath='generated/raw/'+sid;unitpath='generated/unit/'+sid
            require(rawpath not in files and unitpath not in files,'CAPTURE_GENERATED_COLLISION')
            files[rawpath]=raw;rawpaths[sid]=rawpath;unitpaths[sid]=unitpath;units[sid]=permission['current_unit_id']
            normalization=dict(security_id=sid,raw_sha256=digest(raw),review_reference=unitpath,price_basis=permission['price_basis'],basis_asof=permission['basis_asof'],captured_at=receipt['received_at'],current_unit_id=units[sid],split_schedule=deepcopy(permission['split_schedule']),reviewed_dividends=deepcopy(permission['reviewed_dividends']))
            unit=dict(schema='SPLIT_NATIVE_MONTH_UNIT_REVIEW_V1',security_id=sid,ticker=identities[sid]['ticker'],target_id=target['target_id'],proposal_id=proposal['proposal_id'],raw_sha256=digest(raw),identity_sha256=digest(identity_raw),currency='USD',basis_id=units[sid],price_basis=target['payload']['decision']['payload']['input_binding']['current_price_basis'],unresolved_units=deepcopy(grant['unresolved_units']),pending_rights=deepcopy(grant['pending_rights']),native_unit_proof_sha256=native['proof_sha256'],corporate_actions=deepcopy(permission['split_schedule']),raw_normalization=normalization,covered_from=window[0]['open'],covered_through=window[-1]['close'],reviewed_at=stamp(now).isoformat())
            validate_raw_schedule(sid=sid,raw=raw,normalization=normalization,unit=unit,native=native,epoch_open=window[0]['open'])
            files[unitpath]=canonical(unit);normalizations[sid]=normalization
            histories[sid]=dict(source_reference='sha256:'+digest(raw),units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',unit_asof=window[-1]['date'],currency='USD',basis_id=units[sid],review_reference=unitpath),closes=[])
        inputs=dict(base_target=dict(origin_reference=proposal['proposal_id'],monthly_decision_date=epoch,quantities={s:quantities.get(s,0) for s in identities},price_units=units),signal_date=window[-1]['date'],observed_at=stamp(now).isoformat(),session_dates=[r['date'] for r in completed],session_close_times=dict(review_reference=grant['calendar'],closes={r['date']:r['close'] for r in completed}),histories=histories)
        result=review_generation(capture=capture,request=prepared['request'],binding=prepared['binding'],inputs=inputs,identities=identities,reviews=normalizations,now=now)
        for sid,permission in permissions.items():
            baseline=json.loads(files[permission['baseline']]);actual=result['projections'][sid]['normalized_closes']
            require(baseline['security_id']==sid and baseline['unit_id']==units[sid],'CAPTURE_BASELINE_UNIT')
            require(bool(baseline['closes']) and all(d in inputs['session_close_times']['closes'] and stamp(inputs['session_close_times']['closes'][d])<=stamp(grant['reviewed_at']) and Fraction(v)>0 for d,v in baseline['closes'].items()),'CAPTURE_BASELINE_TIME_OR_PRICE')
            overlap=set(baseline['closes'])&set(actual)
            require(bool(overlap) and all(Fraction(baseline['closes'][d])==Fraction(actual[d]) for d in overlap),'CAPTURE_BASELINE_CONTINUITY')
        require('generated/inputs' not in files and 'authorization.json' not in files,'CAPTURE_GENERATED_COLLISION')
        files['generated/inputs']=canonical(result['inputs']);files['authorization.json']=self.raw
        for path,raw in capture['files'].items():
            require('capture/'+path not in files,'CAPTURE_GENERATED_COLLISION');files['capture/'+path]=raw
        review.update(source_received_by_security=received,source_received_at=max(received.values(),key=stamp),documents=dict(calendar=grant['calendar'],identities=grant['identities'],normalized_inputs='generated/inputs',raw_by_security=rawpaths,unit_reviews=unitpaths),source_sha256={k:digest(v) for k,v in files.items()})
        return dict(review_bytes=canonical(review),trusted_review_sha256=digest(canonical(review)),files=files)
