"""Server-owned readers for the separate V2 intraday reference service."""
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath

from data.current_quantity_v2_intraday_reference import CurrentQuantityV2IntradayReference
from data.current_research_intraday_execution import fetch_intraday_chart

MANIFEST = 'tmp/current_expanded_rebased_manifest_20261015_v2.json'


def create_reference_service(*, root, snapshot_service, fetch=fetch_intraday_chart,
                             clock=lambda: datetime.now(timezone.utc)):
    root = Path(root).resolve()

    def read(name):
        if (not isinstance(name, str) or not name or '\\' in name or ':' in name
                or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
            raise ValueError('INVALID_REFERENCE_SOURCE_PATH')
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('REFERENCE_SOURCE_OUTSIDE_ROOT')
        with path.open('rb') as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError('REFERENCE_SOURCE_TOO_LARGE')
        return raw

    def input_reader(snapshot):
        descriptor = snapshot_service.loader()
        name = descriptor['input_path']
        if descriptor['source_hashes'][name] != snapshot['input_sha256']:
            raise ValueError('REFERENCE_INPUT_BINDING_CHANGED')
        return read(name)

    def identity_reader(snapshot, stock, session):
        # The core verifies these original bytes against the immutable snapshot.
        raw = read(MANIFEST)
        candidates = [item for item in json.loads(raw)['candidates']
                      if item['security_id'] == stock['security_id']]
        if len(candidates) != 1:
            raise ValueError('REFERENCE_IDENTITY_NOT_UNIQUE')
        names = {MANIFEST, *candidates[0]['identity_source_references']}
        return dict(manifest_path=MANIFEST,
                    source_hashes={name: snapshot['sources'][name] for name in names},
                    files={name: raw if name == MANIFEST else read(name) for name in names})

    def quote_reader(stock):
        raw = fetch(stock['ticker'])
        return dict(raw=raw, captured_at=clock())

    return CurrentQuantityV2IntradayReference(
        snapshot_reader=snapshot_service.snapshot, input_reader=input_reader,
        quote_reader=quote_reader, identity_reader=identity_reader, clock=clock)
