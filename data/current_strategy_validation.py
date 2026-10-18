"""Read pinned, independently checked research results; never execute a strategy."""
from data.current_quantity_v2_validation import read_quantity_v2_validation
from datetime import date
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'tmp/fixed12_monthly_limit_execution_20261014_v1'
READBACK = 'tmp/fixed12_monthly_execution_independent_readback_20261014_v1.json'
CONTRACT = 'research_contracts/fixed12_monthly_limit_execution_20261014_v1.json'
LABELS = {
    'QUANTITY_FROZEN_WEIGHT_REPLAY': '旧冻结权重组合',
    'TOP1_SAME_PROJECTION_FROZEN_WEIGHT_REPLAY': '旧单股冻结权重对照',
    'QQQ_FULL_WEIGHT': 'QQQ 对照',
}
PINS = {
    BASE + '/result.json': 'e07c0e9fed939e922e4f4fff9705a89421829f84c35008a2600f362efb874e60',
    BASE + '/registration.json': '288b1ff86159aea49dc87bf47c287450958d62fc5873224351ec113289453cab',
    BASE + '/protected_after.json': '5663f8b7c3a5b599b9ae597b78237b123e37418155a5ccd03134d9eb14a19ce7',
    READBACK: '10a8b4a87ed269a4e24012f78a8623d47655681171034e604182d25bea7c996d',
    CONTRACT: 'a680e83bb786379dce482bcec8ff6d1b806b85cc7065db2abc76f274eedcf879',
    BASE + '/QUANTITY_FROZEN_WEIGHT_REPLAY/metrics.json': '5461534a8a4a9516a9cc07ca189383cdda0791d01f83ab41f78ccb73a95b97f2',
    BASE + '/QUANTITY_FROZEN_WEIGHT_REPLAY/outcome.json': 'c51af017f9b6752201f73995cb2436fd41cdc8a0c426e699adf3e13d0241b621',
    BASE + '/TOP1_SAME_PROJECTION_FROZEN_WEIGHT_REPLAY/metrics.json': '7e7d89d7bb09f7009305f16bd39606bc95c0ff23942161b5647d6a93d52c4d52',
    BASE + '/TOP1_SAME_PROJECTION_FROZEN_WEIGHT_REPLAY/outcome.json': '3e3d55c38f842166da807a2e0243998233610f93e18d29d9f94170df2d8b314c',
    BASE + '/QQQ_FULL_WEIGHT/metrics.json': 'c81dacea27981cb6bb9058ed85a9135f5891032df235c90676ea48967829e668',
    BASE + '/QQQ_FULL_WEIGHT/outcome.json': 'f88288bf9ebeace1aeb6b4897785a869ce3f9bdc0aa108ecde9f9d5c503c46d7',
}

ACTUAL_BASE = 'tmp/monthly_actual_equity_execution_20261014_v1'
ACTUAL_ROOT_READBACK = 'tmp/monthly_actual_equity_root_final_readback_20261014_v1.json'
ACTUAL_READBACK = 'tmp/monthly_actual_equity_final_independent_20261014_v1.json'
ACTUAL_CALLBACK_READBACK = 'tmp/monthly_actual_equity_final_callbacks_readback_20261014_v1.json'
PINS.update({'tmp/monthly_actual_equity_execution_20261014_v1/result.json': 'df7b6a75d4c98e83ab31b649dabd9b430647fe77085f22ee7eb513cb3b8265b1', 'tmp/monthly_actual_equity_execution_20261014_v1/outcome.json': '80156817b1431e9a24f1ed14cf91d3384fa4cb7e1853456e09177038c122c0ea', 'tmp/monthly_actual_equity_execution_20261014_v1/registration.json': 'a3abe6b1a05450217693a90127294502c564f57d95773b3629b183b9dc19b5ed', 'tmp/monthly_actual_equity_execution_20261014_v1/protected_after.json': 'b20f62ee9ce6196298d873a8a01e979603bbcae150d1f7e10db4a07d0564674c', 'tmp/monthly_actual_equity_execution_20261014_v1/provider_audit.json': '7158ec98a383b7694b2ae55fa78dfc5d9685efa06b1bde6fec84e5df9cf19edd', 'tmp/monthly_actual_equity_root_final_readback_20261014_v1.json': 'b7041e3f12eff3f99a8c5ac9f13fb5252219084c1f01e329afab6add613d2244', 'tmp/monthly_actual_equity_final_independent_20261014_v1.json': '60284e98241a1f27bbfa1abec3e17fe6019b40dfe461814f67fb68037e2ea048', 'tmp/monthly_actual_equity_final_callbacks_readback_20261014_v1.json': 'bb71905554ad06a33a012688c1a577710b9c286369394938925543dbc7ea04d1'})

