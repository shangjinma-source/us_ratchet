"""Explicit server configuration for V2; importing this module selects no data."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re

from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2


def create_service(*, root, descriptor_path, descriptor_sha256):
    """Pin the descriptor itself; never accept these parameters from HTTP clients."""
    root = Path(root).resolve()
    if (not isinstance(descriptor_path, str) or not descriptor_path
            or '\\' in descriptor_path or ':' in descriptor_path
            or PurePosixPath(descriptor_path).is_absolute()
            or '..' in PurePosixPath(descriptor_path).parts
            or not isinstance(descriptor_sha256, str)
            or re.fullmatch('[0-9a-f]{64}', descriptor_sha256) is None):
        raise ValueError('INVALID_SERVER_DESCRIPTOR_CONFIGURATION')

    def load():
        path = (root / descriptor_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError('DESCRIPTOR_OUTSIDE_ROOT')
        with path.open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or sha256(raw).hexdigest() != descriptor_sha256:
            raise ValueError('DESCRIPTOR_CHANGED_OR_TOO_LARGE')
        descriptor = json.loads(raw)
        if not isinstance(descriptor, dict) or set(descriptor) != {'input_path', 'admission_path', 'source_hashes'}:
            raise ValueError('DESCRIPTOR_SCHEMA_INVALID')
        return descriptor

    load()  # Validate configuration at construction; calculation is explicit.
    return CurrentQuantityPortfolioResearchV2(root=root, source_loader=load)
