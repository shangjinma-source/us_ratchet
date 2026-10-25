"""Latest display candles, isolated from training and executable suggestions."""
from copy import deepcopy
from datetime import datetime, timezone, date
from hashlib import sha256
import json
import math
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.strategy_bounded_source_gate_v1 import _no_links

NY = ZoneInfo("America/New_York")
MAX_BYTES = 4 * 1024 * 1024


def display_url(ticker):
    return ("https://query1.finance.yahoo.com/v8/finance/chart/"
            + quote(ticker, safe="") + "?range=2y&interval=1d&events=div%2Csplits")


def fetch_display_daily(ticker):
    url = display_url(ticker)
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as response:
        raw = response.read(MAX_BYTES + 1)
        require(response.status == 200 and response.url == url, "DISPLAY_TRANSPORT_INVALID")
    require(0 < len(raw) <= MAX_BYTES, "DISPLAY_BODY_BUDGET")
    return raw


def monthly_display_context(monthly, security_id):
    """A server-owned resolver; the client never supplies ticker or source paths."""
    with monthly.snapshot_operation() as snapshot:
        state = deepcopy(monthly.accounts.read())
        target = deepcopy(monthly.current())
        require(state is not None and target is not None, "DISPLAY_SAVED_TARGET_REQUIRED")
        quantities = target["payload"]["target_quantities"]
        require(state["shares"].get(security_id, 0) > 0 or quantities.get(security_id, 0) > 0,
                "DISPLAY_SECURITY_NOT_HELD_OR_SELECTED")
        runtime, configuration = monthly._for_target(target)
        provider = runtime.execution_provider.__self__
        raw = provider._read(provider.manifest_path, provider.manifest_hash)
        manifest = json.loads(raw)
        rows = [row for row in manifest["candidates"]
                if row.get("security_id") == security_id and row.get("status") == "READY_CONDITIONAL"]
        require(len(rows) == 1, "DISPLAY_BASELINE_REQUIRED")
        row = rows[0]
        identity = monthly.resolve_identity(row["ticker"])
        require(identity["security_id"] == security_id, "DISPLAY_IDENTITY_MISMATCH")
        path = row["training_source"]
        baseline = provider._read(path, manifest["source_hashes"][path])
        return dict(account_revision=state["revision"], target_id=target["target_id"],
                    security_id=security_id, ticker=row["ticker"], identity=identity,
                    snapshot=dict(snapshot), baseline=baseline,
                    baseline_sha256=sha256(baseline).hexdigest(),
                    manifest_sha256=provider.manifest_hash)


def aggregate(daily, interval):
    groups = {}
    for row in daily:
        day = date.fromisoformat(row["date"])
        key = row["date"] if interval == "day" else (
            str(day.isocalendar()[:2]) if interval == "week" else row["date"][:7])
        groups.setdefault(key, []).append(row)
    result = []
    for rows in groups.values():
        result.append(dict(date=rows[-1]["date"], first_date=rows[0]["date"],
                           through=rows[-1]["date"],
                           source_timestamps=[r["source_timestamp"] for r in rows],
                           open=rows[0]["open"], high=max(r["high"] for r in rows),
                           low=min(r["low"] for r in rows), close=rows[-1]["close"],
                           volume=None if any(r["volume"] is None for r in rows)
                           else sum(r["volume"] for r in rows),
                           complete=all(r["complete"] for r in rows)))
    return result


