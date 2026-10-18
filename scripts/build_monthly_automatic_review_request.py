"""Build an existing publisher request from pinned automatic screening evidence.

No fetch or account writes. This is conditional known-source review, not complete
corporate-action/PIT certification. Inputs are explicit local trusted evidence.
"""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources as IdentityReader
from data.current_quantity_v2_monthly_training import _daily
from data.current_quantity_v2_monthly_known_source_review import review
from scripts.prepare_monthly_captured_training import build
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_simulated_settlement import _references


def account_snapshot(daily):
    saved=SimulationStore(daily['database_path']).read(daily['simulation_id'])
    return saved


def construct(*,preparation_arguments,settings,daily,inputs,output_prefix):
    require(set(inputs)=={'schema','expected_revision','source_hashes','feed_path','feed_receipt_path','policy_path','identity_manifest_path','held_bar_sources'},'AUTO_REVIEW_INPUT_FIELDS')
    require(inputs['schema']=='MONTHLY_AUTOMATIC_REVIEW_INPUTS_V1','AUTO_REVIEW_SCHEMA')
    now=stamp(preparation_arguments['clock']());preparation_arguments=dict(preparation_arguments,clock=lambda:now)
    root=Path(preparation_arguments['root']).resolve();saved=account_snapshot(daily)
    require(saved['revision']==inputs['expected_revision'],'AUTO_REVIEW_ACCOUNT_CHANGED')
    pins=inputs['source_hashes'];require(type(pins)is dict and 0<len(pins)<=2000,'SOURCE_PIN_LIMIT')
    files={};total=0
    for name,h in pins.items():
        IdentityReader._path(name);path=root/name
        require(not path.is_symlink() and path.resolve().is_relative_to(root) and path.is_file() and path.stat().st_size<=32*1024*1024,'AUTO_REVIEW_SOURCE_MISSING')
        raw=path.read_bytes();total+=len(raw);require(total<=128*1024*1024 and sha256(raw).hexdigest()==h,'AUTO_REVIEW_SOURCE_CHANGED');files[name]=raw
    for key in ('feed_path','feed_receipt_path','policy_path','identity_manifest_path'):require(inputs[key] in files,'AUTO_REVIEW_SOURCE_MISSING')
    for path,h in settings['fixed_source_hashes'].items():
        IdentityReader._path(path);p=root/path
        require(not p.is_symlink() and p.resolve().is_relative_to(root) and p.is_file() and p.stat().st_size<=32*1024*1024 and sha256(p.read_bytes()).hexdigest()==h,'AUTO_REVIEW_FIXED_SOURCE_CHANGED')
    manifest,compiled,_=build(**preparation_arguments)
    domain=compiled['input']['search_arguments']['metadata'];chain=saved['simulation']['chain'];ledger=chain['ledger']
    held={sid for sid,q in ledger['shares'].items() if Fraction(q)>0};outside=held-set(domain)
    require(type(inputs['held_bar_sources'])is dict and set(inputs['held_bar_sources'])==outside,'AUTO_REVIEW_HELD_CLOSE_DOMAIN_MISMATCH')
    references=_references(chain);identity_manifest=json.loads(files[inputs['identity_manifest_path']])
    meta=dict(domain)
    for sid in outside:
        rows=[r for r in identity_manifest['candidates'] if r.get('security_id')==sid]
        require(len(rows)==1 and rows[0]['ticker']==references[sid]['ticker'],'AUTO_REVIEW_HELD_IDENTITY_MISMATCH')
        meta[sid]=dict(ticker=rows[0]['ticker'],issuer_id=rows[0]['issuer_id'])
    reader=IdentityReader(root=root,snapshot_service=None,server_account_id=ledger['account_id'],identity_manifest_path=inputs['identity_manifest_path'])
    decision=dict(decision_date=manifest['decision_date'],binding=dict(search_arguments=dict(metadata=meta)))
    identities={sid:reader._identity(decision,files,pins,sid,manifest['decision_date']) for sid in meta}
    calendar=json.loads((root/settings['calendar_path']).read_bytes());closing=stamp(calendar['decision_close_at']);require(calendar['decision_date']==manifest['decision_date'] and closing<=now,'AUTO_REVIEW_CLOSE_TIME_INVALID')
    held_sources={}
    for sid,source in inputs['held_bar_sources'].items():
        require(type(source)is dict and set(source)=={'raw_path','receipt_path','unit_review_path'},'AUTO_REVIEW_HELD_SOURCE_FIELDS')
        require(all(p in files for p in source.values()),'AUTO_REVIEW_HELD_SOURCE_MISSING')
        raw=files[source['raw_path']];receipt=json.loads(files[source['receipt_path']]);ticker=meta[sid]['ticker']
        require(receipt['security_id']==sid and receipt['ticker']==ticker and receipt['target_date']==manifest['decision_date']
                and receipt['http_status']==200 and receipt['body_truncated'] is False and receipt['raw_sha256']==sha256(raw).hexdigest()
                and closing<=stamp(receipt['started_at_utc'])<=stamp(receipt['received_at_utc'])<=now,'AUTO_REVIEW_HELD_RECEIPT_INVALID')
        chart=json.loads(raw)['chart']['result'][0]
        require(not any(chart.get('events',{}).values()),'AUTO_REVIEW_HELD_ACTION_UNRESOLVED')
        from data.current_quantity_v2_late_unit_review import replay
        replay(json.loads(files[source['unit_review_path']]),reference=references[sid],capture_raw_sha256=sha256(raw).hexdigest(),captured_at=receipt['received_at_utc'],observed_at=now,read=lambda p:files[p])
        channel,closes=_daily(raw,ticker);require(closes.get(manifest['decision_date']) is not None and max(channel['dates'])==manifest['decision_date'],'AUTO_REVIEW_HELD_CLOSE_MISSING')
        held_sources[sid]=source['raw_path']
    result=review(preparation_arguments=preparation_arguments,feed_raw=files[inputs['feed_path']],feed_receipt_raw=files[inputs['feed_receipt_path']],policy_raw=files[inputs['policy_path']],evidence_prefix=output_prefix+'/screen')
    artifacts=dict(result['evidence_files']);review_path=output_prefix+'/review.json';identity_path=output_prefix+'/identities.json';binding_path=output_prefix+'/account-binding.json'
    artifacts[review_path]=canonical(result['review']);artifacts[identity_path]=canonical(dict(securities=identities,source_references=sorted(pins)))
    artifacts[binding_path]=canonical(dict(simulation_id=daily['simulation_id'],account_id=ledger['account_id'],revision=saved['revision'],outside_held=sorted(outside),source_hashes=pins,limitations=['Known-source screening only; no exhaustive unit or historical identity certification.']))
    combined=dict(pins)
    for p,h in settings['fixed_source_hashes'].items():require(p not in combined or combined[p]==h,'AUTO_REVIEW_PIN_CONFLICT');combined[p]=h
    for p,raw in artifacts.items():require(p not in combined,'AUTO_REVIEW_OUTPUT_SOURCE_COLLISION');combined[p]=sha256(raw).hexdigest()
    request=dict(preparation_arguments={k:v for k,v in preparation_arguments.items() if k not in ('root','clock','plan_validator')},supplemental_hashes=combined,calendar_path=settings['calendar_path'],schedule_path=settings['schedule_path'],identities_path=identity_path,held_bar_sources=held_sources,review_path=review_path,output_directory=settings['publish_output'])
    require(account_snapshot(daily)['revision']==saved['revision'],'AUTO_REVIEW_ACCOUNT_CHANGED')
    return dict(status='READY_REQUEST' if result['status']=='NO_MATCH_UNDER_BOUNDED_POLICY' else 'WAITING_REVIEW',reason=None if not result['review']['unresolved'] else 'KNOWN_SOURCE_UNRESOLVED',request=request if not result['review']['unresolved'] else None,artifacts=artifacts,revision=saved['revision'],unresolved=result['review']['unresolved'])
