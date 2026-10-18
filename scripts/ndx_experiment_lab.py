"""Run resumable, white-box Nasdaq-100 stock competition experiments.

PyCharm / PowerShell examples:
    python -B scripts/ndx_experiment_lab.py --plan-only
    python -B scripts/ndx_experiment_lab.py --max-jobs 1
    python -B scripts/ndx_experiment_lab.py --resume
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_competition import run_ndx_competition_research
from backtest.ndx_experiment_lab import (
    NdxExperimentLabError,
    bind_strategy_config,
    checkpoint_payload,
    expand_experiment_jobs,
    load_experiment_spec,
    read_checkpoint,
    utc_now_iso,
    validate_checkpoint,
    write_checkpoint,
    write_export_bundle,
    write_plan_csv,
)
from core.config import load_config
from core.helpers import atomic_write_text, setup_logging


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _checkpoint_path(output_dir: Path, job: dict) -> Path:
    return output_dir / "jobs" / f"{job['job_id']}.json"


def _load_valid_checkpoints(output_dir: Path, jobs: list[dict]) -> tuple[dict, dict]:
    completed = {}
    stale = {}
    for job in jobs:
        path = _checkpoint_path(output_dir, job)
        if not path.exists():
            continue
        try:
            payload = read_checkpoint(path)
            valid, reason = validate_checkpoint(payload, job)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            valid, reason = False, f"{type(exc).__name__}: {exc}"
            payload = None
        if valid:
            completed[job["job_id"]] = payload
        else:
            stale[job["job_id"]] = reason
    return completed, stale


def _run_job(base_cfg, job: dict) -> dict:
    cfg = copy.deepcopy(base_cfg)
    params = job["params"]
    cfg.data.start_date = params["start"]
    cfg.data.end_date = params.get("end")
    return run_ndx_competition_research(
        cfg,
        total_cap=params["total_cap"],
        monthly=params["monthly"],
        target_benchmark=params["target"],
        min_years=params["min_years"],
        lookback_years=params["lookback_years"],
        min_history_years=params["min_history_years"],
        top_ns=params["top_ns"],
        weight_modes=params["weight_modes"],
        safe_weights=params["safe_weights"],
        rebalance_months=params["rebalance_months"],
        max_weights=params["max_weights"],
        trade_cost_bps=params["trade_cost_bps"],
        safe_annual=params["safe_annual"],
        step_months=params["step_months"],
        max_windows=params["max_windows"],
        local_only=True,
        include_samples=bool(params["include_samples"]),
        construction_profiles=params.get("construction_profiles"),
        comparison_priority=params["comparison_priority"],
    )


def _write_error(output_dir: Path, job: dict, error: str) -> None:
    path = output_dir / "errors" / f"{job['job_id']}.json"
    atomic_write_text(
        path,
        json.dumps({
            "job_id": job["job_id"],
            "job_sha256": job["job_sha256"],
            "failed_at": utc_now_iso(),
            "error": error,
        }, ensure_ascii=False, indent=2) + "\n",
    )


def _format_seconds(value: float | None) -> str:
    if value is None or value < 0:
        return "-"
    seconds = int(round(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}h{minutes:02d}m"
    if minutes:
        return f"{minutes:d}m{seconds:02d}s"
    return f"{seconds:d}s"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "纳指100个股白盒实验室：可断点续跑，输出CSV/Excel；"
            "默认以012922为主目标，QQQ只作成分代理和辅助参照。"
        )
    )
    parser.add_argument(
        "--spec", default="config/ndx_experiment_lab_012922_v3.yaml"
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--phase", action="append", default=[])
    parser.add_argument("--job", action="append", default=[])
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="复用指纹和数据版本证据完整的已有作业检查点",
    )
    parser.add_argument("--force", action="store_true", help="重跑选中的已有作业")
    parser.add_argument("--max-jobs", type=int, default=0, help="本次最多执行多少个待跑作业")
    parser.add_argument(
        "--xlsx",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="同时生成多工作表Excel；CSV始终生成",
    )
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    setup_logging(logging.ERROR)
    spec_path = _resolve(args.spec)
    config_path = _resolve(args.config)
    spec = bind_strategy_config(load_experiment_spec(spec_path), config_path)
    jobs = expand_experiment_jobs(spec, phase_ids=args.phase)
    if args.job:
        requested = set(args.job)
        jobs = [job for job in jobs if job["job_id"] in requested]
        missing = requested - {job["job_id"] for job in jobs}
        if missing:
            raise NdxExperimentLabError(f"unknown job filters: {sorted(missing)}")
    if not jobs:
        raise NdxExperimentLabError("no enabled jobs match the selected filters")

    configured_output = args.output_dir or spec.get("output_dir") or "data/cache/research/ndx_lab"
    output_dir = _resolve(configured_output) / str(spec["experiment_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    completed, stale = _load_valid_checkpoints(output_dir, jobs)
    if stale:
        print("检测到失效检查点，将按当前规格重跑:")
        for job_id, reason in sorted(stale.items()):
            print(f"  {job_id}: {reason}")

    write_plan_csv(
        jobs,
        output_dir / "plan.csv",
        checkpoints=completed.values(),
    )
    expected_rows = sum(job["expected_candidate_rows"] for job in jobs)
    print("\n纳指100个股白盒实验计划")
    print(f"实验: {spec['experiment_id']}")
    print(f"作业: {len(jobs)} | 预计候选行: {expected_rows}")
    print(f"已完成有效检查点: {len(completed)} | 输出: {output_dir}")
    objective = spec.get("objective_contract") or {}
    if objective:
        analysis = spec.get("analysis_contract") or {}
        if analysis.get("decision_priority") == "incumbent_first":
            print(
                "主竞争基准: 当前8只配置 | "
                f"{objective['primary_target']}: 第二层参照 | "
                "QQQ: 成分代理与辅助参照"
            )
        else:
            print(
                f"主目标: {objective['primary_target']} | "
                "QQQ: 成分代理与辅助参照，不参与主优化 | 当前配置: 替换守门"
            )
    else:
        print("QQQ角色: benchmark only；实验失败只作用于当前形态。")
    if args.plan_only:
        print(f"计划文件: {output_dir / 'plan.csv'}")
        return 0

    pending = []
    for job in jobs:
        has_valid = job["job_id"] in completed
        if args.force or not (args.resume and has_valid):
            pending.append(job)
    if args.max_jobs > 0:
        pending = pending[:args.max_jobs]

    base_cfg = load_config(config_path)
    errors = {}
    durations = []
    interrupted = False
    try:
        for index, job in enumerate(pending, start=1):
            params = job["params"]
            print(
                f"\n[{index}/{len(pending)}] {job['job_id']} | "
                f"LB={params['lookback_years']:g}y cost={params['trade_cost_bps']:g}bp | "
                f"预计 {job['expected_candidate_rows']} 行"
            )
            started_at = utc_now_iso()
            started = time.perf_counter()
            try:
                result = _run_job(base_cfg, job)
                duration = time.perf_counter() - started
                payload = checkpoint_payload(
                    job,
                    result,
                    started_at=started_at,
                    duration_seconds=duration,
                )
                write_checkpoint(_checkpoint_path(output_dir, job), payload)
                (output_dir / "errors" / f"{job['job_id']}.json").unlink(
                    missing_ok=True
                )
                completed[job["job_id"]] = payload
                durations.append(duration)
                print(
                    f"完成: {len(result.get('rows') or [])} 候选行 / "
                    f"{len(result.get('samples') or [])} 窗口行 / {_format_seconds(duration)}"
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                errors[job["job_id"]] = error
                _write_error(output_dir, job, error)
                print(f"失败: {error}")
                if not args.continue_on_error:
                    raise
            finally:
                manifest = write_export_bundle(
                    spec,
                    jobs,
                    completed.values(),
                    output_dir,
                    errors=errors,
                    write_xlsx=False,
                )
                remaining = len(pending) - index
                eta = (sum(durations) / len(durations) * remaining) if durations else None
                print(
                    f"进度: {manifest['completed_jobs']}/{manifest['planned_jobs']}，"
                    f"本次剩余ETA {_format_seconds(eta)}"
                )
    except KeyboardInterrupt:
        interrupted = True
        print("\n收到中断，已保留完成作业；下次使用 --resume 继续。")

    manifest = write_export_bundle(
        spec,
        jobs,
        completed.values(),
        output_dir,
        errors=errors,
        write_xlsx=args.xlsx,
    )
    print("\n白盒证据包")
    print(f"候选汇总: {output_dir / 'candidates.csv'}")
    print(f"逐窗口: {output_dir / 'windows.csv'}")
    print(f"逐次重选: {output_dir / 'selections.csv'}")
    print(f"失败门槛: {output_dir / 'gate_failures.csv'}")
    print(f"引擎跳过: {output_dir / 'engine_skips.csv'}")
    print(f"数据版本: {output_dir / 'versions.csv'}")
    if manifest.get("files", {}).get("workbook"):
        print(f"Excel: {output_dir / manifest['files']['workbook']}")
    if manifest.get("workbook_error"):
        print(f"Excel生成失败但CSV完整: {manifest['workbook_error']}")
    inconsistent_phases = [
        phase_id
        for phase_id, evidence in manifest.get("phase_version_consistency", {}).items()
        if not evidence.get("comparison_ready")
    ]
    if inconsistent_phases:
        print(
            "禁止横向比较：以下阶段混用了不同数据版本束："
            + ", ".join(inconsistent_phases)
        )
        print("确认缓存版本后使用 --force 重跑该阶段全部作业。")
    constraint_audit = manifest.get("selection_constraint_audit") or {}
    if constraint_audit.get("passed") is False:
        print(
            "禁止使用结果：逐次重选约束审计失败："
            + json.dumps(constraint_audit, ensure_ascii=False)
        )
    if interrupted:
        return 130
    if inconsistent_phases:
        return 2
    if constraint_audit.get("passed") is False:
        return 3
    if errors and not args.continue_on_error:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
