---
id: TASK-248
title: Ship the sweep chain that drains a transcript backlog across runs
status: Done
assignee: []
created_date: '2026-09-10 15:46'
updated_date: '2026-09-14 06:22'
labels: []
dependencies: []
priority: medium
type: feature
ordinal: 187600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
One sweep run stops on its own budget and leaves the rest pending. That is deliberate -- the sweep shares a GPU with the embedding model serving the recall hot path -- but it means a backlog only disappears by repeating the run, and nothing in the repo does that. On 2026-09-09 a backlog of 97 transcripts had stood still for 35 hours.

A throwaway chain script drained it to zero in roughly thirteen hours with no errors, and the numbers it produced are the reason to keep it rather than the fact that it worked.

Cost structure, measured. Capture costs ~300 s per transcript. The maintenance tail after the loop (exact_duplicate, supersede, recheck, cluster_promote, groundcheck, focus) costs ~3300 s PER RUN and does not depend on how many transcripts the run handled. Cost per transcript is therefore 300 + 3300/N. Measured: 580 s at N=10, 277 s at N=40. The transcript cap is the knob, not the time budget -- raising KB_SWEEP_TIME_BUDGET alone changed nothing because --max bound first (processed 10 with budget_reached False).

Ceiling on N: _sweepstate.LEASE_MAX_SEC is 14400 s. A run that outlives its lease stops refreshing, and a second sweep can start beside it.

Three things the script needs that are not obvious:

1. A memory gate that samples more than once. Free physical memory on the development machine swung between 2.5 and 4.4 GB within four seconds with no sweep running, so a single reading is a coin flip rather than a gate; the first version blocked the chain at a false 1.7 GB while the median of three read 6.6 GB. Two sweep wrappers were killed for low memory that night at 0.7 GB free, with commit at 65.0 of 67.4 GB, so the gate itself is warranted.
2. A lock collision is a missed turn, not a failure. A session-start hook launches its own sweep; a run that reports 'overgeslagen' must wait and retry instead of counting toward the give-up threshold.
3. A stop flag that takes effect BETWEEN runs. Interrupting a sweep mid-transcript would mark it swept and lose the rest, because the watermark is append-only.

Current location is <vault>/.claude/sweep-ketting.py, a session artefact outside the repo. Upstreaming means scripts/, resolving its own directory instead of a vault-relative path, tests, and a line in the docs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The script lives in scripts/ and resolves its sibling modules from its own directory, not from a vault-relative path
- [x] #2 The transcript cap per run is a named constant whose comment carries the measured 300 + 3300/N cost and the LEASE_MAX_SEC ceiling
- [x] #3 The memory gate takes the median of several samples, and a test pins that a single low outlier does not block a run
- [x] #4 A run that could not take the lock waits and retries without counting toward the give-up threshold, covered by a test
- [x] #5 The stop flag ends the chain between runs and never interrupts a running sweep, covered by a test
- [x] #6 Manual invocation and the stop flag are documented where the other manual tools are
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Shipped as scripts/sweep-chain.py. Renamed from sweep-ketting.py and written in English: AGENTS.md states English by default, TASK-157 (translate the Dutch script layer) is still To Do, and a new file need not add to that debt. The rename is a deliberate, user-visible choice, not a side effect.

AC#1 SCRIPTS = Path(__file__).resolve().parent. setup.sh installs it through the existing scripts/*.py glob, so no installer change was needed. Test pins that SCRIPTS is the checkout's scripts/ and not the vault's .claude/scripts, which is the difference a vault-relative import would hide.
AC#2 MAX_PER_RUN carries 300 + 3300/N with the measured 580 s at N=10 and 277 s at N=40, why the time budget was the wrong knob (--max bound first), and the LEASE_MAX_SEC 14400 s ceiling.
AC#3 free_gb takes the median of MEMORY_SAMPLES readings. Tests: 0.7/6.6/6.6 does not block, 6.6/0.7/0.7 does, unmeasurable does not stop the chain.
AC#4 A run carrying SKIP_MARKER waits on lock_busy and continues without touching the empty counter. Test asserts the chain reaches MAX_RUNS AND consulted lock_busy once per missed turn, so it cannot pass by merely looping.
AC#5 The stop flag is read at the top of the loop. Two tests: flag present before run 1 means no sweep runs at all, and a flag raised mid-run lets that run finish while run 2 never starts.
AC#6 README section 'Draining a transcript backlog' with manual invocation, the stop flag, the between-runs guarantee and the cost model. The README has no table of contents, so nothing else needed updating.

Falsified, each against a mutated chain: counting a missed turn toward the threshold, removing the stop-flag check, and disabling SKIP_MARKER recognition each turn the matching test red. A seventh test pins SKIP_MARKER against the literal in memory-sweep.py, because that coupling crosses a subprocess and no import would break when the sentence is translated.

Not done here: the vault still holds the old .claude/sweep-ketting.py. After the next setup.sh both exist side by side and they write to different logs (sweep-ketting.log vs sweep-chain.log). Removing the old copy is the owner's call.
<!-- SECTION:NOTES:END -->
