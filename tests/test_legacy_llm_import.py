import subprocess
import sys


def test_default_agent_import_does_not_load_deprecated_planner():
    result = subprocess.run(
        [
            sys.executable,
            "-Werror::DeprecationWarning",
            "-c",
            "import src.core.agents; print('ok')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_explicit_legacy_import_remains_available_with_warning():
    result = subprocess.run(
        [
            sys.executable,
            "-Walways::DeprecationWarning",
            "-c",
            (
                "from src.core.agents.capabilities.llm import DeepSeekPlanner; "
                "print(DeepSeekPlanner.__name__)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "DeepSeekPlanner"
    assert "deprecated" in result.stderr.lower()
