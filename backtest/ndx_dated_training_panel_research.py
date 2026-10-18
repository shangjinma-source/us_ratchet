"""Dated conditional training payload, with future-window evidence segregated."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math

SCHEMA='DATED_CONDITIONAL_TRAINING_PANEL_V1'
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
FLAGS=dict.fromkeys(('point_in_time_verified','execution_authorized','promotion_allowed','legal_training_input_admitted','fit_performed','historical_identity_verified','historical_risk_verified','liquidity_qualification_at_training_cutoff_verified','provider_binding_verified','complete_corporate_actions_verified','identity_interval_extended','future_independent_oos','untouched_holdout','evaluation_values_in_fit_payload','old_task_weights_reused','historical_pool_eligibility_verified','source_bytes_authenticated'),False)


def require(ok,message):
    if not ok:raise ValueError(message)


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):return hashlib.sha256(encode(value)).hexdigest()


def exact(a,b,message):require(encode(a)==encode(b),message)


def reference(r):
    require(type(r) is dict and set(r)=={'path','sha256'},'Exact external reference required')
    require(type(r['path']) is str and bool(r['path']),'Reference path')
    s=r['sha256'];require(type(s) is str and len(s)==64 and all(c in '0123456789abcdef' for c in s),'Reference SHA')


def prepare_dated_training_panel(*,channels_document,channels_reference,independent_readback_reference,parent_panel_reference):
    for r in (channels_reference,independent_readback_reference,parent_panel_reference):reference(r)
    source=channels_document
    require(source['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1','New long-window source schema')
    for k in ('point_in_time_verified','execution_authorized','promotion_allowed','legal_training_input_admitted','fit_performed','historical_identity_verified','historical_risk_verified','identity_interval_extended'):require(source[k] is False,'Source authority upgraded: '+k)
    for k,v in dict(security_count=77,issuer_count=76,observed_security_count=101,conditional_numeric_channel_count=77,blocked_price_channel_count=0).items():require(type(source[k]) is int and source[k]==v,'Full denominator differs')
    calendar=source['calendar253'];require(type(calendar) is list and len(calendar)==253 and calendar==sorted(set(calendar)),'Full fixed calendar')
    require(all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in calendar),'Canonical observed dates')
    require(calendar[0]=='2025-09-18' and calendar[126]=='2026-03-20' and calendar[127]=='2026-03-23' and calendar[-1]=='2026-09-21','Dated train/evaluation split')
    require(source['training_freeze_close_date']==calendar[126] and source['evaluation_first_return_date']==calendar[127],'Source freeze date')
    require(source['evaluation_interval_previously_used_for_fitting'] is True and source['future_independent_oos'] is False and source['untouched_holdout'] is False,'Prior consumption limits must survive')
    exact(source['input_references']['panel'],parent_panel_reference,'Original panel reference')
    exact(source['original_identity_assumed_window'],dict(first='2026-03-20',last='2026-09-21'),'Original identity window cannot expand')
    gaps=source['original_provenance_and_missing'];require(type(gaps) is list and len(gaps)==101 and len({r['ticker'] for r in gaps})==101,'Full101 original provenance')
    require(set(source['preserved_evidence_sidecars'])==set(SIDECARS) and set(source['preserved_sidecar_references'])==set(SIDECARS),'All seven evidence layers')
    for name in SIDECARS:exact(source['preserved_sidecar_references'][name],dict(parent_panel_reference,json_pointer='/'+name),'Sidecar pointer')
    rows=source['rows'];require(type(rows) is list and len(rows)==77,'All77 channel rows')
    coordinates=[r['coordinate'] for r in rows]
    for c in coordinates:require(all(type(c.get(k)) is str and c[k] for k in ('security_id','ticker','issuer_id','risk_chain')),'Full conditional coordinate')
    require(len({c['security_id'] for c in coordinates})==77 and len({c['ticker'] for c in coordinates})==77 and len({c['issuer_id'] for c in coordinates})==76,'Unique SID/ticker, issuer class separation')
    require({c['ticker'] for c in coordinates}<={r['ticker'] for r in gaps},'All typed tickers represented in101')
    values={};conversion=[];evaluation=[];selected={}
    for i,row in enumerate(rows):
        c=row['coordinate'];channel=row['channel'];ticker=c['ticker'];sid=c['security_id']
        require(channel['schema']=='BULK_LONG_WINDOW_CONDITIONAL_CHANNEL_V1' and channel['ticker']==ticker and channel['status']=='CONDITIONAL_NUMERIC_RESULT' and channel['reasons']==[],'Only complete new conditional channel')
        for k in ('source_bytes_authenticated','provider_price_unit_verified','identity_interval_verified','point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed'):require(channel[k] is False,'No channel certification')
        exact(channel['calendar'],calendar,'Channel calendar');exact(row['original_identity_assumed_window'],source['original_identity_assumed_window'],'Preserved identity interval')
        require(channel['training_freeze_close_date']==calendar[126] and channel['evaluation_initial_close_date']==calendar[126],'Shared close predecessor')
        train=channel['training_returns'];ev=channel['evaluation_returns'];require(type(train) is list and len(train)==126 and type(ev) is list and len(ev)==126,'Separate126 partitions')
        exact(channel['return_rows'],train+ev,'Original complete return partition')
        require(digest(train)==channel['training_returns_sha256'] and digest(ev)==channel['evaluation_returns_sha256'],'Saved partition checksums')
        vals=[];evidence=[]
        for j,item in enumerate(train):
            require(item['previous_session']==calendar[j] and item['session']==calendar[j+1] and item['dividends_included'] is False,'Training predecessor/date')
            literal=item['split_only_return_exact'];require(type(literal) is str and 0<len(literal)<=1024,'Bounded exact return string')
            try:r=Fraction(literal)
            except (ValueError,ZeroDivisionError):raise ValueError('Canonical rational return required') from None
            require(str(r)==literal and r>-1,'Canonical finite split-only return')
            value=item['split_only_return_float'];require(type(value) is float and math.isfinite(value) and value>-1 and value==float(r),'Exact-to-float boundary differs')
            vals.append(value);evidence.append(dict(session=item['session'],source_reference=dict(channels_reference,json_pointer=f'/rows/{i}/channel/training_returns/{j}'),exact_return=literal,float_hex=value.hex()))
        # Evaluation numerical values stay only in the sealed parent. Here we
        # bind their dates and saved digest, without creating a second fit frame.
        for j,item in enumerate(ev):require(item['previous_session']==calendar[126+j] and item['session']==calendar[127+j] and item['dividends_included'] is False,'Evaluation dates only')
        values[ticker]=vals;selected[sid]={k:c[k] for k in ('ticker','issuer_id','risk_chain')}
        conversion.append(dict(security_id=sid,ticker=ticker,rows=evidence))
        evaluation.append(dict(security_id=sid,ticker=ticker,reference=dict(channels_reference,json_pointer=f'/rows/{i}/channel/evaluation_returns'),saved_payload_sha256=channel['evaluation_returns_sha256'],previous_close_date=calendar[126],return_end_dates=deepcopy(calendar[127:])))
    tickers=sorted(values);sids=sorted(selected)
    frame=dict(type='DataFrame',index_type='DatetimeIndex',index=[d+'T00:00:00' for d in calendar[1:127]],columns=tickers,dtypes=['float64']*77,data=[[values[t][i] for t in tickers] for i in range(126)])
    payload=dict(cutoff=calendar[126],returns=frame,selected_by_security={sid:selected[sid] for sid in sids})
    result=dict(schema=SCHEMA,status='CONDITIONAL_DATED_TRAINING_PAYLOAD_ONLY_NOT_FITTED',fit_payload=payload,training_price_predecessor=calendar[0],training_return_count=126,security_count=77,issuer_count=76,observed_security_count=101,
        input_references=dict(channels=deepcopy(channels_reference),independent_readback=deepcopy(independent_readback_reference),parent_panel=deepcopy(parent_panel_reference)),training_frame_sha256=digest(frame),fit_payload_sha256=digest(payload),
        numeric_conversion_evidence=conversion,evaluation_references=evaluation,evaluation_dates_sha256=digest(calendar[127:]),original_coordinate_evidence=deepcopy(coordinates),
        original_provenance_and_missing=deepcopy(gaps),preserved_evidence_sidecars=deepcopy(source['preserved_evidence_sidecars']),preserved_sidecar_references=deepcopy(source['preserved_sidecar_references']),original_identity_assumed_window=deepcopy(source['original_identity_assumed_window']),
        evaluation_prior_fit_overlap_evidence=deepcopy(source['evaluation_prior_fit_overlap_evidence']),excluded_from_training_selection_fields=['median_dollar_volume_usd'],
        liquidity_evidence_scope='ORIGINAL_2026_09_21_PANEL_METADATA_PRESERVED_NOT_2026_03_20_LIQUIDITY_GATE',
        pool_scope='RETROSPECTIVE_LATE_POOL_AND_CONDITIONAL_IDENTITY_RISK_LABELS_NOT_HISTORICAL_ELIGIBILITY',new_numerical_task_identity_required=True,old_results_are_not_dated_refit_results=True,
        matrix_digest_is_typed_payload_not_fitter_selected_matrix_identity=True,historical_retrospective_only=True,**FLAGS)
    result['content_sha256']=digest(result);return result


def selected_mapping_dated(panel,security_ids):
    require(panel.get('schema')==SCHEMA,'Dated schema required')
    require(panel['content_sha256']==digest({k:v for k,v in panel.items() if k!='content_sha256'}),'Panel content hash')
    for key in FLAGS:require(panel[key] is False,'Panel authority changed')
    require(type(security_ids) is list and security_ids and all(type(s) is str for s in security_ids) and security_ids==sorted(set(security_ids)),'Canonical nonempty selected SID list')
    mapping=panel['fit_payload']['selected_by_security'];require(set(security_ids)<=set(mapping),'Unknown selected SID')
    chosen={s:deepcopy(mapping[s]) for s in security_ids}
    for value in chosen.values():require(set(value)=={'ticker','issuer_id','risk_chain'} and all(type(v) is str and v for v in value.values()),'Exact fitter selected schema')
    require(len({r['issuer_id'] for r in chosen.values()})==len(chosen),'Same issuer classes cannot coexist in a selected combination')
    return chosen
