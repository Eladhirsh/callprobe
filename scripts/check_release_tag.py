"""Reject a release tag that does not match project metadata (Python 3.11+)."""
import os
from pathlib import Path
import tomllib


def check_tag(tag: str, version: str) -> None:
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match expected {expected!r}")


if __name__ == "__main__":
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    version = tomllib.loads(project.read_text())["project"]["version"]
    try:
        check_tag(os.environ.get("RELEASE_TAG", ""), version)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Release tag matches package version {version}")