class LatestDisplayChartsV1:
    def __init__(self, *, context_reader, validate_sources, output_root,
                 clock=None, fetch=fetch_display_daily, sleep=None):
        self.context = context_reader
        self.gate = validate_sources
        self.output = Path(output_root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.fetch = fetch
        self.sleep = sleep or time.sleep

    def bars(self, *, security_id, interval="day", bars=90):
        require(type(security_id) is str and interval in ("day", "week", "month")
                and type(bars) is int and 1 <= bars <= 260, "DISPLAY_ARGUMENTS")
        self.gate()
        context = self.context(security_id)
        require(context["security_id"] == security_id, "DISPLAY_CONTEXT_BINDING")
        started = self.clock()
        require(started.utcoffset() is not None, "DISPLAY_AWARE_CLOCK")
        _no_links(self.output)
        directory = self.output / uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)

        def save(name, raw):
            with (directory / name).open("xb") as stream:
                stream.write(raw)

        save("started.json", canonical(dict(security_id=security_id,
             ticker=context["ticker"], started_at=started.isoformat(), display_only=True)))
        try:
            raw = self.fetch(context["ticker"])
            received = self.clock()
            require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "DISPLAY_BODY_BUDGET")
            save("provider.raw", raw)
            receipt = dict(url=display_url(context["ticker"]), raw_sha256=sha256(raw).hexdigest(),
                           started_at=started.isoformat(), received_at=received.isoformat(),
                           baseline_sha256=context["baseline_sha256"], display_only=True)
            save("receipt.json", canonical(receipt))
            require(started <= received, "DISPLAY_CLOCK_REVERSED")
            channel = parse_provider_ohlc(raw, context["ticker"])
            baseline = parse_provider_ohlc(context["baseline"], context["ticker"])
            require(sha256(context["baseline"]).hexdigest() == context["baseline_sha256"],
                    "DISPLAY_BASELINE_HASH")
            document = json.loads(raw)["chart"]["result"][0]
            meta = document["meta"]
            require(meta.get("exchangeName") in ("NMS", "NGM", "NCM"), "DISPLAY_EXCHANGE")
            old = dict(zip(baseline["dates"], baseline["values"]))
            overlap = [(day, values) for day, values in zip(channel["dates"], channel["values"])
                       if day in old and all(v is not None for v in values[:4] + old[day][:4])]
            require(len(overlap) >= 5, "DISPLAY_UNIT_OVERLAP_REQUIRED")
            require(all(abs(a-b) <= max(abs(b)*0.000001, 0.000001)
                        for day, values in overlap for a, b in zip(values[:4], old[day][:4])),
                    "DISPLAY_PRICE_UNITS_CHANGED")
            require(not document.get("events", {}).get("splits"), "DISPLAY_SPLIT_REVIEW_REQUIRED")
            today = received.astimezone(NY).date().isoformat()
            regular = meta.get("currentTradingPeriod", {}).get("regular", {})
            opening = datetime.fromtimestamp(regular["start"], timezone.utc)
            closing = datetime.fromtimestamp(regular["end"], timezone.utc)
            require(opening < closing, "DISPLAY_SESSION_INVALID")
            price_stamp = meta.get("regularMarketTime")
            require(type(price_stamp) is int, "DISPLAY_PRICE_TIME_INVALID")
            quote_at = datetime.fromtimestamp(price_stamp, timezone.utc)
            ahead = (quote_at - received).total_seconds()
            require(ahead <= 1, "DISPLAY_FUTURE_PRICE")
            validated_at = received
            if ahead > 0:
                # Vendor timestamps have whole-second precision. Wait for the
                # real clock; keep original transport receipt and never refetch.
                self.sleep(ahead + 0.001)
                validated_at = self.clock()
                require(validated_at >= received, "DISPLAY_CLOCK_REVERSED")
                require(quote_at <= validated_at and (validated_at-received).total_seconds() <= 2,
                        "DISPLAY_FUTURE_PRICE")
            price = meta.get("regularMarketPrice")
            require(type(price) in (int, float) and math.isfinite(price) and price > 0,
                    "DISPLAY_PRICE_INVALID")
            daily = []
            for day, values, source_timestamp in zip(channel["dates"], channel["values"], document["timestamp"]):
                require(day <= today, "DISPLAY_FUTURE_BAR")
                require(type(source_timestamp) is int and
                        datetime.fromtimestamp(source_timestamp, timezone.utc) <= received,
                        "DISPLAY_FUTURE_BAR_TIMESTAMP")
                if any(v is None for v in values[:4]):
                    continue
                complete = day < today
                if day == today:
                    require(opening.astimezone(NY).date().isoformat() == today and received >= opening,
                            "DISPLAY_CURRENT_SESSION_MISMATCH")
                    complete = received >= closing
                daily.append(dict(zip(("date", "open", "high", "low", "close", "volume"),
                                      [day] + values), complete=complete,
                                  source_timestamp=source_timestamp))
            require(daily, "DISPLAY_NO_BARS")
            self.gate()
            require(self.context(security_id) == context, "DISPLAY_SNAPSHOT_CHANGED")
            finished = self.clock()
            require(validated_at <= finished, "DISPLAY_CLOCK_REVERSED")
            grouped = aggregate(daily, interval)[-bars:]
            current_date = date.fromisoformat(today)
            for row in grouped:
                through = date.fromisoformat(row["through"])
                if interval == "week" and through.isocalendar()[:2] == current_date.isocalendar()[:2]:
                    row["complete"] = False
                if interval == "month" and row["through"][:7] == today[:7]:
                    row["complete"] = False
            result = dict(status="DISPLAY_ONLY", security_id=security_id, ticker=context["ticker"],
                          account_revision=context["account_revision"], target_id=context["target_id"],
                          interval=interval, bars=grouped,
                          as_of=daily[-1]["date"], current_bar_complete=daily[-1]["complete"],
                          price=price, price_time=price_stamp,
                          price_session="REGULAR", period_complete=grouped[-1]["complete"],
                          received_at=received.isoformat(), verified_at=validated_at.isoformat(),
                          evidence_directory=str(directory),
                          raw_sha256=receipt["raw_sha256"], unit_check="CONDITIONAL_OVERLAP_ONLY",
                          corporate_actions_completeness_verified=False,
                          executable=False, training_modified=False)
            save("complete.json", canonical(result))
            return result
        except Exception as error:
            code = error.args[0] if type(error) is ValueError and len(error.args) == 1 else None
            code = code if type(code) is str and code.startswith("DISPLAY_") and code.replace("_", "").isalnum() else "DISPLAY_VALIDATION_FAILED"
            save("failed.json", canonical(dict(status="DISPLAY_UNAVAILABLE", reason=code, account_mutated=False)))
            raise
