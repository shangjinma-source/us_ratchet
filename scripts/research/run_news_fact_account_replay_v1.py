"""Replay freshly source-validated news facts against the frozen local account.

Reuses saved model output; no model calls, network, or production changes.
This strict numeric rule is distinct from qualitative delivery-delay research.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.news_fact_rule_bridge_v1 import bridge
from scripts.research.run_mrna_causal_local_v1 import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='tmp/news_fact_account_replay_20261027_v2')
    options = parser.parse_args()
    result = bridge(ROOT, ROOT/'tmp/news_fact_extraction_20261027/run1',
                    ROOT/'tmp/news_fact_rule_bridge_20261027/source_review.json')
    if result.get('validation_complete') is not True:
        raise ValueError('FACT_BRIDGE_INPUT_VALIDATION_INCOMPLETE')
    summary = run(ROOT, fact_bridge=result, output_relative=options.output)
    print(json.dumps({key: summary.get(key) for key in (
        'status', 'baseline_daily_exact', 'no_admission_account_unchanged',
        'first_different_account_date', 'terminal_equity_delta')}))


if __name__ == '__main__':
    main()
