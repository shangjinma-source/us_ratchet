"""Wait for a bounded vendor clock lead without altering receipt capture time."""
from datetime import datetime, timezone
import json
import time


def wait_for_vendor_clock(raw, *, captured_at, clock, sleep=time.sleep, monotonic=time.monotonic):
    value = json.loads(raw)['chart']['result'][0]['meta']['regularMarketTime']
    if type(value) is not int:
        raise ValueError('INTEGER_QUOTE_TIMESTAMP_REQUIRED')
    last = datetime.fromtimestamp(value, timezone.utc)
    if (last - captured_at).total_seconds() > 1:
        raise ValueError('VENDOR_CLOCK_LEAD_EXCEEDS_ONE_SECOND')
    deadline = monotonic() + 1
    checked = clock()
    while checked < last:
        if checked < captured_at:
            raise ValueError('SERVER_CLOCK_ROLLBACK')
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ValueError('VENDOR_CLOCK_WAIT_EXPIRED')
        sleep(min(0.05, remaining))
        checked = clock()
    if checked < captured_at:
        raise ValueError('SERVER_CLOCK_ROLLBACK')
    return checked