NEXT_BASE = 'tmp/next12_monthly_comparison_20261015_v1'
NEXT_REPAIR = 'tmp/next12_top1_pin_repair_20261015_v1'
NEXT_READBACK = 'tmp/next12_final_combined_independent_20261015_v1.json'
PINS.update({'tmp/next12_monthly_comparison_20261015_v1/result.json': '27dc017c5969b4f6760b3d24a3f5731b9495f301de72b822b84925c8720cb8cd', 'tmp/next12_monthly_comparison_20261015_v1/registration.json': '7bc6175d093b472a9b8583a5c9a7a757f3cddd3b5c96834fc4cebeae01cf4cd2', 'tmp/next12_monthly_comparison_20261015_v1/protected_after.json': 'eae1c2d83c249ac3ad9308dfa71fc38f23b760761972e35caf6d4a9c20a58b55', 'tmp/next12_monthly_comparison_20261015_v1/quantity/result.json': '940bcded0bde0b51874caf706a141a26b6131b1538e045cfff90cb1e2a934155', 'tmp/next12_monthly_comparison_20261015_v1/quantity/outcome.json': '08edca2fa2e195df2fe608c00f5ca850a278ea3e0574fda8a736c52066855cea', 'tmp/next12_monthly_comparison_20261015_v1/top1/result.json': 'dc0e949f7d209a72939aa7df8c021fcf5ec800ed31f670d6a8585ad1ee36ce7e', 'tmp/next12_top1_pin_repair_20261015_v1/result.json': 'fd3736ae58120760364e32dc6039b61ef44cc80265ed277cf375a58375d6e58a', 'tmp/next12_top1_pin_repair_20261015_v1/registration.json': '0f9d3b270c8322fd725a52ab3d3b0081a416b63558ed661ec72ee6e17ad9f0b8', 'tmp/next12_top1_pin_repair_20261015_v1/protected_after.json': 'eae1c2d83c249ac3ad9308dfa71fc38f23b760761972e35caf6d4a9c20a58b55', 'tmp/next12_top1_pin_repair_20261015_v1/top1/result.json': '4ce0e3c88a2a7cae26b2a510cb369a7a69f6ce4d6ca07d0b2f9c48be4c90e283', 'tmp/next12_top1_pin_repair_20261015_v1/top1/outcome.json': '74b8de41f91ca25a6e3fcbdc7c119b4e9c95a5d330069b572b900495215fd309', 'tmp/next12_final_combined_independent_20261015_v1.json': '56d33e614d9cec36fddabac880fa3f37e44324adc78a3a85269f17bb32eaa5f2'})


class StrategyValidationSourceError(RuntimeError):
    """Saved evidence is absent, changed, or inconsistent."""


def _require(condition):
    if not condition:
        raise StrategyValidationSourceError('Saved strategy validation evidence failed verification')


