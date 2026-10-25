"""Render a static research equity/drawdown chart from a hash-bound report."""
import argparse
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as dates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, StrMethodFormatter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('book', 'report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    options = parser.parse_args()
    raw = options.book.read_bytes()
    book = json.loads(raw)
    report = json.loads(options.report.read_bytes())
    if (book['status'] != 'COMPLETE' or report['status'] != 'COMPLETE_REVIEWED_RESEARCH_REPORT'
            or report['input_hashes']['book'] != sha256(raw).hexdigest()):
        raise ValueError('COMPLETE_HASH_BOUND_REPORT_REQUIRED')
    initial = Fraction(report['initial_equity'])
    days = [date.fromisoformat(report['start_date'])]
    equity = [initial]
    for row in book['daily_ledger']:
        if Fraction(row['external_flow']):
            raise ValueError('NONZERO_EXTERNAL_FLOW')
        days.append(date.fromisoformat(row['date']))
        equity.append(Fraction(row['equity']))
    peak, drawdown = initial, []
    for value in equity:
        peak = max(peak, value)
        drawdown.append(value / peak - 1)
    if (equity[-1] != Fraction(report['final_equity']) or
            -min(drawdown) != Fraction(report['drawdown']['maximum_drawdown'])):
        raise ValueError('CHART_REPORT_MISMATCH')
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})
    figure, axes = plt.subplots(2, 1, figsize=(12, 7.2), sharex=True,
                               gridspec_kw={'height_ratios': [2, 1]}, layout='constrained')
    values = [float(v) for v in equity]
    axes[0].plot(days, values, color='#265c85', linewidth=1.7)
    axes[0].set_ylim(min(values) * .9, max(values) * 1.18)
    axes[0].axhline(float(initial), color='#89939d', linestyle='--', linewidth=1)
    axes[0].set_ylabel('Research equity (USD)')
    axes[0].yaxis.set_major_formatter(StrMethodFormatter('${x:,.0f}'))
    axes[0].set_title('V27 | 2021–2023 continuous individual-stock research', loc='left', weight='bold')
    caption = (f'Initial USD {float(initial):,.0f}  →  Final USD {values[-1]:,.0f}\n'
               f"CAGR {report['cagr']:.2%}  |  Maximum drawdown {float(-min(drawdown)):.2%}")
    axes[0].text(.02, .96, caption,
                 transform=axes[0].transAxes, va='top', color='#25313a',
                 bbox=dict(facecolor='white', alpha=.9, edgecolor='none'))
    losses = [float(v) for v in drawdown]
    axes[1].fill_between(days, losses, 0, color='#b6433f', alpha=.18)
    axes[1].plot(days, losses, color='#b6433f', linewidth=1.3)
    axes[1].set_ylabel('Drawdown from peak')
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1].xaxis.set_major_locator(dates.MonthLocator(bymonth=[1, 7]))
    axes[1].xaxis.set_major_formatter(dates.DateFormatter('%Y-%m'))
    for axis in axes:
        axis.grid(axis='y', alpha=.18)
        axis.spines[['top', 'right']].set_visible(False)
        axis.margins(x=0)
    figure.supxlabel('Next-open model; 0 commission + 5bp slippage; dividends before withholding tax.\nHistorical research, not actual account performance or independent out-of-sample evidence.', fontsize=9)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    for extension in ('.png', '.svg'):
        figure.savefig(options.output.with_suffix(extension), dpi=170, facecolor='white')
    plt.close(figure)


if __name__ == '__main__':
    main()
