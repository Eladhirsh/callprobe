"""Reject a release tag that does not match project metadata (Python 3.11+).

RELEASE_TAG is the pushed tag. RELEASE_PROJECT optionally names the directory
holding pyproject.toml (default: the repository root). RELEASE_TAG_PREFIX sets
the expected prefix (default: "v"), for example "didyoureally-v".
"""
import os
from pathlib import Path
import tomllib


def check_tag(tag: str, version: str, prefix: str = "v") -> None:
    expected = f"{prefix}{version}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match expected {expected!r}")


def project_version(project_dir: Path) -> str:
    return tomllib.loads((project_dir / "pyproject.toml").read_text())["project"]["version"]


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    project_dir = root / os.environ.get("RELEASE_PROJECT", ".")
    version = project_version(project_dir)
    try:
        check_tag(os.environ.get("RELEASE_TAG", ""), version, os.environ.get("RELEASE_TAG_PREFIX", "v"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Release tag matches package version {version}")