def _read_next_period(documents):
    original = documents[NEXT_BASE + '/result.json']
    registration = documents[NEXT_BASE + '/registration.json']
    repair = documents[NEXT_REPAIR + '/result.json']
    repair_registration = documents[NEXT_REPAIR + '/registration.json']
    check = documents[NEXT_READBACK]
    quantity = documents[NEXT_BASE + '/quantity/result.json']
    top1 = documents[NEXT_REPAIR + '/top1/result.json']
    _require(check['status'] == 'PASS_INDEPENDENT_SAVED_OUTPUT_ARITHMETIC')
    _require(check['successful_books'] == 2 and check['total_book_attempts'] == 3 and check['original_failed_top1_attempts'] == 1)
    _require(check['protected_unchanged'] is True and check['old_artifact_pins_verified'] == 551)
    _require(check['registration_sha256'] == PINS[NEXT_BASE + '/registration.json'])
    _require(check['result_sha256'] == PINS[NEXT_BASE + '/result.json'] and check['repair_result_sha256'] == PINS[NEXT_REPAIR + '/result.json'])
    _require(original['methods'][0] == quantity and original['methods'][1] == documents[NEXT_BASE + '/top1/result.json'])
    _require(original['book_calls'] == 2 and original['complete_books'] == 1 and original['denominator'] == 2)
    _require(original['methods'][1]['metrics']['valued_sessions'] == 0 and original['methods'][1]['metrics']['total_return'] is None)
    _require(repair['recovery'] == top1 and repair['quantity_reused_not_rerun'] is True and repair['original_failure_preserved'] is True)
    _require(repair['quantity_core_calls'] == 0 and repair_registration['methods'] == ['top1'] and repair_registration['maximum_quantity_core_calls'] == 0)
    _require(repair_registration['original_registration_sha256'] == PINS[NEXT_BASE + '/registration.json'])
    for name in ('result.json', 'quantity/result.json', 'quantity/outcome.json'):
        original_path = str(Path(repair_registration['original_directory']) / name)
        _require(repair_registration['original_artifact_hashes'][original_path] == PINS[NEXT_BASE + '/' + name])
    for base in (NEXT_BASE, NEXT_REPAIR):
        _require(documents[base + '/protected_after.json']['unchanged'] is True)
    _require(registration['session_dates'][0] == '2025-07-31' and registration['session_dates'][-1] == '2026-07-30' and len(registration['session_dates']) == 251)
    _require(registration['monthly_cash_reset'] is False and registration['initial_cash'] == '20000')
    _require(quantity['core_calls'] == 12 and top1['core_calls'] == 0 and top1['selector_calls'] == 12)
    rows = []
    reviewed = {row['method']: row for row in check['methods']}
    for name, saved, label in [('quantity', quantity, '真实净值月度重优化'), ('top1', top1, 'TOP1 单股月度对照')]:
        metrics = saved['metrics']; audit = reviewed[name]
        _require(saved['method'] == name and saved['book_calls'] == 1)
        _require(saved['independent_oos'] is False and saved['adoption_allowed'] is False)
        _require(metrics['status'] == 'COMPLETE' and metrics['complete_full_period'] is True and audit['complete'] is True)
        _require(metrics['terminal_state_valuation_synchronized'] is True and metrics['final_wealth_basis'] == 'REGULAR_CLOSE_CURRENT_STATE')
        _require(metrics['valued_sessions'] == audit['valued_sessions'] == 250 and metrics['annualization_basis']['calendar_days'] == 364)
        _require(Fraction(metrics['daily_close_maximum_drawdown']) == Fraction(audit['drawdown']) == Fraction(check['comparison'][name + '_drawdown']))
        _require(metrics['annualized_return'] == check['comparison'][name + '_annualized'])
        _require(Fraction(metrics['terminal_equity']) == Fraction(check['comparison'][name + '_terminal_equity']))
        _require(Fraction(metrics['total_return']) == Fraction(metrics['terminal_equity']) / 20000 - 1)
        rows.append(dict(mode=name, label=label, total_return=float(Fraction(metrics['total_return'])),
            annualized_return=metrics['annualized_return'], max_drawdown=float(Fraction(metrics['daily_close_maximum_drawdown']))))
    annual_gap = 100 * (rows[1]['annualized_return'] - rows[0]['annualized_return'])
    dd_gap = 100 * (rows[1]['max_drawdown'] - rows[0]['max_drawdown'])
    return dict(period=dict(start='2025-07-31', end='2026-07-30', calendar_days=364), modes=rows,
        successful_books=2, total_attempts=3, original_failed_attempts=1,
        conclusion=f'TOP1 年化收益高 {annual_gap:.2f} 个百分点，最大回撤也高 {dd_gap:.2f} 个百分点。',
        independent_oos=False, current_candidate_performance=False,
        note='2 个成功账本、3 次总尝试；原 TOP1 接线失败保留，组合未重跑。非独立样本外检验，不是当前推荐的收益。')


