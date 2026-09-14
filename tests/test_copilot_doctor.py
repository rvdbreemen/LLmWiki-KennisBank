"""doctor.sh Copilot section tests (TASK-26.9 AC#5).

Runs the real scripts/doctor.sh against a fixture vault + temp COPILOT_HOME and
asserts the Copilot checks report PASS / not-configured / FAIL correctly. Skips
where bash is unavailable. Hermetic: never touches the real ~/.copilot.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = REPO_ROOT / "scripts" / "doctor.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
# _find_bash and _posix live in _proc beside run_bounded: they describe the
# same bash, and tests/test_projection_doctor_shell.py imports them from here.
from _proc import (  # noqa: E402
    find_bash as _find_bash,
    posix_path as _posix,
    run_bounded,
)

#: Gemeten op een rustige machine: de hele doctor.sh tegen deze
#: fixture kost ~18 s. 120 s laat ruimte voor een trage of belaste
#: machine zonder dat een echte hang de suite gijzelt.
DOCTOR_TIMEOUT = 120


BASH = _find_bash()

# Scripts the Copilot doctor block invokes from the vault's .claude/scripts.
VAULT_SCRIPTS = (
    "_copilot.py", "kb-copilot-capture.py", "kb-mcp.py", "kb-activity.py",
    "build-activity-index.py", "_activity.py", "_frontmatter.py", "_vaultpath.py",
)


@unittest.skipIf(BASH is None, "bash not available")
class CopilotDoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kb-cdoctor-"))
        self.vault = self.tmp / "Kluis"
        (self.vault / ".claude" / "scripts").mkdir(parents=True)
        for name in VAULT_SCRIPTS:
            src = REPO_ROOT / "scripts" / name
            if src.is_file():
                shutil.copy2(src, self.vault / ".claude" / "scripts" / name)
        self.saved = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "COPILOT_HOME")}
        os.environ["HOME"] = str(self.tmp)
        os.environ["USERPROFILE"] = str(self.tmp)
        os.environ["COPILOT_HOME"] = str(self.tmp / ".copilot")

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_doctor(self):
        # run_bounded in plaats van subprocess.run: die laatste hield zijn
        # timeout niet. doctor.sh start 54 Python-processen, en een kleinkind
        # dat de stdout-PIJP erft houdt communicate() vast tot HET klaar is.
        # Gemeten gevolg: deze test liep 393 s op een budget van 120 en viel
        # daarna alsnog om. Zie tests/_proc.py voor het bewijs.
        env = {**os.environ, "KENNISBANK_VAULT": _posix(self.vault),
               "COPILOT_HOME": str(self.tmp / ".copilot")}
        r = run_bounded([BASH, "scripts/doctor.sh"], cwd=str(REPO_ROOT),
                        env=env, timeout=DOCTOR_TIMEOUT)
        self.assertFalse(
            r.timed_out,
            f"doctor.sh kwam niet binnen {DOCTOR_TIMEOUT}s klaar "
            f"({r.duur:.0f}s). Laatste uitvoer:" + os.linesep + r.output[-2000:])
        return r.output

    def _install_copilot(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_copilot", REPO_ROOT / "scripts" / "_copilot.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.install(self.vault)

    def _copilot_lines(self, out):
        return [l for l in out.splitlines() if "copilot" in l.lower() and "] copilot" in l.lower()]

    def test_not_configured_no_fail(self):
        out = self._run_doctor()
        self.assertIn("not configured", out)
        fails = [l for l in out.splitlines() if "[FAIL]" in l and "copilot" in l.lower()]
        self.assertEqual(fails, [], f"copilot must not FAIL when unconfigured: {fails}")

    def test_configured_pass(self):
        self._install_copilot()
        out = self._run_doctor()
        self.assertRegex(out, r"\[PASS\] copilot config")

    def test_broken_config_fails(self):
        self._install_copilot()
        # break it: remove the managed instructions file so validate_config fails.
        (self.tmp / ".copilot" / "copilot-instructions.md").unlink()
        out = self._run_doctor()
        self.assertRegex(out, r"\[FAIL\] copilot config")


if __name__ == "__main__":
    unittest.main()
