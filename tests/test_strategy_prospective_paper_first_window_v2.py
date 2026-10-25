from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_first_window_v2 import CODE_PATHS, review_paper_first_window
from test_strategy_prospective_paper_decision_v2 import next_day
from data.strategy_paper_first_window_core_v2 import SOURCES
from data.strategy_paper_first_window_capture_v2 import capture_first_window, load_first_window_archive
from data.strategy_prospective_paper_selection_v2 import select_prospective_target
from data.current_quantity_v2_paper_action_sources import daily_url
from data.strategy_prospective_paper_daily_capture_v2 import capture_prospective_daily, CODE_PATHS as CAPTURE_PINS
from data.strategy_prospective_paper_cap_daily_v2 import project_paper_cap_daily
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_prospective_paper_decision_v2 import produce_prospective_decision, ProspectiveTemporaryCaps
from data.strategy_paper_application_descriptor_v2 import SCOPE
from test_strategy_paper_execution_preview_v1 import capture as market_capture


class PaperFirstBindingTests(unittest.TestCase):
    def test_full_paper_binding_transport_review_and_archive(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            def save(name,raw):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
                return dict(path=name,sha256=sha256(raw).hexdigest())
            evidence=save('identity-source',b'fixture identity B')
            identity=save('identity-manifest',canonical(dict(candidates=[dict(ticker='B',security_id='B',
                status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-source'])],
                source_hashes={'identity-source':evidence['sha256']})))
            daily=next_day(folder,extra_code_paths=CODE_PATHS | CAPTURE_PINS,
                extra_sources={name:(root/name).read_bytes() for name in ('identity-manifest','identity-source')})
            calendar=save('calendar.json',daily['authority']['descriptor_arguments']['calendar_bytes'])
            sessions=json.loads(daily['authority']['descriptor_arguments']['calendar_bytes'])['sessions']
            closed=[r for r in sessions if r['date']<'2026-11-04'][-20:]
            def chart(rows):
                return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol='B',currency='USD',
                    instrumentType='EQUITY',exchangeName='NMS'),events={},
                    timestamp=[int(datetime.fromisoformat(r['open']).timestamp()) for r in rows],
                    indicators=dict(quote=[dict(close=[101]*len(rows))],adjclose=[dict(adjclose=[101]*len(rows))]))])))
            selection=daily['selection_arguments'];package=selection['source_package']
            def put(name,value):
                raw=value if isinstance(value,bytes) else canonical(value)
                package['files'][name]=raw;package['source_hashes'][name]=sha256(raw).hexdigest()
            baseline=chart([r for r in closed if r['date']<'2026-11-03'])
            put('baseline.raw',baseline)
            start=datetime.fromisoformat('2026-10-01T00:00:00+00:00')
            through=datetime.fromisoformat('2026-11-03T15:00:00+00:00')
            put('baseline.receipt',dict(raw_path='baseline.raw',raw_sha256=sha256(baseline).hexdigest(),
                security_id='B',ticker='B',started_at=through.isoformat(),received_at=through.isoformat(),
                http_status=200,body_truncated=False,transport_error=None,interval='1d',
                requested_from=start.isoformat(),requested_through=through.isoformat(),
                url=daily_url('B',start,through),response_url=daily_url('B',start,through)))
            units=json.loads(package['files']['review.paper.json'])
            units['securities']['B']['source_references']+=['baseline.raw','baseline.receipt']
            put('review.paper.json',units)
            admission=json.loads(selection['source_review_bytes']);admission['source_sha256']=package['source_hashes']
            selection['source_review_bytes']=canonical(admission)
            selection['trusted_source_review_sha256']=sha256(selection['source_review_bytes']).hexdigest()
            selected=select_prospective_target(clock=lambda:selection['now'],**selection)
            pins=[save(name,(Path(__file__).resolve().parents[1]/name).read_bytes()) for name in SOURCES]
            config=canonical(dict(schema='PAPER_FIRST_DAILY_WINDOW_V2',security_id='B',
                monthly_decision_date='2026-11-03',identity=identity,calendar=calendar,source_pins=pins))
            binding=dict(account_id=daily['book']['account_id'],account_revision=daily['book']['revision'],
                target_id=selected['decision_id'],session='2026-11-04')
            args=dict(root=root,configuration_bytes=config,configuration_sha256=sha256(config).hexdigest(),
                book=daily['book'],authority=daily['authority'],admitted_decisions={},admitted_settlements={},
                selection_result=selected,selection_arguments=selection,
                clock=lambda:datetime.fromisoformat(daily['now']))
            rss=b'<rss><channel><title>Nasdaq</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            result=capture_first_window(directory=root/'first',review_arguments=args,read_binding=lambda:binding,
                fetch_daily=lambda *values:dict(status=200,body=chart(closed)),
                fetch_official=lambda:dict(status=200,body=rss))
            self.assertEqual(result['status'],'FIRST_WINDOW_REVIEWED_NOT_ADMITTED')
            restored=load_first_window_archive(root=root,directory=root/'first',
                trusted_complete_sha256=result['complete_sha256'],expected_binding=binding)
            self.assertEqual(restored['receipt_bytes'],result['receipt_bytes'])
            receipt=json.loads(result['receipt_bytes'])
            inputs=json.loads(result['files'][receipt['normalized_inputs_path']])
            self.assertEqual(inputs['signal_date'],'2026-11-03')
            self.assertEqual(receipt['target_id'],selected['decision_id'])
            # No producer or verifier is replaced: transport bytes alone are synthetic.
            config_document=json.loads(config);config_document['output_root']='aggregate-first-capture'
            config=canonical(config_document)
            aggregate=capture_prospective_daily(root=root,book=daily['book'],authority=daily['authority'],
                admitted_decisions={},admitted_settlements={},selection_result=selected,selection_arguments=selection,
                release_path=daily['release_path'],capture_requests={'B':dict(configuration_bytes=config,
                    configuration_sha256=sha256(config).hexdigest())},output_directory=root/'aggregate',
                clock=args['clock'],read_binding=lambda:binding,
                fetch_daily=lambda *values:dict(status=200,body=chart(closed)),
                fetch_official=lambda:dict(status=200,body=rss))
            self.assertEqual(aggregate['status'],'DAILY_SIGNAL_READY')
            risk=MonthlyPeakExitStore(root/'integration-risk.sqlite3')
            projected=project_paper_cap_daily(daily_arguments=aggregate['daily_arguments'],risk_store=risk,cap_release_path='policy/cap.json')
            self.assertIsNotNone(projected['projection'])
            self.assertEqual(projected['signal']['effective_target_quantities'],{'B':10})
            book=daily['book'];clock=lambda:daily['now']
            caps=ProspectiveTemporaryCaps(book=book,authority=daily['authority'],admitted_decisions={},clock=clock)
            self.addCleanup(caps.close)
            market,unit_review=market_capture(book,args['clock']())
            admission=canonical(dict(schema='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1',scope=SCOPE,
                descriptor_sha256=book['descriptor_sha256'],account_id=book['account_id'],account_revision=book['revision'],
                target_id=projected['target_id'],daily_evidence_id=projected['signal']['evidence_id'],
                cap_namespace_id=caps.namespace_id,source_sha256=market['source_hashes'],
                unit_review_sha256=sha256(canonical(unit_review)).hexdigest(),available_at=clock()))
            decision=produce_prospective_decision(daily_arguments=aggregate['daily_arguments'],
                execution_admission_bytes=admission,trusted_execution_admission_sha256=sha256(admission).hexdigest(),
                market_capture=market,unit_review=unit_review,caps=caps,clock=clock,risk_store=risk,
                cap_release_path='policy/cap.json')
            self.assertEqual([(o['side'],o['quantity']) for o in decision['new_orders']],[('BUY',10)])

    def test_verified_paper_binding_and_changed_selection_rejection(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            daily=next_day(folder,extra_code_paths=CODE_PATHS)
            def save(name,raw):
                (root/name).write_bytes(raw)
                return dict(path=name,sha256=sha256(raw).hexdigest())
            identity_source=save('identity-source',b'fixture identity B')
            identity=save('identity-manifest',canonical(dict(candidates=[dict(ticker='B',security_id='B',
                status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity-source'])],
                source_hashes={'identity-source':identity_source['sha256']})))
            calendar=save('calendar.json',daily['authority']['descriptor_arguments']['calendar_bytes'])
            raw=canonical(dict(schema='PAPER_FIRST_DAILY_WINDOW_V2',security_id='B',
                monthly_decision_date='2026-11-03',identity=identity,calendar=calendar))
            arguments=dict(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
                capture_files={},book=daily['book'],authority=daily['authority'],admitted_decisions={},
                admitted_settlements={},selection_result=daily['selection_result'],
                selection_arguments=daily['selection_arguments'],clock=lambda:datetime.fromisoformat(daily['now']))
            # Source rules are separately tested with complete raw receipts.
            # Here only the source-core boundary is replaced; paper verification is real.
            with patch('data.strategy_prospective_paper_first_window_v2.review_source_window',return_value={'checked':True}) as core:
                self.assertEqual(review_paper_first_window(**arguments),{'checked':True})
                context=core.call_args.kwargs
                self.assertEqual(context['entry']['ticker'],'B')
                self.assertEqual(context['account_id'],daily['book']['account_id'])
                self.assertEqual(context['target_id'],daily['selection_result']['decision_id'])
                changed=deepcopy(arguments)
                changed['selection_result']['decision_id']='0'*64
                with self.assertRaises(ValueError):
                    review_paper_first_window(**changed)
                self.assertEqual(core.call_count,1)


if __name__=='__main__':
    unittest.main()
