"""Release guard runs on Python 3.12; runtime still supports Python 3.10."""
import importlib.util
from pathlib import Path
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.version_info < (3, 11), reason="release job uses Python 3.12")


def test_release_tag_guard():
    spec = importlib.util.spec_from_file_location(
        "check_release_tag", Path(__file__).resolve().parents[1] / "scripts/check_release_tag.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check_tag("v0.9.0rc1", "0.9.0rc1")
    module.check_tag("v0.9.0", "0.9.0")
    for tag in ("", "0.9.0rc1", "v0.8.0", "v0.9.0", "v0.9.0rc1-extra"):
        with pytest.raises(ValueError, match="does not match expected"):
            module.check_tag(tag, "0.9.0rc1")
