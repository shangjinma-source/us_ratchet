"""Shared deployment withdrawal records; not configurable by runtime clients."""

SOURCE_WITHDRAWALS = ({
    "input_path": "tmp/monthly_captured_training_20261014_v2/input.json",
    "input_sha256": "6ca44931cd8c39f34ae1b48b1fa2dfcf858480342bc4704b1ab48fa49b99757a",
    "descriptor_sha256": "ecc1511d1949a7b061bcd2da9290650b38ec0ba13e9a99299770292ad91e7984",
    "reason": "TRI 历史 NASDAQ USD 未复权价格口径未获独立认证；旧训练域仍含 TRI，撤回新计算、报价和新模拟接受资格。独立剔除实验不替代生产来源。",
    "evidence": {
        "tmp/tri_independent_price_source_check_20261016_v1/last_route_findings.json":
            "7d695b355931194a69427b8dca6aaab1f6b04d1e24c5c46c94a1f7d439bf5351",
    },
},)
