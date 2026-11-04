"""Lossless research JSON codec, independent of Python decimal integer limits."""
import json
from fractions import Fraction

ENCODING = 'RESEARCH_EXACT_FRACTION_HEX_JSON_V1'
TAG = '__research_exact_fraction_hex_v1__'


def dumps(value, *, indent=2):
    def encode(item):
        if isinstance(item, Fraction):
            return {TAG: {'numerator': hex(item.numerator), 'denominator': hex(item.denominator)}}
        if isinstance(item, dict):
            if TAG in item:
                raise ValueError('RESERVED_FRACTION_ENCODING_KEY')
            if any(type(key) is not str for key in item):
                raise TypeError('STRING_JSON_KEYS_REQUIRED')
            return {key: encode(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [encode(val) for val in item]
        if item is None or type(item) in (str, bool, int, float):
            return item
        raise TypeError('UNSUPPORTED_RESEARCH_JSON_TYPE:' + type(item).__name__)
    return json.dumps({'encoding': ENCODING, 'payload': encode(value)}, indent=indent, allow_nan=False)


def loads(text):
    document = json.loads(text)
    if not isinstance(document, dict) or set(document) != {'encoding', 'payload'} or document['encoding'] != ENCODING:
        raise ValueError('RESEARCH_JSON_ENCODING_VERSION_REQUIRED')
    def decode(item):
        if isinstance(item, list):
            return [decode(val) for val in item]
        if isinstance(item, dict):
            if TAG in item:
                if set(item) != {TAG} or not isinstance(item[TAG], dict) or set(item[TAG]) != {'numerator', 'denominator'}:
                    raise ValueError('INVALID_FRACTION_ENCODING')
                parts = item[TAG]
                values = []
                for key in ('numerator', 'denominator'):
                    raw = parts[key]
                    if not isinstance(raw, str):
                        raise ValueError('CANONICAL_HEX_REQUIRED')
                    parsed = int(raw, 16)
                    if hex(parsed) != raw:
                        raise ValueError('CANONICAL_HEX_REQUIRED')
                    values.append(parsed)
                if values[1] <= 0:
                    raise ValueError('POSITIVE_DENOMINATOR_REQUIRED')
                return Fraction(*values)
            return {key: decode(val) for key, val in item.items()}
        return item
    return decode(document['payload'])
