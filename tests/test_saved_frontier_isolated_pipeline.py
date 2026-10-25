"""Offline synthetic full-source/lifecycle/risk/execution integration checks."""
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from core.strategy_account_ledger import canonical
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
from data.current_quantity_v2_paper_action_sources import daily_url
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from data.saved_frontier_isolated_pipeline import run_isolated_saved_frontier_pipeline
from data.strategy_account_action_capture import StrategyAccountActionCapture
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_execution_limits import build_execution_limits
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from test_saved_frontier_daily_evidence import joint_fixture
from test_saved_monthly_frontier_proposal import saved_record, sign


def digest(raw):
    return sha256(raw).hexdigest()


def current_review(case):
    """Explicitly new synthetic trusted review for a later account revision."""
    state = case['accounts'].read()
    proposed = case['proposal']['payload']['proposed_target_quantities']
    needed = ({sid for sid, q in proposed.items() if q}
              | {sid for sid, q in state['shares'].items() if q}
              | {order['security_id'] for order in state['orders'].values() if order['status'] == 'OPEN'}
              | set(case['risk_state']['peaks']))
    files = deepcopy(case['files'])
    review = json.loads(case['review_bytes'])
    identities = json.loads(files['identities.json'])
    identities['securities'] = {sid: row for sid, row in identities['securities'].items() if sid in needed}
    files['identities.json'] = canonical(identities)
    inputs = json.loads(files['normalized.json'])
    inputs['histories'] = {sid: row for sid, row in inputs['histories'].items() if sid in needed}
    for name in ('quantities', 'price_units'):
        inputs['base_target'][name] = {sid: q for sid, q in inputs['base_target'][name].items() if sid in needed}
    inputs['base_target']['quantities'] = {sid: proposed.get(sid, 0) for sid in sorted(needed)}
    inputs['base_target']['origin_reference'] = case['proposal']['proposal_id']
    for label in ('raw_by_security', 'unit_reviews'):
        for sid in set(review['documents'][label]) - needed:
            files.pop(review['documents'][label].pop(sid))
    for path in review['documents']['unit_reviews'].values():
        unit = json.loads(files[path])
        unit['identity_sha256'] = digest(files['identities.json'])
        unit['target_id'] = case['target']['target_id']
        unit['proposal_id'] = case['proposal']['proposal_id']
        files[path] = canonical(unit)
    files['normalized.json'] = canonical(inputs)
    review['account_revision'] = state['revision']
    review['target_id'] = case['target']['target_id']
    review['proposal_id'] = case['proposal']['proposal_id']
    review['source_sha256'] = {name: digest(raw) for name, raw in files.items()}
    case.update(state=state, files=files, review_bytes=canonical(review),
                trusted_review_sha256=digest(canonical(review)))


