"""Read a pinned-source file without allocating its maximum allowed size.

Callers still own path admission and the expected content-hash check. This
helper checks the opened file, including changes during the bounded read.
"""
import os
import stat


def read_sized_source(source, maximum_bytes):
    if type(maximum_bytes) is not int or maximum_bytes < 0:
        raise ValueError('SOURCE_SIZE_LIMIT_INVALID')
    before = os.fstat(source.fileno())
    if not stat.S_ISREG(before.st_mode) or source.tell() != 0:
        raise ValueError('SOURCE_REGULAR_FILE_AT_START_REQUIRED')
    if before.st_size > maximum_bytes:
        raise ValueError('SOURCE_SIZE_LIMIT_EXCEEDED')
    raw = source.read(before.st_size + 1)
    after = os.fstat(source.fileno())
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if (type(raw) is not bytes or len(raw) != before.st_size
            or any(getattr(before, name) != getattr(after, name) for name in fields)):
        raise ValueError('SOURCE_CHANGED_DURING_READ')
    return raw
