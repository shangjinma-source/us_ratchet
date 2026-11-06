"""Runtime monthly artifact reader. Standard library only; no research imports."""
from hashlib import sha256
import json
from pathlib import Path


class RoaMonthlySelectionLoader:
    """Trusted config supplies month -> path/hash. Generation is not activation."""
    def __init__(self,*,root,registry):self.root=Path(root).resolve();self.registry=dict(registry)
    def _read(self,name,expected):
        path=(self.root/name).resolve()
        if not path.is_relative_to(self.root):raise ValueError('MONTH_SOURCE_PATH_INVALID')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('MONTH_SOURCE_CHANGED:'+name)
        return raw
    def __call__(self,session):
        spec=self.registry.get(session[:7])
        if spec is None:raise ValueError('WAIT_NEW_MONTH_SIGNAL')
        artifact=json.loads(self._read(spec['path'],spec['sha256']))
        if artifact['schema']!='ROA_MONTH_SELECTION_V1' or artifact['effective_month']!=session[:7] or artifact['first_execution_session']>session:
            raise ValueError('MONTH_SELECTION_SCOPE_INVALID')
        for name,expected in artifact['source_hashes'].items():self._read(name,expected)
        content=dict(artifact);digest=content.pop('selection_id')
        if sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=digest:
            raise ValueError('MONTH_SELECTION_DIGEST_INVALID')
        return artifact
