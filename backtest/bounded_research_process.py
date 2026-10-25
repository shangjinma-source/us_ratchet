"""Run one frozen Python research worker with a deadline and no retry."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from hashlib import sha256


def run_worker(*, script, expected_sha256, arguments, output_directory, timeout_seconds):
    if isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 6 * 60 * 60:
        raise ValueError('POSITIVE_BUDGET_AT_MOST_SIX_HOURS_REQUIRED')
    script = Path(script).resolve(strict=True)
    if script.suffix != '.py' or sha256(script.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('FROZEN_PYTHON_WORKER_REQUIRED')
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        raise ValueError('EXPLICIT_ARGUMENT_LIST_REQUIRED')
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=False)  # Never restart/overwrite a prior run.
    command = [sys.executable, str(script), *arguments]
    started = time.monotonic()
    result = dict(status='STARTING', script=str(script), script_sha256=expected_sha256,
                  timeout_seconds=timeout_seconds, attempts=1, retry_allowed=False)

    def save():
        pending = output / 'status.pending.json'
        pending.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        pending.replace(output / 'status.json')

    save()
    with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
        try:
            process = subprocess.Popen(command, shell=False, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
        except OSError as error:
            result.update(status='LAUNCH_FAILED', error_type=type(error).__name__,
                          elapsed_seconds=time.monotonic()-started)
            save()
            raise
        result.update(status='RUNNING', pid=process.pid)
        save()
        try:
            code = process.wait(timeout=max(0, timeout_seconds-(time.monotonic()-started)))
            result.update(status='WORKER_EXITED_REVIEW_REQUIRED' if code == 0 else 'WORKER_FAILED', exit_code=code)
        except subprocess.TimeoutExpired:
            # Only this live child PID/process group is targeted; no global name kill.
            if process.poll() is None:
                if os.name == 'nt':
                    killed = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                    result['tree_kill_exit_code'] = killed.returncode
                    if killed.returncode and process.poll() is None:
                        result.update(status='TERMINATION_FAILED', elapsed_seconds=time.monotonic()-started)
                        save()
                        raise RuntimeError('RESEARCH_TREE_TERMINATION_FAILED')
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            result.update(status='TIMED_OUT_INCONCLUSIVE', exit_code=process.returncode)
        result['elapsed_seconds'] = time.monotonic()-started
        save()
    return result
