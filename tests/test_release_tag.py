"""Release guard runs on Python 3.12; runtime still supports Python 3.10."""
import importlib.util
from pathlib import Path
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.version_info < (3, 11), reason="release job uses Python 3.12")


ROOT = Path(__file__).resolve().parents[1]


def _guard():
    spec = importlib.util.spec_from_file_location("check_release_tag", ROOT / "scripts/check_release_tag.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_tag_guard():
    module = _guard()
    module.check_tag("v0.9.0rc1", "0.9.0rc1")
    module.check_tag("v0.9.0", "0.9.0")
    for tag in ("", "0.9.0rc1", "v0.8.0", "v0.9.0", "v0.9.0rc1-extra"):
        with pytest.raises(ValueError, match="does not match expected"):
            module.check_tag(tag, "0.9.0rc1")


def test_didyoureally_release_tag_guard():
    module = _guard()
    version = module.project_version(ROOT / "packages" / "didyoureally")
    module.check_tag(f"didyoureally-v{version}", version, "didyoureally-v")
    for tag in (f"v{version}", version, f"didyoureally-{version}", "didyoureally-v9.9.9"):
        with pytest.raises(ValueError, match="does not match expected"):
            module.check_tag(tag, version, "didyoureally-v")


def test_release_tag_prefixes_do_not_overlap():
    root_trigger = (ROOT / ".github/workflows/release.yml").read_text()
    dyr_trigger = (ROOT / ".github/workflows/release-didyoureally.yml").read_text()
    assert '- "v*"' in root_trigger
    assert '- "didyoureally-v*"' in dyr_trigger
    assert not "didyoureally-v0.1.0".startswith("v")
