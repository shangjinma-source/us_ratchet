"""Unmounted continuous32 composition using split-aware inputs and journal.

Private function bindings preserve the original search and result validation.
No module monkeypatch, production registration or source admission is implied.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from types import FunctionType

from core.strategy_account_ledger import require
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data import strategy_continuous32_target_decision as decision
from data import strategy_continuous32_target_service as service
from docs.candidates.strategy_account_split_target_inputs import build_target_inputs
from docs.candidates.strategy_account_split_scoped_preview import preview_scoped_account
from docs.candidates.strategy_account_split_target_service import MINIMUM_RUNTIME_PATHS as SPLIT_PATHS
from docs.candidates.strategy_split_monthly_target_service import StrategyMonthlyTargetService, LIFECYCLE_PATHS

PATH = 'docs/candidates/split_continuous32_integration_20261105.py'
RUNTIME_PATHS = service.MINIMUM_RUNTIME_PATHS | SPLIT_PATHS | LIFECYCLE_PATHS | {PATH}
# LF-normalized source identity; existing runtime pins still bind exact bytes.
ORIGINAL_SOURCE_HASHES = {
    'data/strategy_continuous32_target_decision.py': 'd1e1fcdb225ce916ac92b91356ae653871daee95d956dfa562b2b2189efab995',
    'data/strategy_continuous32_target_service.py': '43112d15e7ae398f7af5219b404c21a399c09f605b4a861ccbccb10a3472c70f',
}


def _bind(function, **dependencies):
    namespace = dict(function.__globals__, **dependencies)
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


decide_target = _bind(decision.decide_target, build_target_inputs=build_target_inputs)
preview_target = _bind(service.preview_target, preview_scoped_account=preview_scoped_account)


class SplitContinuous32TargetService(service.StrategyContinuous32TargetService):
    _generate = _bind(service.StrategyContinuous32TargetService._generate,
                      decide_target=decide_target, MINIMUM_RUNTIME_PATHS=RUNTIME_PATHS)
    _preview = _bind(service.StrategyContinuous32TargetService._preview, preview_target=preview_target)

    def __init__(self, **arguments):
        require(type(arguments['store']) is SplitStrategyAccountStore, 'SPLIT_ACCOUNT_STORE_REQUIRED')
        require(RUNTIME_PATHS <= set(arguments['runtime_pins']), 'SPLIT_CONTINUOUS32_PINS_REQUIRED')
        super().__init__(**arguments)

    def _pins(self):
        super()._pins()
        root = Path(__file__).resolve().parents[2]
        for name, expected in ORIGINAL_SOURCE_HASHES.items():
            require(sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() == expected,
                    'ORIGINAL_CONTINUOUS32_FUNCTION_CHANGED')
        for name in RUNTIME_PATHS:
            require(sha256((root / name).read_bytes()).hexdigest() == self.pins[name],
                    'EXECUTING_SPLIT_CONTINUOUS32_SOURCE_CHANGED')


class SplitContinuous32MonthlyService(StrategyMonthlyTargetService):
    @contextmanager
    def snapshot_operation(self):
        # Same reentrant lock used by the inherited real publication method.
        with self.lock:
            yield
