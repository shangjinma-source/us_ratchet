"""通用工具：Windows 原子写 + PermissionError 重试、代理环境管理、路径解析。

沿用 valuation_grid 的做法：写临时文件再 os.replace（同卷原子），
遇 Windows 文件锁 PermissionError 时重试。
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("us_ratchet")


def setup_logging(level: int = logging.INFO) -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )


def atomic_write_text(path: str | Path, text: str,
                      retries: int = 5, delay: float = 0.2,
                      encoding: str = "utf-8") -> None:
    """原子写文本。临时文件同目录创建后 os.replace，Windows 上也是原子的。
    遇 PermissionError（文件被占用/杀软扫描）按 delay 退避重试。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(retries):
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
                f.write(text)
            os.replace(tmp, path)   # 原子替换
            return
        except PermissionError as e:
            last_err = e
            log.warning("原子写遇 PermissionError，重试 %d/%d: %s", attempt + 1, retries, e)
            time.sleep(delay)
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    assert last_err is not None
    raise last_err


# 数据源主机（用于 NO_PROXY 绕过）
_DATA_HOSTS = [
    "query1.finance.yahoo.com", "query2.finance.yahoo.com",
    "finance.yahoo.com", "fc.yahoo.com",
    "stooq.com", "stooq.pl",
]


@contextmanager
def proxy_env(proxy_cfg):
    """按配置临时设置 / 绕过代理环境变量，退出时恢复。

    - enabled=True 且 bypass_for_data_hosts=False：对所有请求走 url 指定的代理。
    - enabled=True 且 bypass_for_data_hosts=True：走代理，但把数据域名加入 NO_PROXY。
    - enabled=False：清空代理环境变量，强制直连（绕过系统代理）。
    """
    keys = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"]
    saved = {k: os.environ.get(k) for k in keys}
    try:
        if getattr(proxy_cfg, "enabled", False):
            url = proxy_cfg.url
            os.environ["HTTP_PROXY"] = os.environ["http_proxy"] = url
            os.environ["HTTPS_PROXY"] = os.environ["https_proxy"] = url
            if getattr(proxy_cfg, "bypass_for_data_hosts", True):
                no = ",".join(_DATA_HOSTS)
                os.environ["NO_PROXY"] = os.environ["no_proxy"] = no
        else:
            for k in keys:
                os.environ.pop(k, None)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def project_root() -> Path:
    """项目根 = 本文件上一级的上一级（core/ 的父目录）。"""
    return Path(__file__).resolve().parents[1]


def resolve(path_like: str | Path) -> Path:
    """相对路径相对项目根解析，绝对路径原样返回。"""
    p = Path(path_like)
    return p if p.is_absolute() else (project_root() / p)
