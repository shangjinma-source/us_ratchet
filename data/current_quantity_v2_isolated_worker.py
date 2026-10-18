"""Isolated-interpreter entry: execute only pinned local module source bytes.

Invoked via python -I -S -c <this verified source>; never reads project files.
The interpreter/stdlib are the trusted runtime, not part of the local code pins.
"""
import base64
import hashlib
import importlib.abc
import importlib.util
import json
import sys


def main():
    raw_request = sys.stdin.buffer.read(192 * 1024 * 1024 + 1)
    if len(raw_request) > 192 * 1024 * 1024:
        raise ValueError('V2_WORKER_REQUEST_TOO_LARGE')
    request = json.loads(raw_request)
    sources = request['sources']; pins = request['pins']
    if not isinstance(sources, dict) or len(sources) > 100:
        raise ValueError('V2_WORKER_GRAPH_LIMIT')
    raw_sources = {}; total = 0
    for name, encoded in sources.items():
        if not isinstance(encoded, str) or len(encoded) > 45 * 1024 * 1024:
            raise ValueError('V2_WORKER_SOURCE_LIMIT')
        raw = base64.b64decode(encoded, validate=True)
        total += len(raw)
        if len(raw) > 32 * 1024 * 1024 or total > 128 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != pins[name]:
            raise ValueError('V2_WORKER_SOURCE_HASH_OR_SIZE')
        raw_sources[name] = raw
    loaded = {}

    class FrozenLocal(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] not in ('data', 'backtest', 'scripts'):
                return None
            package = fullname in ('data', 'backtest', 'scripts')
            name = fullname.replace('.', '/') + ('/__init__.py' if package else '.py')
            if name not in sources or name not in pins:
                raise ImportError('V2_UNPINNED_LOCAL_DEPENDENCY:' + name)
            return importlib.util.spec_from_loader(fullname, self, is_package=package)

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            package = module.__name__ in ('data', 'backtest', 'scripts')
            name = module.__name__.replace('.', '/') + ('/__init__.py' if package else '.py')
            raw = raw_sources[name]
            actual = hashlib.sha256(raw).hexdigest()
            if actual != pins[name]:
                raise ValueError('V2_WORKER_SOURCE_HASH_MISMATCH:' + name)
            loaded[name] = actual
            module.__file__ = '/pinned_v2/' + name
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)

    sys.meta_path.insert(0, FrozenLocal())
    # Import-only dependency of the legacy validator/projector. Never execute it.
    from backtest import return_priority_fresh_cash_quantity_search as legacy
    def forbidden(*args, **kwargs):
        raise ValueError('V2_LEGACY_CORE_EXECUTION_FORBIDDEN')
    legacy.search_fresh_cash_quantities = forbidden
    from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
    from data.current_quantity_projection_v2 import project_capital_decision_v2
    decision = decide_quantity_v2_for_account(**request['arguments'])
    view = project_capital_decision_v2(decision)
    sys.stdout.buffer.write(json.dumps(dict(decision=decision, view=view, loaded_source_hashes=loaded),
                                      ensure_ascii=False, allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    main()
