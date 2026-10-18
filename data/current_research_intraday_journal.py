"""Local create-only observations. Hashes prove local bytes, not trusted time."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
import json
import base64
import os
import re
import tempfile


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False,
                      default=lambda x: str(x) if isinstance(x, Decimal) else _unsupported(x)).encode('utf-8')


def _unsupported(value):
    raise TypeError(type(value).__name__)


def _publish(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError('OBSERVATION_CREATE_ONLY_CONFLICT')
    finally:
        os.unlink(temporary)


class IntradayObservationJournal:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _write(self, relative, raw):
        path=self.root/relative
        if not path.parent.resolve().is_relative_to(self.root) or path.is_symlink():
            raise ValueError('WRITE_PATH_OUTSIDE_JOURNAL')
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.parent.resolve().is_relative_to(self.root):
            raise ValueError('WRITE_PATH_OUTSIDE_JOURNAL')
        _publish(path,raw)

    def prepare(self, event, captures):
        """Freeze a historical observation without writing or claiming delivery."""
        event = dict(event)
        identifier = event['event_id']
        if not re.fullmatch(r'[0-9a-f]{32}', identifier):
            raise ValueError('INVALID_EVENT_ID')
        references = []; files = {}
        def freeze(path, raw):
            files[path] = dict(path=path, sha256=sha256(raw).hexdigest(),
                               base64=base64.b64encode(raw).decode('ascii'))
        for capture in captures:
            item = dict(capture); payload = item.pop('payload')
            if isinstance(payload, bytes):
                raw, encoding = payload, 'ORIGINAL_HTTP_RESPONSE_BYTES'
            elif isinstance(payload, str):
                raw, encoding = payload.encode('utf-8'), 'INJECTED_TEXT_UTF8'
            else:
                raw, encoding = _json(payload), 'SYNTHETIC_NORMALIZED_JSON'
            digest = sha256(raw).hexdigest()
            relative = f'raw/{digest}.bin'
            freeze(relative, raw)
            references.append(dict(item, path=relative, sha256=digest, encoding=encoding))
        event['captures'] = references
        event['integrity_scope'] = 'LOCAL_BYTES_NOT_EXTERNALLY_TRUSTED_TIMESTAMP'
        raw = _json(event); digest = sha256(raw).hexdigest()
        day = datetime.fromisoformat(event['request_started_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        relative = f'events/{day}/{identifier}.json'
        freeze(relative, raw)
        receipt = dict(status='SAVED', event_id=identifier, event_path=relative, event_sha256=digest,
                       raw_sha256s=sorted({item['sha256'] for item in references}))
        return dict(schema='INTRADAY_FROZEN_PUBLICATION_V1',files=list(files.values()),receipt=receipt)

    def validate_prepared(self, package):
        """Allow only this observation's hash-bound raw files and exact event path."""
        if not isinstance(package,dict) or set(package)!={'schema','files','receipt'} or package['schema']!='INTRADAY_FROZEN_PUBLICATION_V1':
            raise ValueError('INVALID_FROZEN_PUBLICATION')
        receipt=package['receipt']; files={}
        if not isinstance(package['files'],list) or not package['files']:
            raise ValueError('EMPTY_FROZEN_PUBLICATION')
        for item in package['files']:
            if not isinstance(item,dict) or set(item)!={'path','sha256','base64'}:
                raise ValueError('INVALID_FROZEN_FILE')
            name=item['path']
            if not isinstance(name,str) or name in files or not re.fullmatch(r'(?:raw/[0-9a-f]{64}\.bin|events/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.json)',name):
                raise ValueError('INVALID_FROZEN_PATH')
            raw=base64.b64decode(item['base64'],validate=True)
            if sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('FROZEN_FILE_HASH_MISMATCH')
            files[name]=raw
        event_raw=files[receipt['event_path']]
        if sha256(event_raw).hexdigest()!=receipt['event_sha256']:
            raise ValueError('FROZEN_EVENT_HASH_MISMATCH')
        event=json.loads(event_raw)
        day=datetime.fromisoformat(event['request_started_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        expected_path=f"events/{day}/{event['event_id']}.json"
        references=event['captures']; raw_hashes=sorted({item['sha256'] for item in references})
        expected_receipt=dict(status='SAVED',event_id=event['event_id'],event_path=expected_path,
                              event_sha256=sha256(event_raw).hexdigest(),raw_sha256s=raw_hashes)
        if receipt!=expected_receipt or set(files)!={expected_path}|{f'raw/{h}.bin' for h in raw_hashes}:
            raise ValueError('FROZEN_PUBLICATION_BINDING_MISMATCH')
        for item in references:
            if item['path']!=f"raw/{item['sha256']}.bin" or sha256(files[item['path']]).hexdigest()!=item['sha256']:
                raise ValueError('FROZEN_CAPTURE_BINDING_MISMATCH')
        return files

    def publish_prepared(self, package):
        files=self.validate_prepared(package)
        event_path=package['receipt']['event_path']
        for name,raw in files.items():
            if name!=event_path:self._write(name,raw)
        self._write(event_path,files[event_path])
        return dict(package['receipt'])

    def record(self, event, captures):
        """Legacy create-only format, with prepare/publish separated for outbox."""
        return self.publish_prepared(self.prepare(event,captures))

    def read_event(self, path, *, expected_sha256):
        relative = Path(path)
        resolved = (self.root / relative).resolve()
        if relative.is_absolute() or not resolved.is_relative_to(self.root / 'events'):
            raise ValueError('EVENT_PATH_OUTSIDE_JOURNAL')
        raw = resolved.read_bytes()
        if sha256(raw).hexdigest() != expected_sha256:
            raise ValueError('EVENT_HASH_MISMATCH')
        event = json.loads(raw)
        for item in event['captures']:
            expected = f"raw/{item['sha256']}.bin"
            if item['path'] != expected or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
                raise ValueError('RAW_PATH_INVALID')
            source = (self.root / expected).resolve()
            if not source.is_relative_to(self.root / 'raw') or sha256(source.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('RAW_HASH_MISMATCH')
        return event
