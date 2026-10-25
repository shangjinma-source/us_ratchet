"""Opt-in bounded exception tracing for a reviewed future paper launcher.

No account or scheduler operation is performed here. Messages, locals and URLs
are deliberately excluded; original failure and later persistence failure remain.
"""
from pathlib import Path
import sys


def observe(call, *, root, sink):
    root = Path(root).resolve()
    records = []
    watched = {"bootstrap_current_quantity_v2_simulation.py",
               "run_registered_paper_automation.py",
               "run_registered_quantity_v2_paper_simulation.py",
               "current_quantity_v2_current_cash_sources.py",
               "current_quantity_v2_current_cash_service.py"}
    previous = sys.gettrace()
    if previous is not None:
        raise ValueError("EXISTING_TRACE_REQUIRES_REVIEW")

    def collect(frame, event, argument):
        if event == "call" and Path(frame.f_code.co_filename).name not in watched:
            return None
        if event == "exception":
            filename = Path(frame.f_code.co_filename)
            if filename.name in watched and filename.resolve().is_relative_to(root):
                kind, error, _ = argument
                # Only a simple uppercase diagnostic code is eligible for text.
                if kind in (StopIteration, GeneratorExit):
                    return trace
                try:
                    message = str(error)
                except Exception:
                    message = ""
                code = message if (0 < len(message) <= 160
                                   and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for c in message)) else None
                record = dict(file=filename.resolve().relative_to(root).as_posix(),
                              function=frame.f_code.co_name, line=frame.f_lineno,
                              exception_type=kind.__name__, reason_code=code)
                if record not in records and len(records) < 64:
                    records.append(record)
        return trace

    def trace(frame, event, argument):
        try:
            return collect(frame, event, argument)
        except Exception:
            return None

    sys.settrace(trace)
    try:
        return call()
    finally:
        sys.settrace(previous)
        try:
            sink(dict(schema="PAPER_SAFE_EXCEPTION_DIAGNOSTIC_V1", records=records,
                      bounded=True, raw_messages_included=False, locals_included=False))
        except Exception:
            # Diagnostic failure must never replace the trading failure/return.
            try:
                sys.stderr.write("PAPER_DIAGNOSTIC_SINK_FAILED\n")
            except Exception:
                pass
