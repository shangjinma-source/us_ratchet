"""Join pinned historical and reviewed extension schedules without installing them."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from scripts.build_monthly_successor_plan import calendar, read


def prepare(root, previous_path, previous_pins, extension_path, extension_sha256, output_directory):
    root = Path(root).resolve()
    previous = calendar(root, previous_path, previous_pins)
    extension = read(root, extension_path, extension_sha256)
    pins = dict(previous_pins)
    pins[extension_path] = extension_sha256
    for name, digest in extension['source_hashes'].items():
        if name in pins and pins[name] != digest:
            raise ValueError('CALENDAR_SOURCE_CONFLICT')
        pins[name] = digest
    rows = {row['date']: dict(row) for row in previous['sessions']}
    local_zone = ZoneInfo('America/New_York')
    for source in extension['sessions']:
        row = dict(source)
        for key in ('open_at', 'close_at'):
            instant = datetime.fromisoformat(row[key])
            if instant.tzinfo is None:
                raise ValueError('CALENDAR_TIMEZONE_REQUIRED')
            row[key] = instant.astimezone(local_zone).isoformat()
        if row['date'] in rows:
            if row != rows[row['date']]:
                raise ValueError('CALENDAR_OVERLAP_CHANGED')
        elif row['date'] <= previous['calendar'][-1]:
            raise ValueError('CALENDAR_HISTORICAL_INSERTION')
        else:
            rows[row['date']] = row
    output = root / output_directory
    if not output.resolve().is_relative_to(root / 'tmp'):
        raise ValueError('PRIVATE_CANDIDATE_DIRECTORY_REQUIRED')
    output.mkdir(exist_ok=False)
    schedule = dict(schema='SCHEDULED_REGULAR_SESSIONS_V1', calendar=sorted(rows),
                    sessions=[rows[day] for day in sorted(rows)], source_hashes=pins,
                    status='REVIEWED_EXTENSION_CANDIDATE_NOT_INSTALLED')
    target = output / 'schedule.json'
    target.write_bytes(canonical(schedule))
    name = target.relative_to(root).as_posix()
    pins = dict(pins, **{name: sha256(target.read_bytes()).hexdigest()})
    validated = calendar(root, name, pins)
    result = dict(status='SUCCESSOR_CALENDAR_VALIDATED_NOT_INSTALLED',
                  calendar_path=name, calendar_source_hashes=pins,
                  preserved_sessions=len(previous['sessions']), total_sessions=len(validated['sessions']),
                  end=validated['calendar'][-1])
    (output / 'receipt.json').write_bytes(canonical(result))
    return result
