"""Strict bounded UTF-8 top-level JSON rows iterator; no filesystem operations.

Summary becomes available only after iteration reaches verified EOF. Consuming a
prefix never authenticates the whole document. Byte spans exclude surrounding
whitespace and include the exact original row JSON, not re-encoded values.
"""
import hashlib
import json
import math
from copy import deepcopy


class RowsStreamError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise RowsStreamError(message)


def strict_value(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'Duplicate JSON object key: ' + key)
            out[key] = value
        return out
    def invalid(value):
        raise RowsStreamError('Nonfinite JSON: ' + value)
    def finite_float(value):
        parsed = float(value)
        require(math.isfinite(parsed), 'Nonfinite JSON numeric overflow')
        return parsed
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=invalid, parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RowsStreamError('Invalid UTF-8 JSON value') from error


class JsonRowsStream:
    """Iterate {row_index, byte_start, byte_stop, sha256, value} records.

    The caller owns the binary stream and may wrap it for other hash accounting.
    Resource bounds concern raw token sizes, not a claim about Python RSS.
    This class never closes, seeks, or rereads the supplied stream.
    """
    def __init__(self, stream, *, block_size=65536, max_row_bytes=64*1024**2,
                 max_metadata_bytes=16*1024**2):
        for value in (block_size, max_row_bytes, max_metadata_bytes):
            require(type(value) is int and value > 0, 'Positive exact resource bound')
        require(callable(getattr(stream, 'read', None)), 'Binary readable stream')
        self.stream = stream
        self.block_size = block_size
        self.max_row_bytes = max_row_bytes
        self.max_metadata_bytes = max_metadata_bytes
        self.buffer = b''
        self.cursor = self.offset = self.loaded_bytes = 0
        self.eof = False
        self.hasher = hashlib.sha256()
        self._summary = None
        self._iterator = self._iterate()

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    @property
    def summary(self):
        require(self._summary is not None, 'Summary unavailable before verified exhaustion')
        return deepcopy(self._summary)

    def _peek(self):
        if self.cursor == len(self.buffer) and not self.eof:
            chunk = self.stream.read(self.block_size)
            require(type(chunk) is bytes and len(chunk) <= self.block_size, 'Bounded binary read')
            self.buffer, self.cursor = chunk, 0
            self.eof = not chunk
            self.hasher.update(chunk)
            self.loaded_bytes += len(chunk)
        return self.buffer[self.cursor] if self.cursor < len(self.buffer) else None

    def _take(self):
        value = self._peek()
        require(value is not None, 'Truncated JSON')
        self.cursor += 1
        self.offset += 1
        return value

    def _space(self):
        while self._peek() in (9, 10, 13, 32):
            self._take()

    def _expect(self, value):
        self._space()
        require(self._take() == value, 'Unexpected JSON delimiter')

    def _token(self, limit):
        self._space()
        start = self.offset
        first = self._peek()
        require(first is not None, 'Truncated JSON value')
        raw = bytearray()
        stack = []
        quoted = escaped = False
        compound = first in (123, 91)
        string = first == 34
        while True:
            value = self._peek()
            if not raw or compound or string:
                require(value is not None, 'Truncated JSON token')
            elif value is None or value in (9, 10, 13, 32, 44, 93, 125):
                break
            value = self._take()
            require(len(raw) < limit, 'JSON token resource limit exceeded')
            raw.append(value)
            if quoted:
                if escaped:
                    escaped = False
                elif value == 92:
                    escaped = True
                elif value == 34:
                    quoted = False
                    if string and not stack:
                        break
                continue
            if value == 34:
                quoted = True
            elif compound and value in (123, 91):
                stack.append(125 if value == 123 else 93)
            elif compound and value in (125, 93):
                require(bool(stack) and stack.pop() == value, 'Mismatched JSON container')
                if not stack:
                    break
        blob = bytes(raw)
        return strict_value(blob), start, self.offset, blob

    def _iterate(self):
        self._expect(123)
        metadata = {}
        seen = set()
        metadata_bytes = rows_count = 0
        self._space()
        require(self._peek() != 125, 'Required rows array missing')
        while True:
            require(self._peek() == 34, 'Top-level keys must be JSON strings')
            key, _, _, key_blob = self._token(self.max_metadata_bytes)
            require(type(key) is str and key not in seen, 'Duplicate top-level key')
            seen.add(key)
            metadata_bytes += len(key_blob)
            require(metadata_bytes <= self.max_metadata_bytes, 'Metadata resource limit exceeded')
            self._expect(58)
            if key == 'rows':
                self._expect(91)
                self._space()
                if self._peek() != 93:
                    while True:
                        value, start, stop, blob = self._token(self.max_row_bytes)
                        record = dict(row_index=rows_count, byte_start=start,
                                      byte_stop=stop, sha256=hashlib.sha256(blob).hexdigest(), value=value)
                        rows_count += 1
                        yield record
                        del record, value, blob
                        self._space()
                        if self._peek() == 93:
                            break
                        self._expect(44)
                self._expect(93)
            else:
                value, _, _, blob = self._token(self.max_metadata_bytes - metadata_bytes)
                metadata_bytes += len(blob)
                metadata[key] = value
            self._space()
            if self._peek() == 125:
                self._take()
                break
            self._expect(44)
            self._space()
        require('rows' in seen, 'Required rows array missing')
        self._space()
        require(self._peek() is None, 'Trailing JSON bytes or multiple documents')
        require(self.offset == self.loaded_bytes, 'Complete original byte consumption')
        self._summary = dict(metadata=metadata, row_count=rows_count,
                             byte_count=self.loaded_bytes, sha256=self.hasher.hexdigest(),
                             complete_document_consumed=True)
