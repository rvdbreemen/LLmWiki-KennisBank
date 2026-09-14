"""Tests for scripts/sweep-chain.py.

The chain is a loop around a subprocess that takes hours, so nothing here runs
a real sweep. What is worth pinning is the three judgements the loop makes and
the one coupling it cannot see for itself: whether a run counted, whether the
machine has room, and when the chain is allowed to stop.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "sweep_chain_under_test", SCRIPTS / "sweep-chain.py")
chain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chain)

#: setUp stubs free_gb so the loop never shells out to PowerShell. The
#: memory-gate tests are about that function itself, so they put the real
#: one back and feed it readings instead.
_REAL_FREE_GB = chain.free_gb


class SweepChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb-chain-"))
        self.vault = self.tmp / "vault"
        (self.vault / ".claude").mkdir(parents=True)
        self._saved = os.environ.get("KENNISBANK_VAULT")
        os.environ["KENNISBANK_VAULT"] = str(self.vault)
        # No real sweeps and no real waiting: every test drives the loop
        # through these seams.
        self.runs = []
        self._results = [(0, "no sweep scripted")]
        self._patch("run_sweep", self._next_run)
        self._patch("lock_busy", lambda: False)
        self._patch("MEMORY_SAMPLE_GAP_SEC", 0)
        self._patch("free_gb", lambda: None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("KENNISBANK_VAULT", None)
        else:
            os.environ["KENNISBANK_VAULT"] = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self, name, value):
        old = getattr(chain, name)
        setattr(chain, name, value)
        self.addCleanup(setattr, chain, name, old)

    def _next_run(self):
        """One scripted sweep result per call; the last one repeats."""
        self.runs.append(len(self.runs) + 1)
        return self._results[min(len(self.runs), len(self._results)) - 1]

    def _sweeps(self, *results):
        self._results = list(results)

    def _pending(self, *values):
        """pending() reads these in order; the last value repeats."""
        series = list(values)
        seen = {"i": 0}

        def read():
            i = min(seen["i"], len(series) - 1)
            seen["i"] += 1
            return series[i]
        self._patch("pending", read)

    def _samples(self, *values):
        it = iter(values)
        self._patch("_one_memory_sample", lambda: next(it))
        self._patch("free_gb", _REAL_FREE_GB)

    # --- the memory gate -------------------------------------------------

    def test_a_single_low_outlier_does_not_block_a_run(self):
        """Free memory swings by gigabytes per second on a loaded machine.

        Measured here: 2.5 to 4.4 GB within four seconds with no sweep
        running. A gate on one reading blocked the chain at a false 1.7 GB
        where the median of three read 6.6. Taking the median is what makes
        this a gate rather than a coin flip.
        """
        self._samples(0.7, 6.6, 6.6)
        self.assertAlmostEqual(chain.free_gb(), 6.6)
        self._samples(0.7, 6.6, 6.6)
        self.assertFalse(chain.low_memory(),
                         "one low reading out of three is noise, not a state")

    def test_the_median_decides_the_other_way_too(self):
        """Two low readings are a state, not an outlier, so the gate holds."""
        self._samples(6.6, 0.7, 0.7)
        self.assertAlmostEqual(chain.free_gb(), 0.7)
        self._samples(6.6, 0.7, 0.7)
        self.assertTrue(chain.low_memory())

    def test_being_unable_to_measure_is_no_reason_to_stop(self):
        self._samples(None, None, None)
        self.assertIsNone(chain.free_gb())
        self._samples(None, None, None)
        self.assertFalse(chain.low_memory())

    # --- a missed turn is not a failed run -------------------------------

    def test_a_missed_turn_does_not_count_toward_giving_up(self):
        """The session-start hook launches a sweep too; that is no failure.

        MAX_EMPTY_RUNS is 5. If a skipped run counted as one without progress,
        the chain would stop here with status 1 after five turns, on a
        perfectly healthy vault. It must keep going until MAX_RUNS.
        """
        gekeken = []
        self._patch("lock_busy", lambda: bool(gekeken.append(1)) or False)
        self._sweeps((0, chain.SKIP_MARKER))
        self._pending(12)
        self.assertEqual(chain.main(), 0)
        self.assertEqual(len(self.runs), chain.MAX_RUNS)
        # Run count alone does not discriminate: a chain that never matched the
        # marker and fell through as zero-progress-with-reset would also reach
        # MAX_RUNS. What separates the two is that the skip path waits out the
        # other sweep, once before the loop and once per missed turn.
        self.assertEqual(len(gekeken), chain.MAX_RUNS + 1,
                         "each missed turn must wait for the other sweep")

    def test_a_run_that_held_the_lock_and_did_nothing_does_count(self):
        """The counter-test: with the lock held, zero processed is a fault.

        The line below is a synthetic fixture, not real sweep output. All that
        matters about it is that it does NOT carry SKIP_MARKER, so the loop
        treats the run as one that held the lock.
        """
        self._sweeps((0, "a line that is not the skip marker"))
        self._pending(12)
        self.assertEqual(chain.main(), 1)
        self.assertEqual(len(self.runs), chain.MAX_EMPTY_RUNS)

    def test_the_skip_marker_is_still_the_line_memory_sweep_prints(self):
        """The coupling crosses a subprocess, so no import breaks when that
        sentence is translated. This test does."""
        source = (SCRIPTS / "memory-sweep.py").read_text(encoding="utf-8")
        self.assertIn(chain.SKIP_MARKER, source,
                      "memory-sweep.py no longer prints this line, so the "
                      "chain now reads every missed turn as zero progress")

    # --- the stop flag ---------------------------------------------------

    def test_the_stop_flag_holds_the_chain_before_the_first_run(self):
        chain.stop_flag().touch()
        self._sweeps((0, "should never run"))
        self._pending(12)
        self.assertEqual(chain.main(), 0)
        self.assertEqual(self.runs, [], "the flag was there before run 1")

    def test_the_stop_flag_never_interrupts_a_running_sweep(self):
        """It only decides whether the NEXT run starts.

        The watermark is append-only, so a transcript cut off halfway marks
        itself swept and loses the rest of its content for good. The flag
        therefore lands between runs, never inside one.
        """
        def sweep_then_raise_the_flag():
            self.runs.append(len(self.runs) + 1)
            chain.stop_flag().touch()   # mid-run, the way a person would
            return 0, "memory-sweep: 3 verwerkt"
        self._patch("run_sweep", sweep_then_raise_the_flag)
        self._pending(12, 9, 9)
        self.assertEqual(chain.main(), 0)
        self.assertEqual(len(self.runs), 1,
                         "run 1 had to finish, run 2 was not allowed to start")

    # --- directory resolution --------------------------------------------

    def test_siblings_resolve_from_the_script_directory_not_the_vault(self):
        """Installed the two are one directory; in a checkout they are not.

        A vault-relative path would load the INSTALLED _sweepstate while
        running the checkout's chain, and that difference is exactly what a
        test running from a checkout should catch.
        """
        self.assertEqual(chain.SCRIPTS, SCRIPTS)
        self.assertNotEqual(chain.SCRIPTS, self.vault / ".claude" / "scripts")
        self.assertTrue((chain.SCRIPTS / "memory-sweep.py").is_file())


if __name__ == "__main__":
    unittest.main()
