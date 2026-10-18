"""Read a hash-pinned saved journal row and publish research-only diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.ndx_offline_fund_signal_diagnostic_research import diagnose


def read_saved_row(path, snapshot_id, expected_sha256, tail_bytes=32*1024*1024):
    """Bounded tail lookup; no live API and no claim of whole-journal uniqueness."""
    with Path(path).open('rb') as handle:
        handle.seek(0, 2)
        start=max(0, handle.tell()-tail_bytes)
        handle.seek(start)
        raw=handle.read(tail_bytes)
    lines=raw.splitlines()
    if start:
        lines=lines[1:]
    for line in reversed(lines):
        if hashlib.sha256(line).hexdigest()!=expected_sha256:
            continue
        snapshot=json.loads(line, parse_float=str)
        if snapshot.get('snapshot_id')!=snapshot_id:
            raise ValueError('Pinned row snapshot_id mismatch')
        return line, snapshot
    raise ValueError('Pinned row hash not present in bounded journal tail')


def build_report(raw_line, research_cash):
    snapshot=json.loads(raw_line, parse_float=str)
    constraints=snapshot.get('execution_constraints')
    if type(constraints) is not dict:
        constraints={}
    account=snapshot.get('account')
    gaps=account.get('position_gaps') if type(account) is dict else None
    rows=gaps.get('rows') if type(gaps) is dict else None
    execution=snapshot.get('execution')
    items=execution.get('items') if type(execution) is dict else None
    if type(items) is not list:
        raise ValueError('Saved snapshot lacks execution.items')
    if rows is not None and type(rows) is not list:
        raise ValueError('Saved gap rows malformed')
    policy={key:constraints.get(key) for key in ('lot_size','allow_fractional','fee_bps','min_fee')}
    reference=dict(snapshot_id=snapshot.get('snapshot_id'),ts=snapshot.get('ts'),
        raw_line_sha256=hashlib.sha256(raw_line).hexdigest(),
        timestamp_timezone_unspecified=True,source='HASH_PINNED_SAVED_JOURNAL_ROW')
    report=diagnose(execution_items=items,gap_rows=rows if rows is not None else [],
        research_cash_usd=research_cash,policy=policy,snapshot_reference=reference)
    report.update(research_cash_is_user_current_cash=False,
        saved_state_freshness=snapshot.get('state_freshness'),
        missing_snapshot_fields=(['account.position_gaps.rows'] if rows is None else [])+
            ['execution_constraints.'+key for key,value in policy.items() if value is None],
        snapshot_fields_mapping={'execution_items':'execution.items','gap_rows':'account.position_gaps.rows',
            'policy':'execution_constraints'},
        core_deployment_status='NOT_EVALUATED_NO_ACCOUNT_READINESS_AUTHORITY',
        dynamic_new_money_status='NOT_EVALUATED_REQUIRES_CANONICAL_TARGET_RISK_AND_ADMISSION')
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--journal',required=True)
    parser.add_argument('--snapshot-id',required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--research-cash',required=True,action='append')
    args=parser.parse_args()
    raw,snapshot=read_saved_row(args.journal,args.snapshot_id,args.sha256)
    reports=[build_report(raw,cash) for cash in args.research_cash]
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'snapshot.json').write_bytes(raw+b'\n')
    source_root=Path(__file__).resolve().parents[1]
    document=dict(reports=reports,journal_was_read_only=True,source_sha256={
        name:hashlib.sha256((source_root/name).read_bytes()).hexdigest() for name in
        ('backtest/ndx_offline_fund_signal_diagnostic_research.py',
         'scripts/ndx_offline_saved_fund_signal_diagnostic_20260923.py')})
    (output/'diagnostic.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(output),'snapshot_id':args.snapshot_id,'rows':[len(report['rows']) for report in reports]}))


if __name__=='__main__':
    main()
