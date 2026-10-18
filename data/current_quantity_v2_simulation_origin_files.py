"""Read exact accepted reference bytes; no discovery, quote refresh or account IO."""
import base64
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

from data.current_quantity_v2_paper_chain import review_chain
from backtest.current_quantity_v2_simulated_settlement import _references

LIMIT = 4*1024*1024
TOTAL_LIMIT = 128*1024*1024


def require(ok, reason):
    if not ok: raise ValueError(reason)


class SimulationOriginFilesReader:
    def __init__(self, *, capture_audit_roots=()):
        # Explicit CaptureAudit storage roots, not a recursively searched tree.
        self.roots = tuple(Path(root).absolute() for root in capture_audit_roots)

    def __call__(self, state, reference):
        chain = review_chain(state['chain'])
        sid = reference.get('security_id')
        require(sid in _references(chain) and _references(chain)[sid] == reference,
                'ORIGIN_REFERENCE_NOT_CURRENT_ACCEPTED_REFERENCE')
        pins = reference['source_hashes']
        require(type(pins) is dict and 0 < len(pins) <= 2000, 'ORIGIN_SOURCE_DOMAIN_REQUIRED')
        proposal = chain['genesis']['acceptance']['proposal']
        frozen = proposal.get('causal_inputs', {}).get('frozen_execution_package', {})
        embedded = frozen.get('files_base64', {})
        result = {}; total = 0
        for path, digest in pins.items():
            require(type(path) is str and path and '\\' not in path and ':' not in path
                    and not PurePosixPath(path).is_absolute()
                    and all(part not in ('','..','.') for part in path.split('/'))
                    and type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest),
                    'INVALID_ORIGIN_SOURCE_BINDING')
            raw = None
            # Same filename in an older proposal is never evidence of new bytes.
            if frozen.get('source_hashes', {}).get(path) == digest and path in embedded:
                encoded = embedded[path]
                require(type(encoded) is str and len(encoded) <= 4*((LIMIT+2)//3), 'ORIGIN_SOURCE_TOO_LARGE')
                try: raw = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError) as error: raise ValueError('INVALID_ORIGIN_BASE64') from error
                require(base64.b64encode(raw).decode() == encoded, 'INVALID_ORIGIN_BASE64')
            else:
                for root in self.roots:
                    target = root/'blobs'/digest
                    require(not any(p.is_symlink() for p in (root, *root.parents, root/'blobs', target)), 'ORIGIN_SYMLINK_REFUSED')
                    require(target.resolve().is_relative_to(root.resolve()), 'ORIGIN_PATH_ESCAPE')
                    if not target.exists(): continue
                    with target.open('rb') as stream: candidate = stream.read(LIMIT+1)
                    require(len(candidate) <= LIMIT and sha256(candidate).hexdigest() == digest,
                            'ORIGIN_SOURCE_CHANGED_OR_TOO_LARGE')
                    raw = candidate
                    break
            require(raw is not None, 'ORIGIN_SOURCE_MISSING')
            total += len(raw)
            require(len(raw) <= LIMIT and total <= TOTAL_LIMIT and sha256(raw).hexdigest() == digest,
                    'ORIGIN_SOURCE_CHANGED_OR_TOO_LARGE')
            result[path] = raw
        return result
