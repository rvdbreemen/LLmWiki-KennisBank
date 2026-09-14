#!/usr/bin/env python3
"""Run the memory sweep back to back until the transcript backlog is empty.

One sweep run stops on its own budget and leaves the rest pending. That is
deliberate, because the sweep shares a GPU with the embedding model that serves
the recall hot path. It also means a backlog only disappears by repeating the
run, and nothing else in this repository does that. On 2026-09-09 a backlog of
97 transcripts had stood still for 35 hours.

Stopping: create ``<vault>/.claude/.sweep-stop``. The chain stops AFTER the run
that is busy at that moment. A running sweep is never interrupted, because the
watermark is append-only: a half-processed transcript would be marked swept and
the rest of it lost for good.

Logs one line per run to ``<vault>/.claude/sweep-chain.log``.

Stdlib only. Usage: python3 sweep-chain.py
"""
from __future__ import annotations

import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

#: Sibling modules come from this script's own directory, not from a
#: vault-relative path. Installed the two are the same directory; in a checkout
#: they are not, and a vault-relative import would then load the INSTALLED copy
#: of _sweepstate while running the checkout's chain.
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from _vaultpath import vault_root  # noqa: E402

#: Well above any backlog seen so far, so the count is never the reason the
#: chain stops. Running out of work or the stop flag are the intended exits.
MAX_RUNS = 40

#: Transcripts per sweep run. This is the knob that matters, not the time
#: budget. Measured: capture costs ~300 s per transcript, but the maintenance
#: tail after the loop costs ~3300 s PER RUN and does not depend on how many
#: transcripts the run handled. Cost per transcript is therefore 300 + 3300/N,
#: measured at 580 s for N=10 and 277 s for N=40. Raising KB_SWEEP_TIME_BUDGET
#: on its own changed nothing, because --max bound first (processed 10 with
#: budget_reached False).
#:
#: The ceiling on N is the lease, not the return: _sweepstate.LEASE_MAX_SEC is
#: 14400 s, and a run that outlives it stops refreshing, after which a second
#: sweep can start beside it. Capture of 40 * 300 s plus the tail stays under.
MAX_PER_RUN = 40

#: A run that processed nothing while it DID hold the lock points at something
#: structural: the model is gone, capture is off, or one transcript throws the
#: same exception every time. A run that never got the lock does not count here;
#: that case is handled separately as a missed turn.
#:
#: Five rather than three: a run can only reach zero if the transcript itself
#: fails, because the time budget cuts BETWEEN transcripts and the first check
#: falls on elapsed zero, so every run starts its first transcript regardless.
#: The margin is free and stopping too early costs a whole night of nothing.
MAX_EMPTY_RUNS = 5

#: Do not start a new sweep below this. Two sweep wrappers were killed for
#: memory on the development machine at 0.7 GB free, with commit at 65.0 of
#: 67.4 GB. The maintenance pass also loads a corpus snapshot of thousands of
#: files every run. Waiting is the right answer here: the work does not run off.
MIN_FREE_GB = 1.5
MEMORY_WAIT_SEC = 300
MEMORY_MAX_WAIT_SEC = 7200

#: Free memory on a loaded machine is a snapshot, not a state: measured swings
#: of 2.5 to 4.4 GB within four seconds with no sweep running. A gate on a
#: single reading is a coin flip rather than a gate, and the first version of
#: this script blocked at a false 1.7 GB where the median of three read 6.6 GB.
MEMORY_SAMPLES = 3
MEMORY_SAMPLE_GAP_SEC = 1.0

#: How long to wait out a sweep started elsewhere, typically by the
#: session-start hook.
LOCK_MAX_WAIT_SEC = 7200

#: What memory-sweep.py prints when it could not take the lock. Kept as a
#: constant because it couples two scripts across a subprocess boundary:
#: scripts/memory-sweep.py writes this line and tests/test_sweep_chain.py pins
#: that the two still agree, so translating one side fails visibly instead of
#: turning every missed turn into a silent zero-progress run.
SKIP_MARKER = "memory-sweep: overgeslagen, er draait al een sweep"


def stop_flag() -> Path:
    return vault_root() / ".claude" / ".sweep-stop"


def log_path() -> Path:
    return vault_root() / ".claude" / "sweep-chain.log"


