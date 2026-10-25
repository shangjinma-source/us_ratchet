"""First daily source review bound to a verified paper selection and replayed book."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from backtest.current_strategy_prospective_paper_book_v2 import replay, _context
from core.strategy_account_ledger import canonical, require
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_daily_session_capture import pinned, stamp
from data.strategy_paper_application_descriptor_v2 import NY
from data.strategy_paper_execution_preview_v1 import _local_import_closure
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target
from data.strategy_paper_first_window_core_v2 import review_source_window

SOURCE = 'data/strategy_prospective_paper_first_window_v2.py'
CODE_PATHS = _local_import_closure({SOURCE, 'data/strategy_paper_first_window_capture_v2.py'})


def verified_first_window_context(*, root, configuration_bytes, configuration_sha256,
        capture_files, book, authority, admitted_decisions, admitted_settlements,
        selection_result, selection_arguments, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    began = stamp(clock())
    root = Path(root).absolute()
    original = deepcopy((book, authority, selection_result, selection_arguments, capture_files))
    app = _context(authority, began)
    require(CODE_PATHS <= set(app['code_sha256']), 'PAPER_FIRST_CODE_SCOPE')
    require(selection_arguments['authority'] == authority, 'PAPER_FIRST_AUTHORITY')
    selected = verify_prospective_target(selection_result, **selection_arguments)
    current = replay(book, authority=authority, admitted_decisions=admitted_decisions,
                     admitted_settlements=admitted_settlements)
    previous = replay(selection_arguments['book'], authority=authority,
        admitted_decisions=selection_arguments['admitted_decisions'],
        admitted_settlements=selection_arguments.get('admitted_settlements'))
    require(previous['registration_sha256'] == current['registration_sha256'] and
            previous['descriptor_sha256'] == current['descriptor_sha256'] and
            previous['operations'] == current['operations'][:len(previous['operations'])],
            'PAPER_FIRST_ANCESTRY')
    require(began >= max(stamp(current['last_available_at']),
                        stamp(selection_result['payload']['computation_finished_at'])),
            'PAPER_FIRST_STATE_FUTURE')
    require(sha256(configuration_bytes).hexdigest() == configuration_sha256, 'FIRST_CONFIG_HASH')
    config = json.loads(configuration_bytes)
    require(config.get('schema') == 'PAPER_FIRST_DAILY_WINDOW_V2' and
            config.get('release_sha256') is None, 'PAPER_FIRST_CONFIG_SCHEMA')
    sid = config['security_id']
    needed = {s for s, q in selected['target_quantities'].items() if q} | set(current['shares']) | {
        order['security_id'] for order in current['orders'].values() if order['closed'] is None}
    require(sid in needed, 'PAPER_FIRST_SECURITY_NOT_NEEDED')
    binding = selection_result['payload']['input_binding']
    epoch = stamp(binding['valuation_at']).astimezone(NY).date().isoformat()
    require(config['monthly_decision_date'] == epoch, 'PAPER_FIRST_EPOCH')
    require(pinned(root, config['calendar']) == authority['descriptor_arguments']['calendar_bytes'],
            'PAPER_FIRST_CALENDAR')
    package = selection_arguments['source_package']
    review_path = selection_arguments['unit_review_path']
    units = json.loads(package['files'][review_path])
    unit = units['securities'][sid]
    mark = binding['marks'][sid]
    require(unit['security_id'] == sid and unit['current_mark_sha256'] == sha256(canonical(mark)).hexdigest()
            and unit['held_quantities_in_current_units'] is True
            and unit['historical_scenarios_usable_in_current_units'] is True,
            'PAPER_FIRST_UNIT_BINDING')
    manifest = json.loads(pinned(root, config['identity']))
    candidates = [row for row in manifest['candidates'] if row.get('security_id') == sid]
    require(len(candidates) == 1, 'PAPER_FIRST_IDENTITY_NOT_UNIQUE')
    identity = PinnedStrategyIdentity(root, config['identity']['path'], config['identity']['sha256'])(candidates[0]['ticker'])
    require(identity['security_id'] == sid, 'PAPER_FIRST_IDENTITY')
    references = {name: package['source_hashes'][name] for name in unit['source_references']}
    baseline = dict(unit=deepcopy(unit), reviewed_at=units['reviewed_at'], source_hashes=references,
        review_reference=dict(path=review_path, sha256=package['source_hashes'][review_path]))
    result = dict(root=root, configuration_bytes=configuration_bytes,
        configuration_sha256=configuration_sha256, capture_files=capture_files,
        account_id=current['account_id'], account_revision=current['revision'],
        target_id=selected['target_id'], target_month=selected['target_month'],
        target_quantities=selected['target_quantities'],
        entry=dict(security_id=sid, ticker=identity['ticker'], identity=identity, unit_baseline=baseline),
        baseline_files=package['files'], clock=clock, began=began)
    require((book, authority, selection_result, selection_arguments, capture_files) == original,
            'PAPER_FIRST_INPUT_CHANGED')
    _context(authority, stamp(clock()))
    return result


def review_paper_first_window(**arguments):
    original = deepcopy(arguments)
    context = verified_first_window_context(**arguments)
    result = review_source_window(**context)
    require(arguments == original, 'PAPER_FIRST_INPUT_CHANGED')
    _context(arguments['authority'], stamp(context['clock']()))
    return result