def offline_provider(case, clock):
    root = case['root'] / 'provider-sources'
    root.mkdir()
    for name, raw in case['source_files'].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    repository = Path(__file__).resolve().parents[1]
    runtime_pins = {name: digest((repository / name).read_bytes()) for name in REQUIRED_PINS}
    identity_raw = canonical(dict(synthetic=True, identities=['A', 'B', 'C', 'D', 'E']))

    class Identity:
        def __call__(self, ticker):
            return dict(ticker=ticker, security_id=ticker, source_references=['fixture-identities'],
                        source_hashes={'fixture-identities': digest(identity_raw)})

        def _read(self, name, expected):
            assert name == 'fixture-identities' and expected == digest(identity_raw)
            return identity_raw

    # Transport bytes are synthetic; the production market decoder, raw action
    # reviewer, execution limits and difference engine run without replacement.
    def raw(ticker):
        now = clock[0]
        opening = now.replace(hour=13, minute=30, second=0, microsecond=0)
        count = int((now-opening).total_seconds() // 60)
        price = {'A': 71, 'B': 100, 'C': 50, 'D': 50, 'E': 20}[ticker]
        quote = dict(open=[price]*count, high=[price+1]*count, low=[price-1]*count,
                     close=[price]*count, volume=[10]*count)
        return canonical(dict(chart=dict(error=None, result=[dict(meta=dict(symbol=ticker,
            currency='USD', instrumentType='EQUITY', exchangeTimezoneName='America/New_York',
            dataGranularity='1m', regularMarketPrice=price, regularMarketTime=int(now.timestamp()),
            currentTradingPeriod=dict(regular=dict(start=int(opening.timestamp()),
                                                   end=int((opening+timedelta(hours=6, minutes=30)).timestamp())))),
            timestamp=[int(opening.timestamp())+60*index for index in range(count)],
            indicators=dict(quote=[quote]))])))

    market = StrategyAccountMarketCapture(identity_resolver=Identity(), fetch=raw, clock=lambda: clock[0])

    def actions(ticker, begin, end):
        return dict(status=200, url=daily_url(ticker, begin, end), body=canonical(dict(
            chart=dict(error=None, result=[dict(meta=dict(symbol=ticker, currency='USD',
                                                         instrumentType='EQUITY'), events={})]))))

    action_capture = StrategyAccountActionCapture(fetch=actions, clock=lambda: clock[0],
        rss_fetch=lambda: dict(status=200, body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 23 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
    caps = LazyPullbackCapStore(case['root']/'intraday-caps.sqlite3', clock=lambda: clock[0].isoformat(),
                                max_history_rows=100, max_history_bytes=1024*1024)
    binding = case['target']['payload']['decision']['payload']['input_binding']
    manifest = binding['documents']['training_manifest']
    return StrategyAccountEvidenceProvider(root=root, manifest_path=manifest,
        manifest_sha256=binding['source_hashes'][manifest],
        training_closed_at=binding['training_cutoff_date']+'T20:00:00+00:00',
        market_capture=market, action_capture=action_capture,
        limits_builder=partial(build_execution_limits, cap_store=caps),
        output_root=case['root']/'execution', runtime_pins=runtime_pins, clock=lambda: clock[0])


class IsolatedFrontierPipelineTests(unittest.TestCase):
    def case(self, root, *, fee='1', cash=None, cancel=False):
        case = joint_fixture(root, archive=False, fee=fee)
        if cancel:
            case['accounts'].append(dict(event_id='cancel-existing', kind='CANCEL', order_id='old-open-E'),
                                    expected_revision=case['accounts'].read()['revision'])
        if cash is not None:
            case['accounts'].append(dict(event_id='later-cash', kind='CASH_CONFIRM', amount=cash,
                                         cash_basis='TOTAL_UNINVESTED'),
                                    expected_revision=case['accounts'].read()['revision'])
        current_review(case)
        clock = [datetime.fromisoformat(case['now'])]
        case['clock'] = clock
        case['provider'] = offline_provider(case, clock)
        return case

    def run_case(self, case, **overrides):
        args = dict(research_root=case['root'], account_store=case['accounts'],
            saved_target=case['target'], source_files=case['source_files'],
            risk_source_path=case['risk_path'], risk_source_sha256=digest(case['risk_path'].read_bytes()),
            review_bytes=case['review_bytes'], trusted_review_sha256=case['trusted_review_sha256'],
            daily_files=case['files'], execution_provider=case['provider'], clock=lambda: case['clock'][0], enabled=True)
        args.update(overrides)
        with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
             patch('data.strategy_account_evidence_provider.compile_saved_training',
                   side_effect=AssertionError('NEW_TRAINING_FORBIDDEN')):
            return run_isolated_saved_frontier_pipeline(**args)

    def test_default_disabled_has_no_inputs_or_io(self):
        result = run_isolated_saved_frontier_pipeline(research_root=None, account_store=None,
            saved_target=None, source_files=None, risk_source_path=None, risk_source_sha256=None,
            review_bytes=None, trusted_review_sha256=None, daily_files=None,
            execution_provider=None, clock=None)
        self.assertEqual(result['new_orders'], [])
        self.assertFalse(result['production_admitted'])

    def test_full_source_lifecycle_real_bridge_buy_sell_fee_zero_and_one(self):
        for fee in ('0', '1'):
            with self.subTest(fee=fee), TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
                case = self.case(root, fee=fee, cash='100', cancel=True)
                before = (case['accounts'].path.read_bytes(), case['risk_path'].read_bytes(), deepcopy(case['target']))
                result = self.run_case(case)
                self.assertEqual(result['status'], 'READY')
                self.assertEqual({(o['security_id'], o['side']) for o in result['new_orders']}, {('B', 'BUY'), ('D', 'SELL')})
                self.assertEqual(result['effective_target_quantities']['A'], 0)
                self.assertEqual(result['difference']['binding']['fee_bps'], fee)
                cost = -sum((Fraction(o['estimated_cash_change']) for o in result['new_orders'] if o['side'] == 'BUY'), Fraction(0))
                self.assertLessEqual(cost, 100)
                self.assertEqual(next(o['quantity'] for o in result['new_orders'] if o['side'] == 'BUY'), 1)
                self.assertTrue(result['waiting_cash'])
                self.assertTrue(all(o['proposal_id'] == case['proposal']['proposal_id'] for o in result['new_orders']))
                self.assertEqual((case['accounts'].path.read_bytes(), case['risk_path'].read_bytes(), case['target']), before)
                self.assertFalse(result['production_admitted'])
                self.assertFalse(result['daily_composition_v7_integrated'])
                self.assertEqual(result['optimizer_calls'], 0)

    def test_open_order_full_domain_wait_does_not_call_execution(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            case = self.case(root)
            with patch.object(case['provider'].market, 'capture', side_effect=AssertionError('WAIT_MUST_NOT_CAPTURE')):
                result = self.run_case(case)
            self.assertEqual(result['status'], 'WAIT')
            self.assertEqual(result['detail_status'], 'WAIT_PENDING_RECONCILIATION')
            self.assertEqual(result['new_orders'], [])
            self.assertEqual({row['security_id'] for row in result['daily_gate']['rows']}, {'A', 'B', 'D', 'E'})

    def test_zero_cash_sell_only_no_expected_proceeds_fund_buy(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            case = self.case(root, cash='0', cancel=True)
            result = self.run_case(case)
            self.assertEqual(result['status'], 'READY')
            self.assertEqual([(o['security_id'], o['side'], o['quantity']) for o in result['new_orders']], [('D', 'SELL', 3)])
            self.assertEqual(result['waiting_cash'][0]['security_id'], 'B')
            self.assertEqual(result['difference']['new_buy_cash_required'], '0')

    def test_missing_source_rejects_before_execution(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            case = self.case(root, cancel=True)
            files = dict(case['files']); files.pop('raw/B.json')
            with patch.object(case['provider'].market, 'capture', side_effect=AssertionError('NO_EXECUTION')), \
                 self.assertRaises(ValueError):
                self.run_case(case, daily_files=files)

    def test_month_changes_during_provider_and_expired_quotes_reject(self):
        for mode in ('month', 'expiry', 'account'):
            with self.subTest(mode=mode), TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
                case = self.case(root, cash='100', cancel=True)
                original = case['provider'].limits
                def limits(**kwargs):
                    result = original(**kwargs)
                    if mode == 'account':
                        case['accounts'].append(dict(event_id='concurrent-cash', kind='CASH_CONFIRM',
                            amount='99', cash_basis='TOTAL_UNINVESTED'),
                            expected_revision=case['accounts'].read()['revision'])
                    else:
                        case['clock'][0] += timedelta(days=10) if mode == 'month' else timedelta(seconds=121)
                    return result
                case['provider'].limits = limits
                with self.assertRaises(ValueError):
                    self.run_case(case)

    def test_expiry_after_difference_before_return_rejects(self):
        import data.saved_frontier_isolated_pipeline as pipeline
        for seconds, reason in ((121, 'REQUOTE_REQUIRED'),
                                (86400, 'DAILY_SIGNAL_EXPIRED_DURING_PREVIEW'),
                                (-1, 'SERVER_CLOCK_MOVED_BACKWARDS')):
            with self.subTest(seconds=seconds), TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
                case = self.case(root, cash='100', cancel=True)
                original = pipeline.preview_scoped_account
                def delayed_difference(**kwargs):
                    result = original(**kwargs)
                    self.assertTrue(result['new_orders'])
                    case['clock'][0] += timedelta(seconds=seconds)
                    return result
                with patch.object(pipeline, 'preview_scoped_account', side_effect=delayed_difference), \
                     self.assertRaisesRegex(ValueError, reason):
                    self.run_case(case)

    def test_zero_capped_candidate_needs_no_fabricated_source_domain(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            case = self.case(root, cancel=True)
            target = case['target']
            selected = target['payload']['decision']['payload']
            binding = selected['input_binding']
            arguments = binding['search_arguments']
            arguments['prices']['C'] = '15000'
            binding['marks']['C']['price'] = '15000'
            for scenario in arguments['training_scenarios']:
                scenario['C'] = '2'
            chosen = saved_record({'C': 1}, arguments)
            selected['search_result'].update(selected=chosen,
                best_by_k={'0': saved_record({}, arguments), '1': chosen})
            selected['target_quantities'] = {'C': 1}
            target['payload']['target_quantities'] = {'C': 1}
            sign(target)
            case['proposal'] = build_frontier_proposal(target=target)
            self.assertEqual(case['proposal']['payload']['proposed_target_quantities'], {'C': 0})
            current_review(case)
            self.assertNotIn('raw/C.json', case['files'])
            result = self.run_case(case)
            self.assertEqual(result['status'], 'READY')
            self.assertNotIn('C', result['effective_target_quantities'])
            self.assertEqual([(o['security_id'], o['side']) for o in result['new_orders']], [('D', 'SELL')])

    def test_positive_cash_but_no_affordable_buy_is_wait_without_orders(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            case = self.case(root, cancel=True)
            case['accounts'].append(dict(event_id='sold-old', kind='DIRECT_FILL', security_id='D',
                side='SELL', quantity=3, price='50', fees='0', executed_at='2026-10-20T15:00:00+00:00'),
                expected_revision=case['accounts'].read()['revision'])
            case['accounts'].append(dict(event_id='tiny-current-cash', kind='CASH_CONFIRM', amount='1',
                cash_basis='TOTAL_UNINVESTED'), expected_revision=case['accounts'].read()['revision'])
            current_review(case)
            result = self.run_case(case)
            self.assertEqual(result['status'], 'WAIT')
            self.assertEqual(result['new_orders'], [])
            self.assertEqual(result['reference_quotes'], {})
            self.assertEqual(result['effective_target_quantities']['D'], 0)
            self.assertTrue(result['waiting_cash'])

    def test_resigned_saved_selection_cannot_swap_recorded_holdings(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as root:
            case = self.case(root, cancel=True)
            for change, reason in (
                    ('holdings', 'FRONTIER_PIPELINE_SELECTION_ACCOUNT_FACTS'),
                    ('context', 'FRONTIER_PIPELINE_SELECTION_EXECUTION_CONTEXT'),
                    ('open_mark', 'FRONTIER_PIPELINE_ORIGINAL_MARK_DOMAIN')):
                with self.subTest(change=change):
                    target = deepcopy(case['target'])
                    binding = target['payload']['decision']['payload']['input_binding']
                    if change == 'holdings':
                        binding['strategy_shares'] = {'C': 3}
                        binding['holding_market_values'] = {'C': '150'}
                    elif change == 'context':
                        binding['execution_context']['sell_proceeds_available'] = True
                    else:
                        binding['marks'].pop('E')
                    sign(target)
                    # All content IDs and native arithmetic remain valid, but
                    # these saved facts do not match that recorded revision.
                    build_frontier_proposal(target=target)
                    with self.assertRaisesRegex(ValueError, reason):
                        self.run_case(case, saved_target=target)


if __name__ == '__main__':
    unittest.main()