def log(line: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {line}\n")
    except OSError:
        pass
    print(f"{stamp} {line}", flush=True)


def _sweepstate():
    import _sweepstate
    return _sweepstate


def pending() -> int:
    return len(_sweepstate().pending())


def lock_busy() -> bool:
    ss = _sweepstate()
    lock = ss.lock_path()
    return lock.exists() and not ss.is_free(lock)


def _one_memory_sample() -> "float | None":
    """Free physical memory in GB, or None when it cannot be measured."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
            capture_output=True, text=True, timeout=60)
        return int(out.stdout.strip()) / (1024 * 1024)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def free_gb() -> "float | None":
    """Median of MEMORY_SAMPLES readings, so one outlier cannot decide.

    None means carry on: a chain that stalls because it cannot measure memory
    is worse than one that takes the risk it already took before this gate
    existed.
    """
    samples = []
    for i in range(MEMORY_SAMPLES):
        sample = _one_memory_sample()
        if sample is None:
            return None
        samples.append(sample)
        if i + 1 < MEMORY_SAMPLES:
            time.sleep(MEMORY_SAMPLE_GAP_SEC)
    return statistics.median(samples)


def low_memory() -> bool:
    free = free_gb()
    return free is not None and free < MIN_FREE_GB


def wait_until_false(condition, reason: str, max_sec: float,
                     step: float = 30) -> bool:
    """Wait until condition() is false. False when time ran out or stopped."""
    begin = time.time()
    reported = False
    while condition():
        if stop_flag().exists():
            log(f"stop flag seen while waiting for {reason}")
            return False
        if time.time() - begin > max_sec:
            log(f"waited too long for {reason} ({max_sec}s); chain stops")
            return False
        if not reported:
            log(f"waiting for {reason}")
            reported = True
        time.sleep(step)
    return True


def run_sweep() -> "tuple[int, str]":
    """Run one sweep. Returns its exit status and the last line it printed."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "memory-sweep.py"),
         "--max", str(MAX_PER_RUN)],
        capture_output=True, text=True)
    lines = (proc.stdout or "").strip().splitlines()
    return proc.returncode, lines[-1] if lines else "no output"


def main() -> int:
    vault = vault_root()
    if not vault.exists():
        print(f"vault not found: {vault}", file=sys.stderr)
        return 2
    free = free_gb()
    log(f"chain starts, {pending()} transcripts pending"
        f"{f', {free:.1f} GB free' if free is not None else ''}")

    # Wait out a running sweep rather than standing next to it.
    if not wait_until_false(lock_busy, "the running sweep",
                            max_sec=LOCK_MAX_WAIT_SEC):
        return 0

    empty = 0
    for run in range(1, MAX_RUNS + 1):
        if stop_flag().exists():
            log(f"stop flag seen; chain stops after {run - 1} runs")
            return 0
        before = pending()
        if before == 0:
            log("nothing pending; done")
            return 0
        if not wait_until_false(low_memory, f"memory (>{MIN_FREE_GB} GB free)",
                                max_sec=MEMORY_MAX_WAIT_SEC,
                                step=MEMORY_WAIT_SEC):
            return 0

        begin = time.time()
        status, last = run_sweep()
        duration = round(time.time() - begin)

        # Another sweep beat us to it; the session-start hook launches one too.
        # That is a missed turn, not a failed run: wait and try again without
        # counting it toward the give-up threshold.
        if SKIP_MARKER in last:
            log(f"run {run}: another sweep held the lock; waiting")
            if not wait_until_false(lock_busy, "the other sweep",
                                    max_sec=LOCK_MAX_WAIT_SEC):
                return 0
            continue

        after = pending()
        done = before - after
        free = free_gb()
        log(f"run {run}: {done} processed in {duration}s, {after} still pending"
            f"{f', {free:.1f} GB free' if free is not None else ''} | {last}")

        if status != 0:
            log(f"run {run} ended with status {status}; chain stops")
            return status
        empty = empty + 1 if done == 0 else 0
        if empty >= MAX_EMPTY_RUNS:
            log(f"{empty} runs in a row without progress; chain stops")
            return 1
    log(f"MAX_RUNS ({MAX_RUNS}) reached, {pending()} still pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
