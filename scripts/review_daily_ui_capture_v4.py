"""Strict unified eight-column UI review; currently only unreviewed news cells."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from scripts.review_daily_ui_capture_v3 import review as review_previous

HEADERS = ['股票', '实际持有', '本月目标', '今日有效目标', '今日动作', '建议限价', '原因', '新闻影响']
UNREVIEWED = '未复核，不代表无风险'


def review(capture):
    # Older captures have page text, not a dedicated table-header DOM snapshot.
    # Require its exact header line and each exact row; never infer a news column
    # merely from the number of cells.
    lines = capture.get('page_text', '').splitlines()
    if lines.count('\t'.join(HEADERS)) != 1:
        raise ValueError('UNIFIED_TABLE_HEADER_REQUIRED')
    rows = capture.get('visible_rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('UNIFIED_TABLE_ROWS_REQUIRED')
    normalized = deepcopy(capture)
    for source, target in zip(rows, normalized['visible_rows']):
        cells = source.get('dom_cells')
        if not isinstance(cells, list) or len(cells) != 8:
            raise ValueError('UNIFIED_TABLE_EIGHT_COLUMNS_REQUIRED')
        if cells[7] != UNREVIEWED:
            raise ValueError('NEWS_REVIEW_STATE_OUTSIDE_ACCEPTANCE_SCOPE')
        if any(not isinstance(cell, str) for cell in cells) or lines.count('\t'.join(cells)) != 1:
            raise ValueError('UNIFIED_TABLE_PAGE_ROW_MISMATCH')
        target['dom_cells'] = cells[:7]
    result = review_previous(normalized)
    return dict(result, unified_table_columns=8,
                news_column_scope='Only exact unreviewed placeholder; no AI opinion or AI order acceptance',
                header_evidence='Exact page_text header and rows; original capture has no dedicated DOM headers')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_path', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(review(json.loads(arguments.capture_path.read_bytes())), ensure_ascii=False, indent=2))
