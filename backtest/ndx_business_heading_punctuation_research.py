"""Narrow punctuation extension of the frozen same-parent DOM extractor."""
import hashlib
from pathlib import Path
import re
from types import FunctionType

from backtest import ndx_business_heading_excerpt_research as original

SOURCE = Path(__file__).resolve()
ORIGINAL_SOURCE = Path(original.__file__).resolve()
LOADED_SOURCES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE, ORIGINAL_SOURCE)}


def extract_business_heading_punctuation(raw):
    """Permit en/em dashes and terminal punctuation only on complete headings."""
    for path, expected in LOADED_SOURCES.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Loaded extractor source changed')
    binding = dict(original.extract_business_heading_excerpt.__globals__)
    binding['START'] = re.compile(r'ITEM\s+1\s*[.\-:\u2013\u2014]?\s*BUSINESS\s*[.:]?', re.IGNORECASE)
    binding['END'] = re.compile(r'ITEM\s+1A\s*[.\-:\u2013\u2014]?\s*RISK\s+FACTORS\s*[.:]?', re.IGNORECASE)
    extractor = FunctionType(original.extract_business_heading_excerpt.__code__, binding)
    result = extractor(raw)
    result['schema'] = 'ndx_business_heading_punctuation_research_v1'
    result['boundary_method'] = 'UNIQUE_SIBLING_DOM_COMPLETE_HEADINGS_PUNCTUATION_EXTENSION'
    result['source_hashes'] = dict(LOADED_SOURCES)
    return result
