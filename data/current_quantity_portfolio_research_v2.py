"""DI-only cash research snapshots. No production input, singleton or API mount.

source_loader is server-owned admission configuration, not a client payload.
Default calculation and projection execute pinned source bytes in an isolated
interpreter. Optional search is a test-only capital-decision callable, not a bare
quantity core. File hashes certify local bytes, not external source authenticity.
"""
from copy import deepcopy
from fractions import Fraction
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import base64
import subprocess
import sys
from threading import RLock

from data.current_cash_portfolio_research import normalize_cash, ResearchExpiredError
from data.current_portfolio_preview import _group_bars
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.current_research_capital_decision_v2 import VERSION, REQUIRED_PINS
from data.current_quantity_projection_v2 import project_capital_decision_v2

RESEARCH_VERSION = 'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
WORKER = 'data/current_quantity_v2_isolated_worker.py'
WORKER_SHA256 = '47bec1154a2c2e019e09f9744a413ecbc6cb85a5c224edf02e45eb60381c206f'
WORKER_DEPENDENCIES = (
    'data/__init__.py', 'backtest/__init__.py', 'scripts/__init__.py',
    *REQUIRED_PINS, 'backtest/return_priority_fresh_cash_quantity_search.py',
    'data/current_quantity_projection_v2.py', 'data/current_quantity_portfolio_research.py',
    'data/current_cash_portfolio_research.py', 'data/current_portfolio_preview.py',
    'scripts/return_priority_latest_saved_snapshot_research.py',
    'backtest/return_priority_exact_floor_ceil_research.py',
    'backtest/return_priority_joint_candidate_generator_research.py',
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                            ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class CurrentQuantityPortfolioResearchV2:
    def __init__(self, *, root, source_loader=None, search=None, test_mode=False):
        self.root = Path(root).resolve()
        self.loader = source_loader
        require(search is None or test_mode is True, 'V2_CUSTOM_SEARCH_TEST_MODE_REQUIRED')
        self.search = search
        self.test_mode = test_mode
        self.lock = RLock()
        self.snapshots = {}
        self.keys = {}
        self.failures = set()

    def _load(self):
        require(callable(self.loader), 'V2_SOURCE_ADMISSION_UNAVAILABLE')
        descriptor = deepcopy(self.loader())
        require(isinstance(descriptor, dict) and set(descriptor) ==
                {'input_path', 'admission_path', 'source_hashes'}, 'V2_SOURCE_DESCRIPTOR_INVALID')
        pins = descriptor['source_hashes']
        require(isinstance(pins, dict) and 0 < len(pins) <= 2000, 'V2_SOURCE_PINS_REQUIRED')
        files = {}; total = 0
        for name, expected in pins.items():
            require(isinstance(name, str) and name and '\\' not in name and ':' not in name
                    and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                    'V2_SOURCE_PATH_INVALID')
            require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'V2_SOURCE_HASH_INVALID')
            path = (self.root / name).resolve()
            require(path.is_relative_to(self.root), 'V2_SOURCE_OUTSIDE_ROOT')
            size = path.stat().st_size
            require(size <= 32 * 1024 * 1024 and total + size <= 128 * 1024 * 1024, 'V2_SOURCE_SIZE_LIMIT')
            raw = path.read_bytes(); total += len(raw)
            require(len(raw) == size and total <= 128 * 1024 * 1024 and sha256(raw).hexdigest() == expected,
                    'V2_SOURCE_HASH_MISMATCH')
            files[name] = raw
        require(descriptor['input_path'] in files and descriptor['admission_path'] in files,
                'V2_INPUT_ADMISSION_NOT_PINNED')
        admission = json.loads(files[descriptor['admission_path']])
        require(admission.get('status') == 'ADMITTED_CASH_RESEARCH_V2'
                and admission.get('method') == VERSION
                and admission.get('input_path') == descriptor['input_path']
                and admission.get('input_sha256') == pins[descriptor['input_path']], 'V2_INPUT_NOT_ADMITTED')
        data = json.loads(files[descriptor['input_path']])
        require(set(data) == {'search_arguments', 'valuation_quotes', 'bar_sources'}, 'V2_INPUT_SCHEMA')
        require(all(name in files for name in (*WORKER_DEPENDENCIES, WORKER)), 'V2_IMPLEMENTATION_CLOSURE_MISSING')
        require(pins[WORKER] == WORKER_SHA256, 'V2_BOOTSTRAP_VERSION_MISMATCH')
        for name in (*REQUIRED_PINS, 'backtest/return_priority_fresh_cash_quantity_search.py'):
            require(name in files, 'V2_METHOD_NOT_PINNED')
            require(sha256((Path(__file__).resolve().parent.parent / name).read_bytes()).hexdigest() == pins[name],
                    'V2_LOADED_METHOD_PIN_MISMATCH')
        args = data['search_arguments']; domain = set(args['prices'])
        quotes = data['valuation_quotes']
        require(isinstance(quotes, list) and all(isinstance(q, dict) for q in quotes), 'V2_VALUATION_QUOTES_INVALID')
        marks = {q['security_id']: q for q in quotes}
        require(len(marks) == len(quotes) and domain <= set(marks), 'V2_VALUATION_QUOTE_DOMAIN')
        require(set(data['bar_sources']) == domain, 'V2_BAR_SOURCE_DOMAIN')
        require(len({args['metadata'][sid]['ticker'] for sid in domain}) == len(domain), 'V2_AMBIGUOUS_TICKER')
        channels = {}
        for sid, source in data['bar_sources'].items():
            require(set(source) == {'path', 'price_basis'} and source['path'] in files
                    and isinstance(source['price_basis'], str) and source['price_basis'], 'V2_BAR_SOURCE_NOT_PINNED')
            channels[sid] = parse_provider_ohlc(files[source['path']], args['metadata'][sid]['ticker'])
            require(args['decision_date'] in channels[sid]['dates'], 'V2_DECISION_BAR_MISSING')
            index = channels[sid]['dates'].index(args['decision_date'])
            values = channels[sid]['values'][index][:4]
            require(all(v is not None and v > 0 for v in values), 'V2_DECISION_OHLC_INCOMPLETE')
            opened, high, low, closed = values
            require(low <= min(opened, closed) <= max(opened, closed) <= high, 'V2_DECISION_OHLC_ORDERING')
            # Compare original JSON decimals, not rounded display/float coordinates.
            raw = files[source['path']]
            decoded = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw, parse_float=Decimal)
            exact_close = decoded['chart']['result'][0]['indicators']['quote'][0]['close'][index]
            mark = marks[sid]
            require(source['price_basis'] == args['price_basis'] == mark['price_basis']
                    and mark['as_of'] == args['decision_date'], 'V2_DECISION_PRICE_BASIS_MISMATCH')
            require(Fraction(str(exact_close)) == Fraction(args['prices'][sid]) == Fraction(mark['price']),
                    'V2_DECISION_PRICE_COORDINATE_MISMATCH')
        return descriptor, data, channels, files

    def calculate(self, entered_cash):
        amount = normalize_cash(entered_cash)
        with self.lock:
            descriptor, data, channels, files = self._load()
            source_id = digest(dict(version=RESEARCH_VERSION, method=VERSION, source=descriptor))
            key = digest(dict(source_id=source_id, cash=amount, shares={}))
            require(key not in self.failures, 'V2_PRIOR_ATTEMPT_FAILED_NO_AUTOMATIC_RETRY')
            if key in self.keys:
                view = deepcopy(self.snapshots[self.keys[key]]['view'])
                view.update(cache_hit=True, generator_calls_this_request=0)
                return view
            require(len(self.snapshots) < 32, 'V2_SNAPSHOT_CAPACITY_REACHED')
            args = data['search_arguments']; day = args['decision_date']
            try:
                arguments = dict(decision_date=day,
                    account_state=dict(asof=day, revision=source_id, cash=amount, shares={}, reserved_cash='0'),
                    valuation_quotes=deepcopy(data['valuation_quotes']), source_hashes=deepcopy(descriptor['source_hashes']),
                    search_arguments=deepcopy(args))
                if self.search is not None:
                    decision = self.search(**arguments)
                    view = project_capital_decision_v2(decision)
                    loaded = {}
                else:
                    request = dict(arguments=arguments, pins=descriptor['source_hashes'],
                        sources={name: base64.b64encode(files[name]).decode('ascii') for name in WORKER_DEPENDENCIES})
                    encoded_request = json.dumps(request, allow_nan=False).encode()
                    require(len(encoded_request) <= 192 * 1024 * 1024, 'V2_WORKER_REQUEST_TOO_LARGE')
                    completed = subprocess.run([sys.executable, '-I', '-S', '-c', files[WORKER].decode('utf-8-sig')],
                        input=encoded_request, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=300, check=False)
                    require(completed.returncode == 0, 'V2_ISOLATED_WORKER_FAILED:' + completed.stderr.decode('utf-8', errors='replace')[-1500:])
                    require(len(completed.stdout) <= 32 * 1024 * 1024, 'V2_WORKER_RESULT_TOO_LARGE')
                    output = json.loads(completed.stdout)
                    decision, view, loaded = output['decision'], output['view'], output['loaded_source_hashes']
                    require(loaded == {name: descriptor['source_hashes'][name] for name in WORKER_DEPENDENCIES},
                            'V2_LOADED_IMPLEMENTATION_CLOSURE_MISMATCH')
                expected_args = deepcopy(args)
                expected_args.pop('quote_as_of'); expected_args.pop('price_basis')
                expected_args['entered_cash'] = str(Fraction(amount))
                require(decision['binding']['shares'] == {} and decision['binding']['state_revision'] == source_id
                        and Fraction(decision['available_cash']) == Fraction(amount)
                        and decision['binding']['search_arguments'] == expected_args
                        and decision['binding']['source_hashes'] == descriptor['source_hashes'], 'V2_DECISION_SOURCE_OR_CASH_MISMATCH')
                require(self._load()[0] == descriptor, 'V2_SOURCE_CHANGED_DURING_SEARCH')
                decision_id = decision['decision_id']
                require(type(decision_id) is str and len(decision_id) == 64
                        and all(c in '0123456789abcdef' for c in decision_id)
                        and decision_id[:24] == view['research_id'], 'V2_DECISION_ID_MISMATCH')
                view.update(research_version=RESEARCH_VERSION, cache_hit=False, generator_calls_this_request=1,
                    decision_id=decision_id,
                    frozen_dollar_allocations_exact={
                        sid: str(quantity * Fraction(expected_args['prices'][sid]))
                        for sid, quantity in (decision['target_quantities'] or {}).items() if quantity > 0},
                    implementation_mode='TEST_ONLY_IN_PROCESS_DI' if self.search is not None else 'ISOLATED_PINNED_SOURCE_BYTES',
                    implementation_source_hashes=dict(loaded, **{WORKER: descriptor['source_hashes'][WORKER]}) if loaded else {},
                    origin='ADMITTED_V2_CASH_ONLY_SEARCH', input_sha256=descriptor['source_hashes'][descriptor['input_path']],
                    source_binding_id=source_id, sources=deepcopy(descriptor['source_hashes']))
                rid = view['research_id']
                require(rid not in self.snapshots, 'V2_SNAPSHOT_ID_COLLISION')
                self.snapshots[rid] = deepcopy(dict(view=view, decision=decision, descriptor=descriptor, channels=channels, data=data))
                self.keys[key] = rid
                return deepcopy(view)
            except Exception:
                self.failures.add(key)
                raise

    def _snapshot(self, research_id):
        if research_id not in self.snapshots:
            raise ResearchExpiredError('V2 snapshot unknown; explicit cash calculation required')
        value = self.snapshots[research_id]
        require(self._load()[0] == value['descriptor'], 'V2_SNAPSHOT_SOURCE_CHANGED')
        return value

    def snapshot(self, research_id):
        with self.lock:
            return deepcopy(self._snapshot(research_id)['view'])

    def decision(self, research_id):
        """Server-private original worker decision; source-checked, never recalculated.

        This is not an HTTP projection or a full-account adoption mandate. The
        cached decision retains the original CASH_ONLY capital binding.
        """
        with self.lock:
            return deepcopy(self._snapshot(research_id)['decision'])

    def bars(self, research_id, ticker, interval='day', bars=90):
        require(isinstance(ticker, str) and interval in ('day', 'week', 'month')
                and type(bars) is int and 1 <= bars <= 260, 'V2_BAR_ARGUMENTS')
        with self.lock:
            saved = self._snapshot(research_id); view = saved['view']
            rows = [stock for stock in view['stocks'] if stock['ticker'] == ticker]
            require(len(rows) == 1, 'V2_BAR_NOT_SELECTED')
            sid = rows[0]['security_id']; source = saved['data']['bar_sources'][sid]
            daily = []; missing = []
            channel = saved['channels'][sid]
            for day, values in zip(channel['dates'], channel['values']):
                if day > view['as_of']:
                    continue
                if any(v is None for v in values[:4]):
                    missing.append(day)
                else:
                    daily.append(dict(zip(('date', 'open', 'high', 'low', 'close', 'volume'), [day] + values)))
            return dict(status='AVAILABLE', research_id=research_id, research_version=RESEARCH_VERSION,
                security_id=sid, ticker=ticker, interval=interval, as_of=view['as_of'], daily_as_of=view['as_of'],
                currency='USD', research_only=True, execution_blocked=True,
                bars=_group_bars(daily, interval)[-bars:], no_missing_fill=True,
                missing_sessions=missing, missing_session_count=len(missing), last_period_may_be_partial=interval != 'day',
                price_basis=source['price_basis'], adjustment_basis=source['price_basis'], limit_line_coordinate_confirmed=False,
                source=source['path'], source_sha256=saved['descriptor']['source_hashes'][source['path']])
