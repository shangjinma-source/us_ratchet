"""Pinned identity lookup for recording scoped fills, not quote/action approval."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re


class PinnedStrategyIdentity:
    def __init__(self, root, manifest_path, manifest_sha256):
        self.root=Path(root).resolve()
        self.manifest_path=manifest_path
        self.manifest_sha256=manifest_sha256

    def _read(self, name, expected):
        if (type(name) is not str or '\\' in name or ':' in name
                or PurePosixPath(name).is_absolute()
                or any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError('IDENTITY_SOURCE_PATH_INVALID')
        path=(self.root/name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('IDENTITY_SOURCE_PATH_ESCAPE')
        with path.open('rb') as stream:
            raw=stream.read(8*1024*1024+1)
        if len(raw)>8*1024*1024 or sha256(raw).hexdigest()!=expected:
            raise ValueError('IDENTITY_SOURCE_CHANGED')
        return raw

    def __call__(self, ticker):
        if type(ticker) is not str or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,14}',ticker):
            raise ValueError('INVALID_TICKER')
        document=json.loads(self._read(self.manifest_path,self.manifest_sha256))
        matches=[row for row in document['candidates'] if row.get('ticker')==ticker]
        if len(matches)!=1:
            raise ValueError('IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE')
        row=matches[0]
        if row.get('status')!='READY_CONDITIONAL' or row.get('identity_reviewed') is not True:
            raise ValueError('IDENTITY_NOT_REVIEWED')
        references=row['identity_source_references']
        if not references or len(set(references))!=len(references):
            raise ValueError('IDENTITY_REFERENCES_REQUIRED')
        hashes={self.manifest_path:self.manifest_sha256}
        for name in references:
            expected=document['source_hashes'][name]
            self._read(name,expected)
            hashes[name]=expected
        return dict(ticker=ticker,security_id=row['security_id'],
                    source_references=[self.manifest_path]+list(references),source_hashes=hashes)
