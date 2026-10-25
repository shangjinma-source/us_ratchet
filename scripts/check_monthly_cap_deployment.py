"""Read-only preflight against the currently registered V21 account target."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from data.monthly_cap_target_view import capped_target_view
from data.strategy_unified_server_preparation_v21 import build_unified_server_preparation_v21


def inspect(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'config/strategy_server_active.json').read_bytes())
    configuration = root/manifest['configuration_path']
    if sha256(configuration.read_bytes()).hexdigest() != manifest['configuration_sha256']:
        raise ValueError('ACTIVE_CONFIGURATION_CHANGED')
    if json.loads(configuration.read_bytes())['schema'] != 'DAILY_EXPLANATIONS_UNIFIED_PREPARATION_V21':
        raise ValueError('PREFLIGHT_EXPECTED_V21')
    prepared = build_unified_server_preparation_v21(root=root,
        configuration_path=manifest['configuration_path'],
        configuration_sha256=manifest['configuration_sha256'])
    monthly = prepared['monthly']
    before_account = monthly.accounts.read()
    target = monthly.current()
    monthly.validate_current_target_pins()
    view = capped_target_view(target)
    packet_reader = prepared['observed_daily'].service.service.reader.packet_reader
    source_reference = packet_reader.reference
    source_raw = (root/source_reference['path']).read_bytes()
    if sha256(source_raw).hexdigest() != source_reference['sha256']:
        raise ValueError('SOURCE_CONFIGURATION_CHANGED')
    source = json.loads(source_raw)
    runs = root/source['runs_root']
    sessions = sorted(path.name for path in runs.iterdir() if path.is_dir()) if runs.is_dir() else []
    if monthly.accounts.read() != before_account or monthly.current() != target:
        raise ValueError('STATE_CHANGED_DURING_PREFLIGHT')
    return dict(status='CAP_TARGET_PREFLIGHT_ONLY_NOT_DEPLOYED',
        checked_at=datetime.now(timezone.utc).isoformat(), active_configuration=manifest,
        cap_view=view, current_source_runs_root=source['runs_root'],
        saved_session_directories=sessions[-5:],
        account_unchanged=True, target_unchanged=True,
        actual_daily_signal_evaluated=False, production_released=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = inspect(args.root)
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))
