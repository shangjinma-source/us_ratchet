"""One receipt-native two-session AAPL conditional quote probe; no network/fit."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_current_receipt_quote_guard_research as guard
from scripts.ndx_current_22_price_capture_20260919 import save


if __name__=='__main__':
    folder=guard.BASE/'current79_new_asof_capture_20260919_v1'
    receipt=json.loads((folder/'AAPL.receipt.json').read_bytes())
    report=guard.reconstruct_current_receipt_quote(ticker='AAPL',raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],calendar=['2026-09-16','2026-09-17'],quote_field_basis=guard.nominal.BASIS)
    source=str(Path(__file__).resolve());sha=hashlib.sha256(Path(source).read_bytes()).hexdigest()
    expected=report['historical_expected_source_hashes'];guard.gap.merge(expected,{source:sha})
    guard.gap.attach_partition(report,expected,guard.gap.partition(expected,guard.gap.drift.load_contract(),require_all=True))
    output=guard.BASE/'current_receipt_quote_guard_20260919_v1';output.mkdir(exist_ok=True)
    path=output/'aapl_two_session_probe.json';digest=save(path,report)
    guard.gap.partition(expected,guard.gap.drift.load_contract(),require_all=True)
    print(json.dumps(dict(path=str(path),sha256=digest,rows=len(report['reconstruction']['rows']))))
