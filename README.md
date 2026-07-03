# us_ratchet

美股科技篮子棘轮策略工具：支持历史回测、NAV-DD 面板、实盘状态、今日执行建议、战术挂单研究、券商流水导入和前端仪表盘。

## Quick Start

```powershell
pip install -r requirements.txt
uvicorn api.server:app --host 127.0.0.1 --port 8010
```

Then open `http://127.0.0.1:8010/`.

## Notes

Runtime portfolio state and market cache files are intentionally ignored by Git:

- `data/state.json`
- `data/state.json.bak`
- `data/audit.jsonl`
- `data/cache/*.csv`
