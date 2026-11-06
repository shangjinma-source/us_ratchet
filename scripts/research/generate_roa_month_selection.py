"""Generate a separate immutable roster artifact; never register or activate it."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from data.roa_monthly_selection import generate_month_selection


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--calendar',required=True)
    parser.add_argument('--calendar-sha256',required=True)
    parser.add_argument('--completed-through',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    raw=(root/args.calendar).read_bytes()
    if sha256(raw).hexdigest()!=args.calendar_sha256:raise ValueError('CALENDAR_SOURCE_CHANGED')
    calendar=json.loads(raw)
    if calendar['schema'] not in ('FIXED_EXCHANGE_SESSIONS_V1','VERIFIED_SCHEDULE_DATES_V1'):raise ValueError('CALENDAR_SCHEMA')
    result=generate_month_selection(root=root,manifest_path=args.manifest,manifest_sha256=args.manifest_sha256,
        calendar_sessions=[r['date'] for r in calendar['sessions']],completed_through=args.completed_through)
    result['source_hashes'][args.calendar]=args.calendar_sha256
    for source in calendar['source_references']:
        if sha256((root/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('CALENDAR_EVIDENCE_CHANGED')
        result['source_hashes'][source['path']]=source['sha256']
    result.pop('selection_id');result['selection_id']=sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    target=(root/args.output).resolve()
    if not target.is_relative_to(root):raise ValueError('OUTPUT_OUTSIDE_ROOT')
    encoded=json.dumps(result,indent=2).encode()
    if target.exists() and target.read_bytes()!=encoded:raise ValueError('IMMUTABLE_MONTH_OUTPUT_EXISTS')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(encoded)
    print(json.dumps(dict(path=args.output,sha256=sha256(encoded).hexdigest(),month=result['effective_month'],selected=[r['ticker'] for r in result['securities']])))


if __name__=='__main__':main()
