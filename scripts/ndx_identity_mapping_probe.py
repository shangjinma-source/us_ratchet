"""One small public-data mapping query; prints research evidence, writes no files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_identity_mapping_probe import ENDPOINT, build_mapping_jobs, build_mapping_observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--query", action="store_true", help="Explicitly query the public mapping API")
    arguments = parser.parse_args()
    source = ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv"
    raw_identity = source.read_bytes()
    jobs, _ = build_mapping_jobs(raw_identity, arguments.tickers)
    if not arguments.query:
        print(json.dumps({"status": "QUERY_NOT_REQUESTED", "jobs": jobs, "network_request_performed": False}))
        return 0
    request = Request(ENDPOINT, data=json.dumps(jobs).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        status = response.status
        raw_response = response.read()
    observation = build_mapping_observation(
        identity_csv_bytes=raw_identity, tickers=arguments.tickers,
        response_bytes=raw_response, http_status=status,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    print(json.dumps(observation, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"identity probe failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(2)
