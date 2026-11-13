"""Back up account, corrections and broker side journals; never restore live data."""
import argparse
from contextlib import closing, ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from api.strategy_account import StrategyAccountService
from core.strategy_account_store import StrategyAccountStore


def backup_account(database_path, output_directory, *, classification_path=None):
    source = Path(database_path).resolve(strict=True)
    output = Path(output_directory).absolute()
    store = StrategyAccountStore(source)
    # The account reservation excludes both normal writers and amendments.
    # Separate read connections allow SQLite's online backup without modifying it.
    with ExitStack() as locks, closing(store._connect(False)) as guard:
        guard.execute('BEGIN IMMEDIATE')
        try:
            sidecars = [source.with_name(source.name + suffix) for suffix in
                        ('.internal-transfers.sqlite3', '.broker-cash.sqlite3', '.transfer-reconciliation.sqlite3')]
            if classification_path is not None:
                classification=Path(classification_path).absolute()
                if any(p.is_symlink() for p in (classification,*classification.parents)) or not classification.resolve().is_relative_to(source.parent) or not classification.is_file():
                    raise ValueError('BACKUP_CLASSIFICATION_PATH_INVALID')
                if classification.resolve()==source or classification in sidecars:
                    raise ValueError('BACKUP_CLASSIFICATION_PATH_INVALID')
                sidecars.append(classification)
            if len({p.name for p in [source,*sidecars]})!=len(sidecars)+1:
                raise ValueError('BACKUP_FILENAME_COLLISION')
            missing = [path for path in sidecars if not path.exists()]
            snapshots = {}
            for path in sidecars:
                if path in missing:
                    continue
                if path.is_symlink():
                    raise ValueError('BACKUP_SIDECAR_SYMLINK')
                connection = locks.enter_context(closing(sqlite3.connect(
                    path.as_uri()+'?mode=rw', uri=True, timeout=10)))
                connection.execute('BEGIN IMMEDIATE')
                snapshots[path] = '\n'.join(connection.iterdump())
            state, _ = store._read(guard)
            service = StrategyAccountService(database_path=source, account_id=state['account_id'], resolver=None)
            scope_path = source.with_name(source.stem+'.trade_scope.json')
            if scope_path.is_symlink():
                raise ValueError('BACKUP_SCOPE_SYMLINK')
            scope_bytes = scope_path.read_bytes() if scope_path.exists() else None
            expected = service.read()
            output.mkdir(parents=True, exist_ok=False)
            sources = [source]
            if service.corrections.path.exists():
                sources.append(service.corrections.path)
            sources.extend(snapshots)
            files = []
            for path in sources:
                target = output / path.name
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as reader:
                    with closing(sqlite3.connect(target)) as writer:
                        reader.backup(writer)
                        if writer.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                            raise ValueError('BACKUP_INTEGRITY_FAILED')
                        if path in snapshots and '\n'.join(writer.iterdump()) != snapshots[path]:
                            raise ValueError('BACKUP_SIDECAR_CONTENT_MISMATCH')
                files.append(dict(name=target.name, source_relative_path=path.relative_to(source.parent).as_posix(),sha256=sha256(target.read_bytes()).hexdigest()))
            if scope_bytes is not None:
                target = output/scope_path.name
                target.write_bytes(scope_bytes)
                files.append(dict(name=target.name, sha256=sha256(scope_bytes).hexdigest()))
            restored = StrategyAccountService(database_path=output/source.name, account_id=state['account_id'], resolver=None)
            if restored.read() != expected:
                raise ValueError('BACKUP_PROJECTION_MISMATCH')
            if any(path.exists() for path in missing):
                raise ValueError('BACKUP_SIDECAR_CREATED_DURING_CAPTURE')
            if (scope_path.read_bytes() if scope_path.exists() else None) != scope_bytes:
                raise ValueError('BACKUP_SCOPE_CHANGED_DURING_CAPTURE')
            manifest = dict(status='VERIFIED_ACCOUNT_BACKUP', created_at=datetime.now(timezone.utc).isoformat(),
                            account_revision=state['revision'], files=files,
                            correction_revision=expected['account']['fill_correction_revision'],
                            absent_broker_journals=[path.name for path in missing],
                            flow_classification_included=classification_path is not None,
                            scope='Account journal, price amendments, trade display scope, internal transfers, broker cash allocations and transfer reconciliation; flow classifications only when explicitly supplied; not lifecycle or deployment configuration.')
            (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            return manifest
        finally:
            guard.rollback()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--classification', help='Explicit existing cash classification sidecar beside the account database')
    arguments = parser.parse_args()
    print(json.dumps(backup_account(arguments.database, arguments.output,classification_path=arguments.classification), indent=2))
