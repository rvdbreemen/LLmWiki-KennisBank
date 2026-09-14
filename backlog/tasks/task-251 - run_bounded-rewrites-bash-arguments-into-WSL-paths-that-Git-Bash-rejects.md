---
id: TASK-251
title: run_bounded rewrites bash arguments into WSL paths that Git Bash rejects
status: Done
assignee: []
created_date: '2026-09-14 06:01'
updated_date: '2026-09-14 06:06'
labels: []
dependencies: []
ordinal: 188600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/_proc.py rewrites every argument of a bash command into the WSL filesystem namespace (/mnt/c/...). The bash this repo actually uses on Windows is MSYS2 (Git Bash), which reports OSTYPE=cygwin and expects /c/... or accepts a raw Windows path. Measured in a clean worktree off origin/main: raw Windows path rc=0, /c/ form rc=0, /mnt/c/ form rc=127 'No such file or directory'. Two tests in tests/test_proc_bounded.py fail on this.

Root cause is a duplicated converter. tests/test_copilot_doctor.py::_posix already produces the correct MSYS2 form and is imported by tests/test_projection_doctor_shell.py; _proc.py grew a second, divergent one. Its own comment says it exists for 'Git-for-Windows bash', so the intent was MSYS2 and the implementation is WSL.

Related: tests/test_proc_bounded.py resolves bash with shutil.which('bash'), bypassing _find_bash(), whose docstring states it deliberately rejects the WSL filesystem namespace.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 run_bounded passes argv through verbatim; it never rewrites arguments based on the name of the executable
- [ ] #2 Path translation for bash callers goes through one canonical helper, and a second implementation is treated as a defect
- [ ] #3 tests/test_proc_bounded.py resolves bash through the same helper as the other bash-invoking tests, so the WSL rejection applies there too
- [ ] #4 A falsifiable regression test asserts an argument containing a Windows drive-letter path reaches bash unchanged, and fails against the pre-fix code
- [ ] #5 The full suite is green in a clean worktree off origin/main, excluding untracked files from other sessions
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed. Root cause was a duplicated path converter, not an environment quirk: _proc.py grew a second one that emitted the WSL layout while the canonical _posix emitted MSYS2. Measured against C:/Program Files/Git/bin/bash.exe (OSTYPE=cygwin): raw Windows path rc=0, /c/ rc=0, /mnt/c/ rc=127.

run_bounded now passes argv through verbatim. find_bash and posix_path moved into tests/_proc.py beside it, so the one implementation sits next to the runner that needs it; test_copilot_doctor.py imports them under the old names, which keeps test_projection_doctor_shell.py's import working. test_proc_bounded.py now resolves bash through find_bash instead of shutil.which, so the deliberate WSL rejection applies there too.

Falsified: test_argumenten_bereiken_bash_ongewijzigd fails against the pre-fix rewrite and passes after. 20 bash-touching tests green (proc + copilot doctor + projection doctor shell). Baseline measured in a clean worktree off origin/main, where the third failure (test_integration_documentation) passes -- that one was an artefact of another session's uncommitted tree, not a real failure.
<!-- SECTION:NOTES:END -->
