"""Create a consistent local account + price-correction backup, never restore live data."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from api.strategy_account import StrategyAccountService
from core.strategy_account_store import StrategyAccountStore


def backup_account(database_path, output_directory):
    source = Path(database_path).resolve(strict=True)
    output = Path(output_directory).absolute()
    store = StrategyAccountStore(source)
    # The account reservation excludes both normal writers and amendments.
    # Separate read connections allow SQLite's online backup without modifying it.
    with closing(store._connect(False)) as guard:
        guard.execute('BEGIN IMMEDIATE')
        try:
            state, _ = store._read(guard)
            service = StrategyAccountService(database_path=source, account_id=state['account_id'], resolver=None)
            expected = service.read()
            output.mkdir(parents=True, exist_ok=False)
            sources = [source]
            if service.corrections.path.exists():
                sources.append(service.corrections.path)
            files = []
            for path in sources:
                target = output / path.name
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as reader:
                    with closing(sqlite3.connect(target)) as writer:
                        reader.backup(writer)
                        if writer.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                            raise ValueError('BACKUP_INTEGRITY_FAILED')
                files.append(dict(name=target.name, sha256=sha256(target.read_bytes()).hexdigest()))
            restored = StrategyAccountService(database_path=output/source.name, account_id=state['account_id'], resolver=None)
            if restored.read() != expected:
                raise ValueError('BACKUP_PROJECTION_MISMATCH')
            manifest = dict(status='VERIFIED_ACCOUNT_BACKUP', created_at=datetime.now(timezone.utc).isoformat(),
                            account_revision=state['revision'], files=files,
                            correction_revision=expected['account']['fill_correction_revision'],
                            scope='Account journal and price amendments only; not lifecycle, flow classifications or deployment configuration.')
            (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            return manifest
        finally:
            guard.rollback()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(backup_account(arguments.database, arguments.output), indent=2))
