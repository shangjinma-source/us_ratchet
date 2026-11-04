"""Install the equivalent snapshot reader without changing release or targets."""
from pathlib import Path
from core.strategy_account_ledger import require
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation as Original
from data.strategy_profiled_release_snapshot_replayed_v1 import ProfiledMonthlyReleaseActivation, SOURCES
from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
from scripts.prepare_real_monthly_release import _read


def install_replayed_snapshot(*, prepared, root, upgrade_reference, source_pins, validate_sources):
    root = Path(root).resolve()
    original = prepared['activation']
    monthly = prepared['monthly']
    require(isinstance(original, Original) and original.root.resolve() == root,
            'SIZED_SNAPSHOT_ORIGINAL_ACTIVATION_REQUIRED')
    require(type(upgrade_reference) is dict and set(upgrade_reference) == {'path', 'sha256'},
            'SIZED_SNAPSHOT_UPGRADE_REFERENCE_REQUIRED')
    validate_sources()
    package = _read(root, upgrade_reference['path'], upgrade_reference['sha256'])
    require(package['schema'] == 'CONTINUOUS32_RESEARCH_UPGRADE_V1', 'SIZED_SNAPSHOT_UPGRADE_REQUIRED')
    activation = ProfiledMonthlyReleaseActivation(root=root, initial_snapshot=original.initial,
        legacy_anchor=original.legacy_anchor, clock=original.clock, validate_code=validate_sources,
        reader_source_pins={name: source_pins[name] for name in SOURCES})
    provider = upgrade_handoff_snapshot_provider(root=root,
        package_path=upgrade_reference['path'], package_sha256=upgrade_reference['sha256'],
        base_provider=activation.snapshot, target_provider=monthly.targets.current,
        validate_code=validate_sources)
    # Validate the same archive/upgrade handoff before replacing the read path.
    provider()
    with monthly.lock:
        require(monthly._active_snapshot is None and not monthly._loading_snapshot,
                'SIZED_SNAPSHOT_OPERATION_ACTIVE')
        monthly._snapshot_provider = provider
    prepared['activation'] = activation
    return activation
