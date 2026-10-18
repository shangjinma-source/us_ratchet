"""Explicit UTF-8 bytes transport for the frozen native navigation helper.

No artifact paths, recovery authorization, source claims or visual acceptance are
inferred here. The caller owns immutable input/output publication. This module
never reads the locale-dependent sys.stdin text stream.
"""
import base64
import hashlib
import json
import sys

NATIVE_SHA256 = '267333bd62a3399c6ab3c97104bf884a737e116a51e8c62243aa3e0fcd6a475d'
MAX_REQUEST_BYTES = 128 * 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def apply_navigation_request(request_bytes):
    if type(request_bytes) is not bytes or not 0 < len(request_bytes) <= MAX_REQUEST_BYTES:
        raise ValueError('Bounded UTF-8 request bytes required')
    request = json.loads(request_bytes.decode('utf-8', errors='strict'),
                         object_pairs_hook=unique_object, parse_constant=reject_constant)
    if type(request) is not dict or set(request) != {'source', 'sha', 'xlsx', 'links'}:
        raise ValueError('Exact transport request fields required')
    if request['sha'] != NATIVE_SHA256:
        raise ValueError('Frozen native helper identity required')
    for key in ('source', 'xlsx'):
        if type(request[key]) is not str:
            raise ValueError('Strict base64 strings required')
    source = base64.b64decode(request['source'], validate=True)
    workbook = base64.b64decode(request['xlsx'], validate=True)
    if hashlib.sha256(source).hexdigest() != NATIVE_SHA256:
        raise ValueError('Frozen native helper bytes mismatch')
    namespace = {'__name__': '_authenticated_native_navigation'}
    exec(compile(source, 'authenticated_native_navigation.py', 'exec'), namespace)
    return namespace['add_native_navigation_links'](workbook, request['links'])


def main():
    request = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    sys.stdout.buffer.write(apply_navigation_request(request))
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