def read_current_strategy_validation():
    """Every call verifies disk bytes; no stale response cache or numeric fallback."""
    try:
        documents = {}
        for path, expected in PINS.items():
            raw = (ROOT / path).read_bytes()
            _require(hashlib.sha256(raw).hexdigest() == expected)
            if not path.endswith('/outcome.json'):
                documents[path] = json.loads(raw)
        result = documents[BASE + '/result.json']
        registration = documents[BASE + '/registration.json']
        readback = documents[READBACK]
        contract = documents[CONTRACT]
        _require(documents[BASE + '/protected_after.json']['unchanged'] is True)
        _require(readback['status'] == 'PASS_ALL_747_DAYS_ORDERS_AND_MONTHLY_TARGETS' and readback['protected_unchanged'] is True)
        _require(readback['result_sha256'] == PINS[BASE + '/result.json'] and readback['registration_sha256'] == PINS[BASE + '/registration.json'])
        _require(result['book_calls'] == result['denominator'] == 3 and result['search_calls'] == 0)
        _require(result['independent_oos'] is False and result['adoption_allowed'] is False and registration['monthly_cash_reset'] is False)
        _require([m['mode'] for m in result['modes']] == list(LABELS))
        reviewed = {m['mode']: m for m in readback['modes']}
        _require(set(reviewed) == set(LABELS))
        days = (date.fromisoformat(contract['end_close']) - date.fromisoformat(contract['start_close'])).days
        modes = []
        for summary in result['modes']:
            mode = summary['mode']
            metrics = documents[BASE + '/' + mode + '/metrics.json']
            check = reviewed[mode]
            _require(summary == dict(mode=mode, **metrics))
            _require(metrics['status'] == 'COMPLETE' and metrics['complete_full_period'] is True and check['status'] == 'PASS')
            _require(metrics['annualization_basis']['calendar_days'] == days)
            _require(check['outcome_sha256'] == PINS[BASE + '/' + mode + '/outcome.json'])
            for field, verified_field in (('total_return', 'return_fraction'), ('daily_close_maximum_drawdown', 'maximum_drawdown'), ('terminal_equity', 'terminal_equity')):
                _require(Fraction(metrics[field]) == Fraction(check[verified_field]))
            _require(metrics['annualized_return'] == check['annualized_return'])
            for field, verified_field in (('filled_orders', 'filled_orders'), ('expired_orders', 'expired_orders'), ('cash_wait_days', 'wait_cash_days'), ('unfinished_rebalance', 'unfinished_rebalance')):
                _require(metrics[field] == check[verified_field])
            modes.append(dict(mode=mode, label=LABELS[mode], status='COMPLETE',
                total_return=float(Fraction(metrics['total_return'])), annualized_return=metrics['annualized_return'],
                max_drawdown=float(Fraction(metrics['daily_close_maximum_drawdown'])), terminal_equity=float(Fraction(metrics['terminal_equity'])),
                filled_orders=metrics['filled_orders'], expired_orders=metrics['expired_orders'], cash_wait_days=metrics['cash_wait_days'],
                unfinished_rebalance=metrics['unfinished_rebalance'],
                exact=dict(total_return=metrics['total_return'], max_drawdown=metrics['daily_close_maximum_drawdown'], terminal_equity=metrics['terminal_equity'])))
        actual = documents[ACTUAL_BASE + '/result.json']
        actual_registration = documents[ACTUAL_BASE + '/registration.json']
        actual_check = documents[ACTUAL_READBACK]
        root_check = documents[ACTUAL_ROOT_READBACK]
        _require(documents[ACTUAL_BASE + '/protected_after.json']['unchanged'] is True)
        _require(actual_check['status'] == 'PASS_COMPLETE_INDEPENDENT_MONTHLY_CALLBACK_AND_LEDGER_READBACK')
        _require(root_check['status'] == 'PASS_COMPLETE')
        for name, fingerprint in actual_check['file_hashes'].items():
            _require(PINS[ACTUAL_BASE + '/' + name] == fingerprint)
        for name, fingerprint in root_check['source_hashes'].items():
            _require(PINS[ACTUAL_BASE + '/' + name] == fingerprint)
        _require(actual_check['callback_receipt_sha256'] == PINS[ACTUAL_CALLBACK_READBACK])
        _require(actual['book_calls'] == actual['denominator'] == actual_check['book_calls'] == 1)
        _require(actual['new_search_calls'] == actual_check['new_searches'] == 11 and actual['initial_search_reused'] is True and actual_check['initial_exact_reuse'] is True)
        _require(actual['independent_oos'] is False and actual['adoption_allowed'] is False and actual_check['result_supports_optimality'] is False)
        _require(actual_registration['monthly_cash_reset'] is False and Fraction(actual_registration['initial_cash']) == Fraction(registration['initial_cash_each']))
        metrics = actual['metrics']
        _require(metrics['status'] == 'COMPLETE' and metrics['complete_full_period'] is True and metrics['annualization_basis']['calendar_days'] == days)
        _require(Fraction(metrics['terminal_equity']) == Fraction(actual_check['terminal_equity_exact']) == Fraction(root_check['final_equity']))
        _require(Fraction(metrics['daily_close_maximum_drawdown']) == Fraction(actual_check['maximum_drawdown_exact']))
        _require(float(Fraction(metrics['daily_close_maximum_drawdown'])) == root_check['max_drawdown'])
        _require(metrics['annualized_return'] == actual_check['annualized_return'] == root_check['annualized_return'])
        _require(Fraction(metrics['total_return']) == Fraction(metrics['terminal_equity']) / Fraction(actual_registration['initial_cash']) - 1)
        for field, checked in [('filled_orders','fills_verified'),('expired_orders','expired_verified'),('cash_wait_days','cash_wait_days'),('provider_callbacks','callbacks'),('valued_sessions','daily_ledgers')]:
            _require(metrics[field] == actual_check[checked])
        modes.insert(0, dict(mode='ACTUAL_EQUITY_FRESH_QUANTITY_MONTHLY',label='真实净值月度重优化',status='COMPLETE',
            total_return=float(Fraction(metrics['total_return'])),annualized_return=metrics['annualized_return'],
            max_drawdown=float(Fraction(metrics['daily_close_maximum_drawdown'])),terminal_equity=float(Fraction(metrics['terminal_equity'])),
            filled_orders=metrics['filled_orders'],expired_orders=metrics['expired_orders'],cash_wait_days=metrics['cash_wait_days'],unfinished_rebalance=metrics['unfinished_rebalance'],
            exact=dict(total_return=metrics['total_return'],max_drawdown=metrics['daily_close_maximum_drawdown'],terminal_equity=metrics['terminal_equity'])))
        return dict(status='AVAILABLE', research_only=True, execution_blocked=True, independent_oos=False,
            promotion_allowed=False, validation_stage='ACTUAL_EQUITY_MONTHLY_AND_PRIOR_REPLAY_INDEPENDENTLY_CHECKED',
            period=dict(start=contract['start_close'], end=contract['end_close'], calendar_days=days),
            initial_cash=float(Fraction(registration['initial_cash_each'])), currency='USD', return_units='FRACTION_ONE_EQUALS_100_PERCENT',
            quantity_v2_period=read_quantity_v2_validation(root=ROOT), latest_period=_read_next_period(documents), modes=modes, conclusion=(f'真实净值月度重优化本期折年化 {modes[0]["annualized_return"]:.4%}，最大回撤 {modes[0]["max_drawdown"]:.4%}；'
                '收益低于 QQQ，回撤也更深。旧单股对照收益更高，但回撤仍约56.5%；本期结果不证明当前策略最优或已适用。'),
            limitations=['历史条件价格与日线触价成交假设，不是券商真实成交。', '非独立样本外检验，不含完整股息总回报；折年化仅描述该连续期间，不是未来预测。', '不改变生产准入、交易账户或当前持仓。'],
            source_fingerprints=dict(PINS), calculation_calls=0, search_calls=0)
    except StrategyValidationSourceError:
        raise
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError) as error:
        raise StrategyValidationSourceError('Saved strategy validation evidence unavailable') from error
