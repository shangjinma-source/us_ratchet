"""Synthetic authority/source integration; no registration or live collection."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from tempfile import TemporaryDirectory
from fractions import Fraction
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v1 import SCOPE
from backtest.current_strategy_prospective_paper_book_v1 import SETTLEMENT_SCHEMA
from backtest.current_strategy_prospective_paper_store_v1 import ProspectivePaperStore, SOURCE
from backtest.current_strategy_prospective_paper_coordinator_v1 import (
    ProspectivePaperCoordinator,SOURCE as COORDINATOR_SOURCE)
from data.strategy_prospective_paper_selection_v1 import verify_prospective_target
from data.strategy_prospective_paper_decision_v1 import produce_prospective_decision
from data.strategy_prospective_paper_cap_store_v1 import ProspectivePersistentCaps
from test_strategy_prospective_paper_integration_v1 import fixture, execution
import test_strategy_prospective_paper_integration_v1 as integration
from data.strategy_prospective_paper_settlement_v1 import (
    CODE_PATHS as SETTLEMENT_PINS,accepted_references,produce_prospective_settlement)
from data.current_quantity_v2_completed_session_minutes import capture
from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_prospective_paper_source_capture_v1 import capture_prospective_sources,CODE_PATHS as CAPTURE_PINS
from data.strategy_prospective_paper_unit_review_v1 import review_prospective_execution_sources,CODE_PATHS as UNIT_PINS
from data.strategy_prospective_paper_daily_v1 import verify_prospective_daily
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL
from test_strategy_paper_execution_preview_v1 import capture as raw_fixture


def captured_execution(daily,clock,caps,folder):
    """Only transport bytes are fixtures; market metadata and units are produced."""
    root=Path(folder);root.mkdir()
    current=datetime.fromisoformat(clock())
    raw,_=raw_fixture(daily['book'],current)
    identity=b'isolated synthetic identity for B'
    (root/'identity').write_bytes(identity)
    manifest=canonical(dict(candidates=[dict(ticker='B',security_id='B',status='READY_CONDITIONAL',
        identity_reviewed=True,identity_source_references=['identity'])],source_hashes={'identity':sha256(identity).hexdigest()}))
    (root/'identity-manifest.json').write_bytes(manifest)
    selection=daily['selection_arguments']
    saved_review=json.loads(selection['source_package']['files'][selection['unit_review_path']])
    securities={'B':{'ticker':'B'}}
    def action(ticker,start,end):
        return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
            meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
    rss=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
    captured=capture_prospective_sources(book=daily['book'],authority=daily['authority'],
        admitted_decisions=daily['admitted_decisions'],admitted_settlements=daily.get('admitted_settlements'),
        identity_resolver=PinnedStrategyIdentity(root,'identity-manifest.json',sha256(manifest).hexdigest()),
        securities=securities,target_quantities=daily['selection_result']['payload']['target_quantities'],
        window_start=saved_review['training_closed_at'],output_directory=root/'capture',clock=lambda:current,
        market_fetch=lambda ticker:raw['files'][ticker+'.raw'],
        halt_fetch=lambda:dict(url=SOURCE_URL,status=200,body=raw['files']['halt.raw']),
        action_fetch=action,rss_fetch=lambda:dict(status=200,body=rss))
    # Review only bytes restored from the capture's on-disk archive.
    archive=json.loads((root/'capture'/'archive.json').read_bytes())
    for name,key in [('market','market_capture'),('actions','action_capture')]:
        package=deepcopy(archive['packages'][name])
        package['files']={p:(root/'capture'/'blobs'/(h+'.bin')).read_bytes() for p,h in package['source_hashes'].items()}
        captured[key]=package
    combined=review_prospective_execution_sources(book=daily['book'],authority=daily['authority'],
        admitted_decisions=daily['admitted_decisions'],admitted_settlements=daily.get('admitted_settlements'),
        securities=securities,market_capture=captured['market_capture'],action_package=captured['action_capture'],
        training_manifest_sha256=saved_review['training_manifest_sha256'],
        historical_search_arguments_sha256=saved_review['historical_search_arguments_sha256'],
        historical_price_basis=saved_review['securities']['B']['historical_price_basis'],
        training_closed_at=saved_review['training_closed_at'],clock=lambda:current)
    market=combined['market_capture'];units=combined['unit_review']
    (root/'unit-review.json').write_bytes(canonical(units))
    signal=verify_prospective_daily(**daily)
    admission=canonical(dict(schema='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1',scope=SCOPE,
        descriptor_sha256=daily['book']['descriptor_sha256'],account_id=daily['book']['account_id'],
        account_revision=daily['book']['revision'],target_id=signal['target_id'],daily_evidence_id=signal['signal']['evidence_id'],
        cap_namespace_id=caps.namespace_id,source_sha256=market['source_hashes'],
        unit_review_sha256=sha256(canonical(units)).hexdigest(),available_at=clock()))
    return dict(daily_arguments=daily,execution_admission_bytes=admission,
        trusted_execution_admission_sha256=sha256(admission).hexdigest(),market_capture=market,
        unit_review=units,caps=caps,clock=clock)


def execution_with_production_halt_path(daily,clock,caps):
    args=execution(daily,clock,caps=caps)
    market=args['market_capture'];files=market['files']
    receipt=files.pop('halt.receipt')
    path='halt-source/'+sha256(receipt).hexdigest()+'.receipt.json'
    files[path]=receipt;market['halt_evidence']['receipt_path']=path
    market['source_hashes']={p:sha256(raw).hexdigest() for p,raw in files.items()}
    admission=json.loads(args['execution_admission_bytes'])
    admission['source_sha256']=market['source_hashes']
    args['execution_admission_bytes']=canonical(admission)
    args['trusted_execution_admission_sha256']=sha256(args['execution_admission_bytes']).hexdigest()
    return args


def completed_source(daily,accepted,admitted,origin,folder):
    """Generate synthetic raw via the existing capture and original unit reviewer."""
    current=datetime.fromisoformat('2026-11-03T21:01:00+00:00')
    files=deepcopy(origin);pins={p:sha256(b).hexdigest() for p,b in files.items()}
    refs=accepted_references(book=accepted,authority=daily['authority'],admitted_decisions=admitted,
        files=files,source_hashes=pins,now=current)
    captures={};reviews={}
    for oid,ref in refs.items():
        opening=datetime.fromisoformat('2026-11-03T14:30:00+00:00')
        closing=datetime.fromisoformat('2026-11-03T21:00:00+00:00')
        times=list(range(int(opening.timestamp()),int(closing.timestamp()),60));n=len(times)
        raw=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ref['ticker'],currency='USD',
            instrumentType='EQUITY',dataGranularity='1m',exchangeTimezoneName='America/New_York'),timestamp=times,
            indicators=dict(quote=[dict(open=[990]*n,high=[1010]*n,low=[900]*n,close=[990]*n,volume=[10]*n)]))])))
        path=Path(folder)/'completed'
        capture(directory=path,security_id=ref['security_id'],ticker=ref['ticker'],session='2026-11-03',
            session_open=opening.isoformat(),session_close=closing.isoformat(),
            calendar_source_reference='sha256:'+json.loads(daily['authority']['descriptor_arguments']['descriptor_bytes'])['calendar_sha256'],
            fetch=lambda _:raw,clock=lambda:current)
        paths={k:'capture/'+v for k,v in dict(raw='response.bin',receipt='receipt.json',started='started.json',minutes='minutes.json').items()}
        for p in paths.values():files[p]=(path/Path(p).name).read_bytes()
        captures[oid]=paths
        def action(ticker,start,end):
            return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
                meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
        rss=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 20:00:00 GMT</pubDate></item></channel></rss>'
        sources=PaperActionEvidenceSources(fetch=action,rss_fetch=lambda:dict(status=200,body=rss),clock=lambda:current)
        late=BoundedLateUnitReview(action_sources=sources,clock=lambda:current).capture(reference=ref,
            capture_raw=raw,captured_at=current,origin_files=files,account_id=accepted['account_id'],state_revision=accepted['revision'])
        files.update(late['files']);reviews[oid]=late['review_path']
    # Save and independently read the complete source closure before producer admission.
    archive=Path(folder)/'settlement-originals';archive.mkdir()
    mapping={p:sha256(b).hexdigest() for p,b in files.items()}
    for raw in files.values():
        path=archive/sha256(raw).hexdigest()
        if not path.exists():path.write_bytes(raw)
    loaded={p:(archive/h).read_bytes() for p,h in mapping.items()}
    result=produce_prospective_settlement(book=accepted,authority=daily['authority'],admitted_decisions=admitted,
        captures=captures,unit_reviews=reviews,files=loaded,source_hashes=mapping,clock=lambda:current)
    (archive/'review.json').write_bytes(result['review_bytes'])
    (archive/'settlement.json').write_bytes(result['settlement_bytes'])
    return result


class DurableIntegrationTests(unittest.TestCase):
    def test_selector_daily_limits_sqlite_restart_fill_then_hold(self):
        self.run_chain(False)

    def test_completed_raw_review_durable_caps_restart_next_session_hold(self):
        self.run_chain(True)

    def run_chain(self,completed):
        with TemporaryDirectory() as folder:
            if completed:
                original_setup=integration.setup;original_plan=integration.plan_future_start
                def expanded_setup(path):
                    value=original_setup(path);calendar=json.loads(value['calendar_bytes'])
                    calendar['sessions'].append(dict(date='2026-11-04',open='2026-11-04T14:30:00+00:00',close='2026-11-04T21:00:00+00:00'))
                    value['calendar_bytes']=canonical(calendar)
                    return value
                def expanded_plan(**kwargs):
                    kwargs['terminal_date']='2026-11-04'
                    return original_plan(**kwargs)
                with patch.object(integration,'setup',expanded_setup),patch.object(integration,'plan_future_start',expanded_plan):
                    daily=fixture(folder,extra_code_paths={SOURCE,COORDINATOR_SOURCE}|SETTLEMENT_PINS|CAPTURE_PINS|UNIT_PINS)
            else:daily=fixture(folder,extra_code_paths={SOURCE})
            now=['2026-11-03T15:00:00+00:00']
            admitted={};settlements={}
            def open_store():
                if completed:
                    return ProspectivePaperCoordinator(root=folder,authority=daily['authority'],
                        admission_loader=lambda:dict(decisions=admitted,settlements=settlements),
                        target_verifier=lambda result:verify_prospective_target(result,**daily['selection_arguments']),
                        clock=lambda:datetime.fromisoformat(now[0]))
                return ProspectivePaperStore(root=folder,authority=daily['authority'],
                    admission_loader=lambda:dict(decisions=admitted,settlements=settlements),
                    target_reader=lambda:daily['selection_result']['decision_id'],
                    clock=lambda:datetime.fromisoformat(now[0]))
            store=open_store();initial=store.initialize()
            self.assertEqual(initial,daily['book'])
            if completed:
                now[0]='2026-11-03T15:00:03+00:00'
                store.publish_target(daily['selection_result'],expected_book_revision=initial['revision'],previous_target_id=None)
                self.assertEqual(open_store().current_target_id(),daily['selection_result']['decision_id'])
            self.assertEqual(daily['selection_result']['payload']['target_quantities'],{'B':20})
            caps=ProspectivePersistentCaps(root=folder,book=initial,authority=daily['authority'],
                admitted_decisions=admitted,clock=lambda:'2026-11-03T15:00:10+00:00',initialize=True)
            namespace=caps.namespace_id
            args=(captured_execution(daily,lambda:'2026-11-03T15:00:10+00:00',caps,Path(folder)/'execution-day-one')
                  if completed else execution_with_production_halt_path(daily,lambda:'2026-11-03T15:00:10+00:00',caps=caps))
            self.addCleanup(caps.close)
            decision=produce_prospective_decision(**args)
            self.assertEqual(decision['status'],'VERIFIED_PROSPECTIVE_PAPER_EXECUTION_DECISION')
            admitted[decision['decision_sha256']]=decision['decision_bytes']
            request=dict(kind='ACCEPT',operation_id='generated-decision',expected_revision=initial['revision'],
                         decision_bytes=decision['decision_bytes'].decode())
            now[0]='2026-11-03T15:00:11+00:00'
            accepted=store.apply(request)
            self.assertEqual(open_store().read(),accepted)
            self.assertEqual(open_store().apply(deepcopy(request)),accepted)
            self.assertEqual(len(open_store().read()['operations']),1)
            if completed:
                reviewed=completed_source(daily,accepted,admitted,args['market_capture']['files'],folder)
                evidence=reviewed['settlement_bytes'];observed=reviewed['evidence']['observed_through']
                minutes=reviewed['evidence']['minutes'];now[0]='2026-11-03T21:01:01+00:00'
            else:
                # Boundary-only fixture retained separately from the source-producer test.
                pending={oid:o for oid,o in accepted['orders'].items() if o['closed'] is None}
                minutes={oid:[dict(security_id=o['security_id'],start='2026-11-03T15:01:00+00:00',
                    end='2026-11-03T15:02:00+00:00',open='990',high='1010',low='900',close='990')]
                    for oid,o in pending.items()}
                evidence=canonical(dict(schema=SETTLEMENT_SCHEMA,scope=SCOPE,
                    status='VERIFIED_PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE',
                    descriptor_sha256=accepted['descriptor_sha256'],registration_sha256=accepted['registration_sha256'],
                    account_id=accepted['account_id'],account_revision=accepted['revision'],
                    pending_orders_sha256=sha256(canonical(pending)).hexdigest(),minutes=minutes,
                    observed_through='2026-11-03T15:02:00+00:00',available_at='2026-11-03T15:02:00+00:00',
                    source_review=dict(scope='PROSPECTIVE_PAPER_MINUTE_SOURCE_REVIEW_V1',receipt_sha256='a'*64,
                        source_sha256={'synthetic-minutes.json':sha256(canonical(minutes)).hexdigest()})))
                observed='2026-11-03T15:02:00+00:00';now[0]='2026-11-03T15:02:01+00:00'
            settlements[sha256(evidence).hexdigest()]=evidence
            settle=dict(kind='SETTLE',operation_id='observed-fill',expected_revision=accepted['revision'],
                minutes=minutes,observed_through=observed,settlement_bytes=evidence.decode())
            filled=open_store().apply(settle)
            del store
            reopened=open_store().read()
            self.assertEqual(reopened,filled)
            self.assertEqual(reopened['shares'],{'B':10})
            self.assertEqual(Fraction(reopened['cash']),20000-10*Fraction(decision['new_orders'][0]['limit_price']))
            self.assertEqual(open_store().apply(request),filled)
            self.assertEqual(len(open_store().read()['operations']),2)
            caps.close()
            next_time='2026-11-04T15:00:10+00:00' if completed else '2026-11-03T15:02:10+00:00'
            caps=ProspectivePersistentCaps(root=folder,book=reopened,authority=daily['authority'],
                admitted_decisions=admitted,admitted_settlements=settlements,
                clock=lambda:next_time)
            self.addCleanup(caps.close)
            self.assertEqual(caps.namespace_id,namespace)
            daily.update(book=reopened,admitted_decisions=admitted,admitted_settlements=settlements,
                         now=next_time)
            receipt=json.loads(daily['receipt_bytes'])
            receipt.update(account_revision=reopened['revision'],available_at='2026-11-03T15:02:02+00:00',
                           valid_from='2026-11-03T15:02:02+00:00')
            if completed:
                inputs=json.loads(daily['files']['normalized.json'])
                inputs['signal_date']='2026-11-03';inputs['observed_at']='2026-11-03T21:00:00+00:00'
                inputs['session_dates'].append('2026-11-03')
                inputs['session_close_times']['closes']['2026-11-03']='2026-11-03T21:00:00+00:00'
                for history in inputs['histories'].values():
                    history['closes']=history['closes'][1:]+[dict(date='2026-11-03',close='100',completed_at='2026-11-03T21:00:00+00:00')]
                    history['units']['unit_asof']='2026-11-03'
                daily['files']['normalized.json']=canonical(inputs)
                receipt.update(market_asof='2026-11-03T21:00:00+00:00',source_received_at='2026-11-03T21:01:00+00:00',
                    available_at='2026-11-04T15:00:02+00:00',valid_from='2026-11-04T15:00:02+00:00',
                    valid_until='2026-11-04T21:00:00+00:00',execution_session=dict(date='2026-11-04',
                    open='2026-11-04T14:30:00+00:00',close='2026-11-04T21:00:00+00:00'),
                    source_sha256={p:sha256(b).hexdigest() for p,b in daily['files'].items()})
            daily['receipt_bytes']=canonical(receipt)
            daily['trusted_receipt_sha256']=sha256(daily['receipt_bytes']).hexdigest()
            again=(captured_execution(daily,lambda:next_time,caps,Path(folder)/'execution-day-two')
                   if completed else execution_with_production_halt_path(daily,lambda:next_time,caps=caps))
            held=produce_prospective_decision(**again)
            self.assertEqual(held['status'],'HOLD')
            self.assertEqual(held['new_orders'],[])
            self.assertIsNone(held['decision_bytes'])
            self.assertEqual(open_store().read(),filled)
            if completed:
                self.assertEqual(open_store().current_target_id(),daily['selection_result']['decision_id'])


if __name__=='__main__':unittest.main()
