"""Synthetic source boundary; actual selector, daily projector, limits and ledger."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from fractions import Fraction
import json
from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_selection_v2 import select_prospective_target
from data.strategy_prospective_paper_cap_daily_v2 import project_paper_cap_daily
from data.strategy_prospective_paper_decision_v2 import produce_prospective_decision
from backtest.current_strategy_prospective_paper_book_v2 import transact,replay
from test_strategy_paper_execution_preview_v1 import capture


def verify_zero_cap_exit(test,daily,filled,admitted,settlements,store,caps,admission):
    at='2026-11-05T15:00:10+00:00'
    args=deepcopy(daily['selection_arguments'])
    args.update(book=filled,admitted_decisions=admitted,admitted_settlements=settlements,now=at)
    package=args['source_package']
    def put(name,value):
        raw=canonical(value);package['files'][name]=raw;package['source_hashes'][name]=sha256(raw).hexdigest()
    marks=json.loads(package['files'][args['marks_path']])
    for mark in marks.values():mark.update(price='30000',observed_at=at)
    put(args['marks_path'],marks)
    units=json.loads(package['files'][args['unit_review_path']])
    units.update(account_revision=filled['revision'],reviewed_at=at,marks_sha256=package['source_hashes'][args['marks_path']])
    for sid,unit in units['securities'].items():
        unit.update(current_mark_sha256=sha256(canonical(marks[sid])).hexdigest(),covered_through=at)
    put(args['unit_review_path'],units)
    source=json.loads(args['source_review_bytes'])
    source.update(account_revision=filled['revision'],available_at=at,source_sha256=package['source_hashes'])
    args['source_review_bytes']=canonical(source);args['trusted_source_review_sha256']=sha256(args['source_review_bytes']).hexdigest()
    selected=select_prospective_target(clock=lambda:at,**args)
    test.assertEqual(selected['payload']['target_quantities'],{'B':1})
    next_daily=deepcopy(daily)
    next_daily.update(book=filled,admitted_decisions=admitted,admitted_settlements=settlements,
        selection_arguments=args,selection_result=selected,now=at)
    history=json.loads(next_daily['files']['normalized.json'])
    history.update(signal_date='2026-11-04',observed_at='2026-11-04T21:00:00+00:00')
    history['base_target'].update(origin_reference=selected['decision_id'],quantities={'B':1})
    history['session_dates'].append('2026-11-04')
    history['session_close_times']['closes']['2026-11-04']=history['observed_at']
    for row in history['histories'].values():
        row['closes']=row['closes'][1:]+[dict(date='2026-11-04',completed_at=history['observed_at'],close='101')]
        row['units']['unit_asof']='2026-11-04'
    next_daily['files']['normalized.json']=canonical(history)
    receipt=json.loads(next_daily['receipt_bytes'])
    receipt.update(account_revision=filled['revision'],target_id=selected['decision_id'],available_at=at,
        source_received_at=at,valid_from=at,valid_until='2026-11-05T21:00:00+00:00',market_asof=history['observed_at'],
        execution_session=dict(date='2026-11-05',open='2026-11-05T14:30:00+00:00',close='2026-11-05T21:00:00+00:00'),
        source_sha256={p:sha256(raw).hexdigest() for p,raw in next_daily['files'].items()})
    next_daily['receipt_bytes']=canonical(receipt);next_daily['trusted_receipt_sha256']=sha256(next_daily['receipt_bytes']).hexdigest()
    old_risk=store.path.read_bytes()
    projected=project_paper_cap_daily(daily_arguments=next_daily,risk_store=store,cap_release_path='policy/cap.json')
    test.assertEqual(projected['signal']['effective_target_quantities'],{'B':0})
    test.assertEqual(projected['projection']['projection_kind'],'ZERO_MONTHLY_TARGET_EXIT')
    test.assertEqual(store.path.read_bytes(),old_risk)
    caps.clock=lambda:at
    market,units=capture(filled,datetime.fromisoformat(at))
    envelope=json.loads(admission)
    envelope.update(account_revision=filled['revision'],target_id=selected['decision_id'],
        daily_evidence_id=projected['signal']['evidence_id'],source_sha256=market['source_hashes'],
        unit_review_sha256=sha256(canonical(units)).hexdigest(),available_at=at)
    raw=canonical(envelope)
    decision=produce_prospective_decision(daily_arguments=next_daily,execution_admission_bytes=raw,
        trusted_execution_admission_sha256=sha256(raw).hexdigest(),market_capture=market,unit_review=units,
        caps=caps,clock=lambda:at,risk_store=store,cap_release_path='policy/cap.json')
    test.assertEqual([(o['side'],o['quantity']) for o in decision['new_orders']],[('SELL',1)])
    all_decisions={**admitted,decision['decision_sha256']:decision['decision_bytes']}
    accepted=transact(filled,dict(kind='ACCEPT',operation_id='zero-cap-exit',expected_revision=filled['revision'],
        decision_bytes=decision['decision_bytes'].decode()),authority=daily['authority'],admitted_decisions=all_decisions,
        admitted_settlements=settlements,current_target_id=selected['decision_id'],
        clock=lambda:datetime.fromisoformat('2026-11-05T15:00:11+00:00'))
    test.assertEqual(accepted['cash'],filled['cash'])
    test.assertEqual(accepted['shares'],filled['shares'])
    test.assertEqual(replay(accepted,authority=daily['authority'],admitted_decisions=all_decisions,
        admitted_settlements=settlements),accepted)
    test.assertEqual(store.path.read_bytes(),old_risk)

    # Only a subsequent admitted minute crossing may credit the modeled sale.
    pending={oid:o for oid,o in accepted['orders'].items() if o['closed'] is None}
    minutes={}
    for oid,order in pending.items():
        price=Fraction(order['limit_price'])
        minutes[oid]=[dict(security_id=order['security_id'],start='2026-11-05T15:01:00+00:00',
            end='2026-11-05T15:02:00+00:00',open=str(price+10),high=str(price+20),low=str(price+1),close=str(price+10))]
    evidence=json.loads(next(iter(settlements.values())))
    evidence.update(account_revision=accepted['revision'],pending_orders_sha256=sha256(canonical(pending)).hexdigest(),
        observed_through='2026-11-05T15:02:00+00:00',available_at='2026-11-05T15:02:00+00:00',minutes=minutes)
    evidence['source_review']['source_sha256']={'fixture':sha256(canonical(minutes)).hexdigest()}
    settlement=canonical(evidence);all_settlements={**settlements,sha256(settlement).hexdigest():settlement}
    flat=transact(accepted,dict(kind='SETTLE',operation_id='zero-cap-fill',expected_revision=accepted['revision'],
        minutes=minutes,observed_through=evidence['observed_through'],settlement_bytes=settlement.decode()),
        authority=daily['authority'],admitted_decisions=all_decisions,admitted_settlements=all_settlements,
        clock=lambda:datetime.fromisoformat('2026-11-05T15:02:01+00:00'))
    test.assertFalse(any(flat['shares'].values()))
    test.assertEqual(Fraction(flat['cash']),Fraction(filled['cash'])+Fraction(decision['new_orders'][0]['limit_price']))
    test.assertEqual(replay(flat,authority=daily['authority'],admitted_decisions=all_decisions,
        admitted_settlements=all_settlements),flat)
