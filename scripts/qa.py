"""人格质量一键检查：python scripts/qa.py

跑人格质量六项 + 人格/记忆/可靠性相关套件，退出码非 0 表示有问题。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUITES = [
    "tests/test_persona_quality.py",
    "tests/test_phase2.py",
    "tests/test_diary_belief.py",
    "tests/test_outbox.py",
    "tests/test_phase1.py",
]


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", *SUITES]
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
