"""Account-bound launcher fork of run_local_scheduled_simulation.py (2026-10-19).
Default is read-only. Shares the old log directory and exclusive lock so the old
and new launchers cannot execute concurrently. No task installation is performed.
Literal pins cover the local static imports discovered for this reviewed entry;
they are not a claim of complete dynamic dependency or environment attestation.
Monthly release directory remains the same explicitly trusted publication input.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT=Path('E:/Git/us_ratchet')
PYTHON=Path('D:/python/python.exe')
BOOTSTRAP='research_contracts/isolated_trial_20261016/bootstrap-v10.json'
DAILY='research_contracts/isolated_trial_20261016/daily.json'
PINS={'api/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'api/current_quantity_v2_difference.py': '07db94bf3459becdfa0b445a63e73771788b9578d63c3ac73fa5b7d10e151838',
 'backtest/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'backtest/affordable_support_seeds.py': '69e47fe9ae76917b3fd84797cfa60cc974f8428744c5760084372719f3791c02',
 'backtest/current_quantity_v2_annual_clock.py': '8dea47bd87c3694cce33871689e7cc2bcf332c48714812241a931a40885bc339',
 'backtest/current_quantity_v2_close_capture_simulation.py': 'ea08811a946d7f764d5530427e3ac91b5ee49342a162db1e4c6258517d385797',
 'backtest/current_quantity_v2_continuation_simulation.py': 'dafc96b753bb26dac95afc6ed6c76d13dbe305cd994f509eaf209dda68e735f2',
 'backtest/current_quantity_v2_daily_evidence_providers.py': 'ff15cfe331c0892b8da8a93f5d7e65c2d999ed3e1a521543c5db17838941ec14',
 'backtest/current_quantity_v2_daily_next_open.py': '2cd8b55f26b11c1055cd2a4f23dd8ed5b0087fb5418805f0bfa826c231d50061',
 'backtest/current_quantity_v2_daily_settlement_simulation.py': '3b6a5ed5609ded1fbde1b48b41e1d2052a1f6164ae8ef3c4351162c3d6b2234d',
 'backtest/current_quantity_v2_daily_simulation.py': '22a1bb7adee162993e8cea9351232a40c0278c307895bca9055496ea25d3c0db',
 'backtest/current_quantity_v2_minute_day_fill.py': '112351aec80270c12f75f27e9429498d7de269d3caee345b605df2be0348910f',
 'backtest/current_quantity_v2_monthly_simulation.py': '9f111c92a4d059e0d1cfb9871b590567a37d3c5d3f750e31534caaab323d90e4',
 'backtest/current_quantity_v2_next_open_book.py': '2d0f4268bf1a22ad5362a82335bf57813c697703628165d9fd6f0d24728db4e8',
 'backtest/current_quantity_v2_simulated_settlement.py': 'b7a6b6e3f355dee08e89e213f763ab01d5d974e0f163ee620aa809eb991133e8',
 'backtest/current_quantity_v2_simulation_bootstrap.py': 'e72702589b8eb40175dc550ae971f21809765280e53ed4f111e19501fa7ca579',
 'backtest/current_quantity_v2_simulation_store.py': '17ae390e4b63e85f367ff04a05ce0657f211e76e1982c2dd0e14a5dbc4202563',
 'backtest/log_concave_integer_search.py': 'bcd1278f35021b16a728433d4b791a4f64819218521789b94df261b84f22b741',
 'backtest/quantity_training_upper_bound.py': 'e244cc50c21785ae79be98d3cdd916cbb6b4e1d1b1e2dbd9630876f610647915',
 'backtest/return_priority_ads_conversion.py': '28bfd3c8b874f7ce704d258cbb48fd158e45e88925bb8862a298a6d5b84f9e68',
 'backtest/return_priority_cash_stock_entitlements.py': '7aece5075df20b76e1a39e8cc0f5cfb14f6987a72968e3b5a853ff1823d4be59',
 'backtest/return_priority_distribution_entitlements.py': '5762bd88aff00b91c4d55e2416c733681f9f680f755742c1c7d965e7856c5954',
 'backtest/return_priority_exact_floor_ceil_research.py': '96a69d7f7458d6d0fed1b67236312afcd443719bec897c0c38d7b70a4559ef5b',
 'backtest/return_priority_fresh_cash_quantity_search.py': '756a16a83735279db24332d096aa149b54fc7ff4e91cb807410b3f33f425b588',
 'backtest/return_priority_fresh_cash_quantity_search_v2.py': 'f813782ab166139c8d30b268a242fa05bd65ce76e9b9b20aa03a0beee2bd01d7',
 'backtest/return_priority_joint_candidate_generator_research.py': 'f9ec16351443c41454ee667daac3af2863d15471e3f43937044006300abc0a01',
 'backtest/return_priority_monthly_quantity_provider_v4.py': '48e5096bae35ca433a46f0ea4a8750f37fc8aa931a2d4c5e6a0778529c27dda4',
 'backtest/return_priority_monthly_training_inputs.py': 'c0a548c9d5140ee81a7f18982d32e78a4718178f6b66aefa080cd3f18628855d',
 'data/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'data/current_cash_portfolio_research.py': '54055b6cc52570d384fa3fe7a5d8f775a7db472c4358a7152e05e5abd8396f76',
 'data/current_portfolio_preview.py': '9024e5f747d4171d0f382cda3d45866a9ce0b76c155228a9ffec3ce559a65964',
 'data/current_quantity_portfolio_research.py': 'e9b0ec8fd8f9d1093bca6a00cfaa6c0434c55da3e5d6b404f29e87a58ecb6a17',
 'data/current_quantity_portfolio_research_v2.py': '3df63af3b8cbbde2fd21d4102f703412ffa5b58f12b31807c9aa43fe1373b75a',
 'data/current_quantity_projection_v2.py': '69a94f8645a94c1929262027c42638121c28d7b583e32c27cbbc4ab9250f152e',
 'data/current_quantity_v2_bounded_unit_review.py': 'f6a374023e8e06b117374d59fd6bafa5c0da74679ad336c3f1457c126050c6c1',
 'data/current_quantity_v2_completed_session_minutes.py': 'a19cd3f7bf40e1671ba8cf1c86c6b187948af99669b0130eec9b266b33cc64cb',
 'data/current_quantity_v2_continuation_service.py': 'cebc185643db749a1f81a992363bafe1bdf1d4d9eeeec97d53e46b107ebaed9b',
 'data/current_quantity_v2_current_cash_continuation.py': '7b984d83ffa283181afb198ed2e42db645265d0979cab0ea2e016c591376e1da',
 'data/current_quantity_v2_current_cash_continuation_sources.py': 'dfc66948235d3df8b1570d77567728bba79d859d2ac0655d1796a00f117de2cb',
 'data/current_quantity_v2_current_cash_ledger_adapter.py': '9a3fa57d7741df4d01eb2d0b7094e9d480aa6ef469d0682d9d1cd947178aade9',
 'data/current_quantity_v2_current_cash_plan.py': 'b9c2c61a41d01e5d8dd3325fd3a7eb5d894b67b0c929e67f6994fa8a7464a2a1',
 'data/current_quantity_v2_current_cash_service.py': 'fa944a4fc34f0564668288d7315893701cd5ef732a1347bf23509aecde763c13',
 'data/current_quantity_v2_current_cash_sources.py': 'ab986e9918f9d389f75ea1877f04fe718309fe61a50375f65538436967f8ad0b',
 'data/current_quantity_v2_difference_plan.py': '06ef796cf0c151797cafa13c045aeee6b9282ff03724ef80774b59b29a794039',
 'data/current_quantity_v2_difference_service.py': 'a6e91bcf8a298d7e5ad03780f68c6ffb0fa25bffceb7ed81a16b9ff586e7f699',
 'data/current_quantity_v2_execution_month.py': '025ab32ae57277e5ca692b172215c6880f7b1e2f7fea3d6267105377f1d69598',
 'data/current_quantity_v2_late_unit_review.py': '82a9c19e2eb263df4082f7814525b439c11feafcd184cf49b93294b2444c9ead',
 'data/current_quantity_v2_minute_close_marks.py': '1c7ecbb92f1316ba06fc49f60c4067f3ac48ba4af7e225e4fcc99081d40fc249',
 'data/current_quantity_v2_monthly_bounded_review.py': '5ee27a5d17473323305058d27e492df94ee485d3e77ab05b9dfbea781a9516c6',
 'data/current_quantity_v2_monthly_capture_audit.py': '33759ee3fc56827093bf7ec956fc65cef4fad71887c45457dae837eb616dfd06',
 'data/current_quantity_v2_monthly_composition.py': '0dc004102e7303e940dea2e297de465316442ccdbe2b8ca779fb011ca3c34450',
 'data/current_quantity_v2_monthly_continuation_factory.py': 'a8bf4a750d2032a55cb0d83aede8264fc5d9cf47c5fb4cee061d475ae34ec7aa',
 'data/current_quantity_v2_monthly_continuation_sources.py': '6a80a707658b8a070aee1c2bd5793d1de0e5121086c9d9f8870bf5541b634f7b',
 'data/current_quantity_v2_monthly_decision.py': '087e5c942d392d3d0911a6cf6de518fd97e06c2b356a925442bdd8f2883cb395',
 'data/current_quantity_v2_monthly_factory.py': 'afcdd92024edad4da9e67cc3fe6aa18fe6bc1e1352b93d9b1d6c1ed925fc9576',
 'data/current_quantity_v2_monthly_origins.py': '0603d392ffe74c28f97791b394e30a5ead697415c11412bea6ce52658ba083eb',
 'data/current_quantity_v2_monthly_research_service.py': '35f8362a37c61eb88f578c19e26c12366961c6c45c9eb7c16b14c99822f59d74',
 'data/current_quantity_v2_monthly_retarget.py': '74232643b28cdc840e7eaeee87fe007275af7f8fb880d3d6fa7e67651d897326',
 'data/current_quantity_v2_monthly_service.py': '0267d4acf33ac2644b98ebdb95bd9e432a10120846ac27638a90f4051e78137f',
 'data/current_quantity_v2_monthly_sources.py': 'b73ca28119e3c6d8cdd48979e09ae5f06e6ede4ddda41de3a7b5f5a82fe51bb4',
 'data/current_quantity_v2_monthly_training.py': 'a44447855ac0387428c7bac332df18927aef0b873a3c9b8efba4e39403ec73c2',
 'data/current_quantity_v2_monthly_training_reader.py': '096293a3da1c68f0542d2306a08f15bf63ef9e7356a18ef135a1f6247a764dac',
 'data/current_quantity_v2_paper_action_sources.py': 'b4be5cccbc4c759d3f7ecb7a28a3a994f24f212929149f866eb48d551e88238f',
 'data/current_quantity_v2_paper_chain.py': 'a4a8bec0c0a542edf753497a488b8030100cf91661251682d755c59cce532f13',
 'data/current_quantity_v2_paper_ledger.py': 'fa92581c42258f6f87f677297416d6b22363973d50523a3f0a82296bacd137cc',
 'data/current_quantity_v2_paper_review.py': '08ffee49a4f321f054ce23cc16e29b0d10592334db08ab9a84b3e4715ba77901',
 'data/current_quantity_v2_paper_review_provider.py': 'cf46f6630aea3471d21c6dad8c1d5faf07cea646f9f4c8cdb4a6947ac316fa8a',
 'data/current_quantity_v2_paper_service.py': '8d89dbc6cad5a9926601d7a47d1ebb0bff49a0d9a717f59b7331dff4ad79d3a9',
 'data/current_quantity_v2_pullback_cap_store.py': '7d0c3e344a2339814753c39930ea6b6e7d448101b0c17d459514bd992a2612ce',
 'data/current_quantity_v2_pullback_entry.py': '48249a9c5e1fa043d1c54d9668da82191bdc0a09fc1ed9fbeb61dab5c3aa4e4f',
 'data/current_quantity_v2_pullback_proof.py': '8bf590b99df98628d705f68b2a1f08451db5b0adc5c9c5c449c17a2229c3bef4',
 'data/current_quantity_v2_pullback_runtime.py': '40e2b1539b64d0ecf73617baff62e8bcb4579e6849eb8759e1edfe2eb4c6cfbb',
 'data/current_quantity_v2_pullback_sources.py': '64a5c392802347c5fdf0d905da86033814db742631024547c6bcd121d3877b6f',
 'data/current_quantity_v2_service_factory.py': '22cdd25b9f98b199ef6f5ef6506d348df1f4e60165f4117298b3c527ef7d1973',
 'data/current_quantity_v2_simulation_origin_files.py': 'f12c0c7419acd33082813706656bafa8b43e74d1789feaa5d13070b8db23c03c',
 'data/current_quantity_v2_simulation_paths.py': '2c992c162aefa428103c961bc46c0f691ab1e85396ce3aadb2ff4f956cce234c',
 'data/current_quantity_v2_source_admission_policy.py': 'b744ec94ad5ad82046cfc0b4d9deece896c3e396fd615b92f5b9fdce75b64ef8',
 'data/current_quantity_v2_verified_snapshot_bundle.py': '9fc64cbd25975f78d8429ed6ba00c1e967d40c5aba48f5f1875c197279d4d538',
 'data/current_research_capital_decision.py': 'fc3f2113f314ec3547b4d15d241d9868f3091ce39f449bb2029b90d626cdf0cf',
 'data/current_research_capital_decision_v2.py': 'c680c57e669f9c07be40a4f583c420f4432e9b44b3574bc19b635145ed492ea7',
 'data/current_research_close_panel.py': '5ebacf528557a869b28b532b79852964b0ed6d1865c553626618284b34c3841d',
 'data/current_research_intraday_cap_store.py': '18c2ffc09c9472db1cd61165580cd2e2d36c04b6743c7c25fa4c59431fadcc66',
 'data/current_research_intraday_execution.py': '92d3d8f1d7f21911748f905ea2e05ddc0caa5845237b146257ca3e91b13fc1b4',
 'data/current_research_intraday_journal.py': 'ad14db99c9ae66bbb392a5156a1b64a1657cfa80d2bf6afda716d53d527bcc7b',
 'data/current_research_ohlc_panel.py': 'c9eed4d223c33a8edbdd1f425eff80079ded57cc55f69386d58f696d45b8e1f0',
 'data/current_research_snapshot_resolver.py': 'e05264d7e713e56e5b58d7d996d1d4eda2f8645ca9b134520302ef0ecd0a1e8e',
 'data/current_top1_portfolio_research.py': '5c03a3b5595c72e55cb2b3c094f40305b49835dd8a17fafb381e067e13ead822',
 'data/quantity_v2_simulation_account_binding.py': '42800afd5ce3d474fdc468985e61139ae998d153e2fccfb0ecceaf977213e585',
 'research_contracts/isolated_trial_20261016/bootstrap-v10.json': '3dc94f6f6d02f3a6d8e93897aabc9f572bfe459196d5cd127e5f50b2d766d4e7',
 'research_contracts/isolated_trial_20261016/daily.json': '1939ff1614f87d6732a4d4e731244d759a4e067159ad4a940628ece2deea0c3f',
 'scripts/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 'scripts/bootstrap_current_quantity_v2_simulation.py': '272cccc969b152b67bae9cb259d715c0c71c2541af893536da9772a09a2dd5ed',
 'scripts/current_research_official_alert_capture.py': '105cde07551eb99c107d3f99d6637e41a8ffcbc12f12d75e22322c326a0b2e27',
 'scripts/monthly_runtime_routes.py': 'b99af69a58ad2c23860c7167cd7e68a54bf4f3dd6691a79f09a0fcab66561c03',
 'scripts/return_priority_current_rebased_training.py': '21312a804e3ffd2ae469adc9f5ce1e8173d0511bf7caaef364bb2cadab15f39e',
 'scripts/return_priority_latest_saved_snapshot_research.py': '1180c3dd863a5c682a0a1e55b93e51af00fdb61f90882ce1b1400f44b6ac965e',
 'scripts/run_account_bound_scheduled_simulation.py': 'c64d57213225fce01f4678ff1e9bfe1fc561bdce6b1663e0117ad0831f7d2794',
 'scripts/run_current_quantity_v2_simulation.py': '5ec25a6def63b63f46eae449f4d2715ac6f9913f125d3d07393377c12672bab2'}
MONTHLY='research_contracts/isolated_trial_20261016/monthly-releases'
LOGS='data/local_scheduler/quantity_v2_daily'


def now():return datetime.now(timezone.utc).isoformat()


def checked_command():
    for path,expected in PINS.items():
        source=ROOT/path
        if source.is_symlink() or sha256(source.read_bytes()).hexdigest()!=expected:
            raise ValueError('PINNED_INPUT_CHANGED')
    return [str(PYTHON),'-X','utf8','-E','-B','-m','scripts.run_account_bound_scheduled_simulation',
        '--bootstrap-config',str(ROOT/BOOTSTRAP),'--bootstrap-sha256',PINS[BOOTSTRAP],
        '--daily-config',str(ROOT/DAILY),'--daily-sha256',PINS[DAILY],
        '--monthly-runtime-directory',str(ROOT/MONTHLY),'--execute']


def save(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())


def run(*,execute=False):
    if not execute:
        checked_command()
        return dict(status='PREFLIGHT_ONLY',execute=False,source_hashes=PINS,working_directory=str(ROOT))
    directory=ROOT/LOGS;directory.mkdir(parents=True,exist_ok=True)
    run_directory=directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex)
    run_directory.mkdir()
    save(run_directory/'started.json',dict(status='STARTED',started_at=now(),scheduled_module='scripts.run_account_bound_scheduled_simulation',
        source_hashes=PINS,launcher_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))
    lock=directory/'running.lock';owned=False
    try:
        try:
            with lock.open('x',encoding='utf-8') as stream:stream.write(str(os.getpid()))
            owned=True
        except FileExistsError:
            result=dict(status='SKIPPED',reason='RUN_LOCK_PRESENT_REVIEW_IF_STALE')
        else:
            command=checked_command()
            # Raw output is retained even if the child is terminated or returns invalid JSON.
            with (run_directory/'stdout.txt').open('xb') as stdout,(run_directory/'stderr.txt').open('xb') as stderr:
                completed=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
            raw=(run_directory/'stdout.txt').read_bytes()
            if len(raw)>1024*1024:raise ValueError('CHILD_OUTPUT_TOO_LARGE')
            try:child=json.loads(raw.decode('utf-8').strip().splitlines()[-1])
            except (ValueError,IndexError,UnicodeError):raise ValueError('CHILD_RESULT_INVALID') from None
            if not isinstance(child,dict) or child.get('status') not in {'SKIPPED','COMPLETE','BLOCKED','CREATED_ISOLATED_SIMULATION'}:
                raise ValueError('CHILD_STATUS_UNRECOGNIZED')
            result=dict(status=child['status'],child_result=child,exit_code=completed.returncode)
            if completed.returncode:result['status']='BLOCKED'
    except Exception as error:
        result=dict(status='BLOCKED',reason=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'LOCAL_RUN_FAILED')
    finally:
        if owned:lock.unlink()
    result['finished_at']=now();save(run_directory/'finished.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    try:result=run(**vars(parser.parse_args(argv)))
    except Exception:result=dict(status='BLOCKED',reason='LOCAL_PREFLIGHT_FAILED',finished_at=now())
    print(json.dumps(result,ensure_ascii=False));return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
