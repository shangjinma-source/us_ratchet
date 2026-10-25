from pathlib import Path
from datetime import datetime
from tempfile import TemporaryDirectory
import sqlite3
import unittest
import json
from hashlib import sha256

from data.strategy_prospective_paper_daily_context_v2 import CapturedPaperDailyContext, SOURCE
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from data.strategy_prospective_paper_daily_capture_v2 import load_prospective_daily_archive
from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore
from test_strategy_prospective_paper_daily_capture_v2 import arguments
from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target
from backtest.current_strategy_prospective_paper_coordinator_v2 import ProspectivePaperCoordinator
from backtest.current_strategy_prospective_paper_run_once_v2 import ProspectivePaperRunOnce
from data.strategy_prospective_paper_cap_store_v2 import ProspectivePersistentCaps
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL
from test_strategy_paper_execution_preview_v1 import capture as market_fixture
from backtest.current_strategy_prospective_paper_admission_reader_v2 import registered_selection
from scripts.run_prospective_paper_v2 import load_runner


class DailyContextTests(unittest.TestCase):
    def test_runner_uses_capture_context_and_waits_for_first_configuration_close(self):
        with TemporaryDirectory() as folder:
            release=canonical(dict(schema='PAPER_CAP_EXIT_DAILY_RELEASE_V2',policy_id='MONTHLY_CAP50_EXIT20',
                approved=True,scope='PAPER_DAILY_SIGNAL_RULE_ONLY',approved_at='2026-11-03T14:58:00+00:00'))
            args,calls=arguments(folder,extra_code_paths=_local_import_closure({SOURCE,
                'scripts/run_prospective_paper_v2.py',
                'backtest/current_strategy_prospective_paper_run_once_v2.py',
                'backtest/current_strategy_prospective_paper_coordinator_v2.py'}),extra_sources={'policy/cap.json':release},
                extra_sessions=[dict(date='2026-11-04',open='2026-11-04T14:30:00+00:00',close='2026-11-04T21:00:00+00:00')],
                integration_review_sha256=sha256(b'synthetic integration review').hexdigest())
            now=['2026-11-03T15:00:00+00:00'];clock=lambda:datetime.fromisoformat(now[0])
            store=ProspectivePaperAdmissionStore(root=Path(folder),authority=args['authority'],clock=clock)
            store.initialize();sqlite3.connect(store.directory.parent/'risk.sqlite3').close()
            coordinator=ProspectivePaperCoordinator(root=Path(folder),authority=args['authority'],
                admission_loader=store.load,target_verifier=lambda r:verify_prospective_target(r,**args['selection_arguments']),clock=clock)
            coordinator.initialize();now[0]='2026-11-03T15:00:01+00:00'
            archived=store.produce_and_archive_selection('monthly-selection',args['selection_arguments'])
            self.assertEqual(archived,args['selection_result'])
            # Reopen a store object and recover all selection bytes from its
            # registry; daily execution does not use a closure over test args.
            reopened_store=ProspectivePaperAdmissionStore(root=Path(folder),authority=args['authority'],clock=clock)
            recovered=registered_selection(reopened_store,archived['decision_id'])
            self.assertEqual(recovered['selection_arguments'],args['selection_arguments'])
            now[0]='2026-11-03T15:00:03+00:00'
            coordinator.publish_target(args['selection_result'],expected_book_revision=args['book']['revision'],previous_target_id=None)
            now[0]='2026-11-03T15:00:10+00:00'
            context=CapturedPaperDailyContext(root=Path(folder),authority=args['authority'],admission_store=store,
                selection_loader=lambda target:registered_selection(reopened_store,target),
                request_templates=args['capture_requests'],release_path=args['release_path'],clock=clock,
                fetch_daily=args['fetch_daily'],fetch_official=args['fetch_official'])
            runner=ProspectivePaperRunOnce(root=Path(folder),authority=args['authority'],coordinator=coordinator,
                admission_store=store,daily_context=context,identity_resolver=None,securities={},training_context={},
                cap_release_path='policy/cap.json',clock=clock)
            before=coordinator.read()
            self.assertEqual(runner.run_once()['status'],'WAIT_FIRST_CONFIGURATION_CLOSE')
            self.assertEqual(calls,['daily','official'])
            self.assertEqual(runner.run_once()['status'],'WAIT_FIRST_CONFIGURATION_CLOSE')
            self.assertEqual(calls,['daily','official'])
            self.assertEqual(coordinator.read(),before)
            self.assertEqual(store.load()['decisions'],{})
            # Next session uses actual capture/normalization, not a hand-built
            # admitted daily archive. Only HTTP response bytes are synthetic.
            caps=ProspectivePersistentCaps(root=Path(folder),book=args['book'],authority=args['authority'],
                admitted_decisions={},clock=lambda:now[0],initialize=True)
            caps.close()
            now[0]='2026-11-04T15:00:10+00:00'
            original=args['fetch_daily']
            def next_daily(*values):
                response=original(*values);doc=json.loads(response['body']);series=doc['chart']['result'][0]
                series['timestamp'].append(int(datetime.fromisoformat('2026-11-03T14:30:00+00:00').timestamp()))
                series['indicators']['quote'][0]['close'].append(101)
                series['indicators']['adjclose'][0]['adjclose'].append(101)
                return dict(response,body=canonical(doc))
            rss=b'<rss><channel><title>Nasdaq</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            context.fetch_daily=next_daily;context.fetch_official=lambda:dict(status=200,body=rss)
            root=Path(folder);identity_raw=b'synthetic identity B';(root/'identity-source').write_bytes(identity_raw)
            manifest=canonical(dict(candidates=[dict(ticker='B',security_id='B',status='READY_CONDITIONAL',
                identity_reviewed=True,identity_source_references=['identity-source'])],
                source_hashes={'identity-source':sha256(identity_raw).hexdigest()}))
            (root/'identity-manifest').write_bytes(manifest)
            identity=PinnedStrategyIdentity(root,'identity-manifest',sha256(manifest).hexdigest())
            review=json.loads(args['selection_arguments']['source_package']['files']['review.paper.json'])
            training={k:review[k] for k in ('training_manifest_sha256','historical_search_arguments_sha256','training_closed_at')}
            training['historical_price_basis']=review['securities']['B']['historical_price_basis']
            def market(ticker):return market_fixture(args['book'],clock())[0]['files'][ticker+'.raw']
            def halt():return dict(url=SOURCE_URL,status=200,body=market_fixture(args['book'],clock())[0]['files']['halt.raw'])
            def actions(ticker,start,end):return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
                meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
            def write(path,raw):
                destination=root/path;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
                return dict(path=path,sha256=sha256(raw).hexdigest())
            authority=args['authority'];descriptor_args=authority['descriptor_arguments']
            for path,raw in (descriptor_args['code_bytes']|descriptor_args['source_bytes']).items():write(path,raw)
            config=dict(schema='REGISTERED_PROSPECTIVE_PAPER_RUNTIME_V2',
                descriptor=write('runtime/descriptor.json',descriptor_args['descriptor_bytes']),
                approval=write('runtime/approval.json',descriptor_args['approval_bytes']),
                calendar=write('runtime/calendar.json',descriptor_args['calendar_bytes']),
                registration=write('runtime/registration.json',authority['registration_bytes']),
                integration_review=write('runtime/review.txt',b'synthetic integration review'),
                daily_sources={'B':dict(configuration=write('runtime/daily.json',args['capture_requests']['B']['configuration_bytes']),
                                        parent=args['capture_requests']['B']['parent_reference'])},
                daily_release_path='policy/daily.json',cap_release_path='policy/cap.json',
                identity_manifest=dict(path='identity-manifest',sha256=sha256(manifest).hexdigest()),
                securities={'B':{'ticker':'B'}},training_context=training)
            config_ref=write('runtime/config.json',canonical(config))
            runner=load_runner(root=root,configuration_path=config_ref['path'],expected_sha256=config_ref['sha256'],
                clock=clock,transports=dict(daily_fetch=next_daily,daily_official_fetch=lambda:dict(status=200,body=rss),
                market_fetch=market,halt_fetch=halt,action_fetch=actions,rss_fetch=lambda:dict(status=200,body=rss)))
            self.assertEqual(runner.run_once()['status'],'PAPER_OPERATION_RECORDED')
            orders=list(coordinator.read()['orders'].values())
            self.assertEqual([(order['side'],order['quantity']) for order in orders],[('BUY',10)])
            count=len(calls)
            self.assertEqual(runner.run_once()['status'],'WAIT_PENDING_SESSION_CLOSE')
            self.assertEqual(len(calls),count)

    def test_registered_context_captures_and_reopens_without_manual_daily_archive(self):
        with TemporaryDirectory() as folder:
            args,calls=arguments(folder,extra_code_paths=_local_import_closure({SOURCE,
                'backtest/current_strategy_prospective_paper_admission_store_v2.py'}))
            store=ProspectivePaperAdmissionStore(root=Path(folder),authority=args['authority'],clock=args['clock'])
            store.initialize()
            sqlite3.connect(store.directory.parent/'risk.sqlite3').close()
            context=CapturedPaperDailyContext(root=Path(folder),authority=args['authority'],admission_store=store,
                selection_loader=lambda target:dict(selection_result=args['selection_result'],selection_arguments=args['selection_arguments']),
                request_templates=args['capture_requests'],release_path=args['release_path'],clock=args['clock'],
                fetch_daily=args['fetch_daily'],fetch_official=args['fetch_official'])
            target=args['selection_result']['decision_id']
            result=context(args['book'],target)
            reopened=load_prospective_daily_archive(**result,clock=args['clock'])
            self.assertEqual(reopened['status'],'DAILY_SIGNAL_READY')
            self.assertEqual(reopened['daily_arguments']['book'],args['book'])
            self.assertEqual(calls,['daily','official'])
            with self.assertRaisesRegex(ValueError,'PARTIAL_REQUIRES_RECOVERY'):
                context(args['book'],target)
            self.assertEqual(calls,['daily','official'])
            self.assertEqual(store.load()['decisions'],{})


if __name__=='__main__':unittest.main()
