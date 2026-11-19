import sys
from pathlib import Path

import pytest

from callprobe.agent_session import require_auditor

tomllib = pytest.importorskip("tomllib")

ROOT = Path(__file__).resolve().parents[1]


def _project(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]


def test_missing_auditor_names_the_agent_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "didyoureally", None)
    with pytest.raises(ValueError) as excinfo:
        require_auditor()
    message = str(excinfo.value)
    assert 'pip install "callprobe[agent]"' in message
    assert "pip install -e packages/didyoureally" in message


def test_agent_extra_accepts_the_bundled_didyoureally_version():
    extra = _project(ROOT / "pyproject.toml")["optional-dependencies"]["agent"]
    assert extra == ["didyoureally>=0.1,<0.2"]
    version = _project(ROOT / "packages" / "didyoureally" / "pyproject.toml")["version"]
    major, minor = (int(part) for part in version.split(".")[:2])
    assert (major, minor) == (0, 1)


def test_callprobe_wheel_does_not_require_didyoureally():
    dependencies = _project(ROOT / "pyproject.toml")["dependencies"]
    assert not any(dep.startswith("didyoureally") for dep in dependencies)
