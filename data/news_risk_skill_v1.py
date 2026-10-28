"""Pinned, bounded principles only; reference material is never model input."""
from pathlib import Path
import hashlib
VERSION = 'us-equity-news-risk-v1'
PINS = {
 'skills/us-equity-news-risk/SOUL.md': '6775681f3b49612a7c50568347e3b9e27597658e5fa40ac02b7f35d9a069893b',
 'skills/us-equity-news-risk/SKILL.md': '3c4863648f98901c64c6788ad5eb6f34e8fded73b3b76989ec2cb7c79b0a2c78',
}

def load_risk_skill(root=None):
    root = Path(root if root is not None else Path(__file__).resolve().parents[1]).resolve()
    chunks = []
    total = 0
    for relative, expected in PINS.items():
        path = root / relative
        for part in (path, *path.parents):
            if part == root: break
            if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 1024):
                raise ValueError('RISK_SKILL_LINK_FORBIDDEN')
        if not path.resolve().is_relative_to(root):
            raise ValueError('RISK_SKILL_PATH_INVALID')
        if path.stat().st_size > 12288:
            raise ValueError('RISK_SKILL_SIZE_INVALID')
        raw = path.read_bytes()
        total += len(raw)
        if total > 12288 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('RISK_SKILL_HASH_OR_SIZE_MISMATCH')
        text = raw.decode('utf-8', errors='strict')
        if not text.strip(): raise ValueError('RISK_SKILL_EMPTY')
        chunks.append(relative + '\n' + text)
    binding = {'version': VERSION, 'source_hashes': dict(PINS)}
    return {'binding': binding, 'prompt': '\nPINNED_RISK_REVIEW_PRINCIPLES\n' + '\n'.join(chunks)}

def require_risk_skill(binding, root=None):
    if binding != load_risk_skill(root)['binding']:
        raise ValueError('RISK_SKILL_VERSION_CHANGED')
