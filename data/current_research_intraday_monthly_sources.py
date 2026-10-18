"""Read-only saved training + journal capital bridge; no selection activation.

The server owns the bundle path and expected hash. Byte consistency does not
authenticate universe membership, corporate actions or the training admission.
"""
from hashlib import sha256
import json
from pathlib import Path

from data.current_research_intraday_buy_plan import _require
from data.current_research_intraday_continuation_ledger import review_continuation_ledger
from data.current_research_intraday_mark_sources import review_journal_holding_marks
from data.current_research_monthly_retarget_capital import build_monthly_retarget_capital
from data.current_research_intraday_monthly_selection import build_intraday_monthly_top1_selection


def review_saved_intraday_monthly_selection(state, *, root, holding_inputs,
        training_path, training_sha256, now):
    """Read one server-pinned bundle, reconstruct capital, run declared TOP1 once.

    No network, persistence, live orders or automatic source admission. Source
    files outside the workspace, changed bytes and conflicting pins are rejected.
    """
    base = Path(root).resolve()

    def read(name, expected):
        _require(isinstance(name, str) and name and '\\' not in name, 'INVALID_SOURCE_PATH')
        path = Path(name)
        _require(not path.is_absolute() and not path.drive and '..' not in path.parts, 'SOURCE_OUTSIDE_ROOT')
        full = (base / path).resolve()
        _require(full.is_relative_to(base) and full.stat().st_size <= 32 * 1024 * 1024, 'SOURCE_OUTSIDE_ROOT_OR_TOO_LARGE')
        raw = full.read_bytes()
        _require(sha256(raw).hexdigest() == expected, 'SOURCE_HASH_MISMATCH:' + name)
        return raw

    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, 'DUPLICATE_JSON_FIELD')
            result[key] = value
        return result

    bundle = json.loads(read(training_path, training_sha256), object_pairs_hook=unique)
    _require(set(bundle) == {'schema', 'training_input', 'selection_calendar', 'target_month', 'source_hashes'}
        and bundle['schema'] == 'SAVED_INTRADAY_MONTHLY_TOP1_INPUT_V1', 'TRAINING_BUNDLE_SCHEMA')
    pins = bundle['source_hashes']
    _require(isinstance(pins, dict) and pins, 'TRAINING_SOURCE_PINS_REQUIRED')
    for name, digest in pins.items():
        read(name, digest)
    selector = 'backtest/return_priority_monthly_top1_selector.py'
    _require(pins.get(selector) == sha256((Path(__file__).resolve().parents[1] / selector).read_bytes()).hexdigest(), 'RUNNING_SELECTOR_SOURCE_MISMATCH')
    _require(training_path not in pins or pins[training_path] == training_sha256, 'SOURCE_PIN_CONFLICT')
    pins = dict(pins, **{training_path: training_sha256})
    _require('root' not in holding_inputs and 'now' not in holding_inputs, 'HOLDING_INPUT_SCHEMA')
    state = review_continuation_ledger(state)
    source = review_journal_holding_marks(state, root=root, now=now, **holding_inputs)
    proposal = state['acceptance']['proposal']
    quotes, units = [], {}
    for sid, mark in source['marks'].items():
        quotes.append(dict(security_id=sid, ticker=proposal['security']['ticker'], currency='USD',
            price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS', price_kind='REGULAR_MARKET_LAST',
            price=mark['price'], quoted_at=mark['observed_at'], captured_at=mark['received_at'],
            source_references=mark['source_references']))
        units[sid] = dict(source['unit_continuity'], quote_source_references=mark['source_references'])
    capital_inputs = dict(expected_revision=state['revision'],
        initial_capital_identity=dict(account_id=state['account_id'], initial_acceptance_id=state['acceptance_id'],
            initial_proposal_id=proposal['proposal_id'], initial_research_id=proposal['research_id'],
            initial_cash=proposal['causal_inputs']['available_cash']),
        valuation_quotes=quotes, unit_continuity=units, source_hashes=source['source_hashes'],
        market_session=holding_inputs['market_session'])
    capital = build_monthly_retarget_capital(state, now=now, **capital_inputs)
    _require(capital['status'] == 'READY', 'CAPITAL_UNAVAILABLE:' + str(capital.get('reason')))
    for name, digest in source['source_hashes'].items():
        _require(name not in pins or pins[name] == digest, 'SOURCE_PIN_CONFLICT')
        pins[name] = digest
    result = build_intraday_monthly_top1_selection(state, capital=capital, capital_inputs=capital_inputs,
        training_input=bundle['training_input'], target_month=bundle['target_month'],
        selection_calendar=bundle['selection_calendar'], source_hashes=pins, now=now)
    if result['status'] == 'READY':
        result.update(source_bytes_verified=True, training_bundle_sha256=training_sha256,
            complete_corporate_actions_verified=False, universe_completeness_authenticated=False)
    return result
