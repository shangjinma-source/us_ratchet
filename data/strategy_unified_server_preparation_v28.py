"""Versioned historical replay optimization over the unchanged V27 policy."""
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v27 import build_unified_server_preparation_v27
from data.strategy_profiled_release_snapshot_replayed_v1 import SOURCES as REPLAY_SOURCES
from data.strategy_replayed_snapshot_install_v1 import install_replayed_snapshot

SOURCES = REPLAY_SOURCES | {'data/strategy_unified_server_preparation_v28.py',
                            'api/strategy_server_mount_v7.py', 'api/server.py'}


def build_unified_server_preparation_v28(*, root, configuration_path,
                                       configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = _read(root, reference)
    require(set(configuration) == {'schema', 'base_v27', 'source_pins'}
        and configuration['schema'] == 'VERIFIED_REPLAY_UNIFIED_PREPARATION_V28',
        'V28_CONFIGURATION')
    pins = configuration['source_pins']
    require(type(pins) is dict and set(pins) == SOURCES, 'V28_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]

    def validate():
        require(_read(root, reference)[0] == raw, 'V28_CONFIGURATION_CHANGED')
        for name, expected in pins.items():
            for base in (root, executing):
                require(_read_digest(base / name, 32*1024*1024) == expected,
                        'V28_SOURCE_CHANGED')

    validate()
    base = configuration['base_v27']
    _, base_configuration = _read(root, base)
    prepared = build_unified_server_preparation_v27(root=root,
        configuration_path=base['path'], configuration_sha256=base['sha256'], clock=clock)
    previous_gate = prepared['validate_code']

    def gate():
        previous_gate()
        validate()

    install_replayed_snapshot(prepared=prepared, root=root,
        upgrade_reference=base_configuration['snapshot_read_upgrade'],
        source_pins=pins, validate_sources=gate)
    gate()
    return dict(prepared, validate_code=gate, replay_optimization_enabled=True)
