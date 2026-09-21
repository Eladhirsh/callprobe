#!/usr/bin/env python3
"""Project three GitHub REST operations out of the official OpenAPI document.

Offline only: reads a locally downloaded copy of the pinned upstream file,
verifies its SHA256, and writes a small OpenAPI 3.0.3 document plus a
provenance file. Nothing is fetched and no API operation is executed.

    python examples/github-issues/extract.py SOURCE.json examples/github-issues/openapi.json
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REVISION = "338cb199baa4f326790b0b1c246d8d4f481a82a0"
SOURCE_URL = (
    "https://raw.githubusercontent.com/github/rest-api-description/"
    f"{REVISION}/descriptions/api.github.com/api.github.com.json"
)
SOURCE_SHA256 = "4fbdc7d0102276803a07f9880d14ed543ba1afc10a4c9fd7bd3782408d9abaf7"

# (path, method) in output order.
OPERATIONS = (
    ("/repos/{owner}/{repo}/issues/{issue_number}", "get"),
    ("/repos/{owner}/{repo}/issues/{issue_number}/comments", "get"),
    ("/repos/{owner}/{repo}/issues/{issue_number}/comments", "post"),
)
# Only these operation members are copied. Everything else (tags, responses,
# x-github metadata, externalDocs, ...) is dropped.
KEPT_MEMBERS = ("summary", "description", "operationId", "parameters", "requestBody")
PLACEHOLDER_RESPONSES = {"get": "200", "post": "201"}

INFO_DESCRIPTION = (
    "A request-contract projection of three operations from GitHub's REST API "
    f"description at revision {REVISION} (MIT license, see LICENSE.md). "
    "Operation summaries, descriptions, operationIds, parameters, requestBody and "
    "the local components they reference are copied verbatim. Responses are "
    "placeholders, and all other operations, servers, security and metadata are "
    "omitted. Not an official GitHub artifact."
)


def _walk_refs(node: Any):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield ref
        for value in node.values():
            yield from _walk_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_refs(value)


def _resolve(document: dict, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"only local references are supported: {ref!r}")
    node: Any = document
    for raw in ref[2:].split("/"):
        node = node[raw.replace("~1", "/").replace("~0", "~")]
    return node


def project(document: dict) -> dict:
    """Return the projected document. Deterministic for a given input."""
    operations: dict[str, dict] = {}
    for path, method in OPERATIONS:
        source = document["paths"][path][method]
        operation = {k: copy.deepcopy(source[k]) for k in KEPT_MEMBERS if k in source}
        operation["responses"] = {
            PLACEHOLDER_RESPONSES[method]: {
                "description": "Projection placeholder; upstream responses are not part of this request contract."
            }
        }
        operations.setdefault(path, {})[method] = operation

    # Collect every component reachable from the copied request contracts.
    pending = list(_walk_refs(operations))
    found: dict[str, Any] = {}
    while pending:
        ref = pending.pop()
        if ref in found:
            continue
        found[ref] = copy.deepcopy(_resolve(document, ref))
        pending.extend(_walk_refs(found[ref]))

    components: dict[str, dict] = {}
    for ref in sorted(found):
        parts = ref[2:].split("/")
        if len(parts) != 3 or parts[0] != "components":
            raise ValueError(f"unexpected reference target: {ref}")
        components.setdefault(parts[1], {})[parts[2]] = found[ref]

    return {
        "openapi": document["openapi"],
        "info": {
            "title": "GitHub REST API issue comments (request-contract projection)",
            "version": f"upstream-{REVISION[:12]}",
            "description": INFO_DESCRIPTION,
        },
        "paths": operations,
        "components": components,
    }


def provenance(projected: dict) -> dict:
    return {
        "source_url": SOURCE_URL,
        "source_revision": REVISION,
        "source_sha256": SOURCE_SHA256,
        "license": "MIT (see LICENSE.md)",
        "operations": [f"{method.upper()} {path}" for path, method in OPERATIONS],
        "copied_components": {k: sorted(v) for k, v in projected["components"].items()},
        "transform_scope": (
            "Selected exactly three operations. Copied summary, description, operationId, "
            "parameters and requestBody verbatim, plus the local components they reach "
            "through $ref. Replaced responses with one placeholder each (200 for GET, 201 "
            "for POST). Dropped tags, servers, security, x-github metadata and every other "
            "operation and component. Added a small info block. No schema constraints "
            "were added, removed, or shortened."
        ),
    }


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def extract(source: Path, output: Path, provenance_path: Path | None = None,
            expected_sha256: str = SOURCE_SHA256) -> None:
    raw = Path(source).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise SystemExit(f"source SHA256 mismatch: expected {expected_sha256}, got {digest}")
    projected = project(json.loads(raw))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dump(projected), encoding="utf-8")
    target = Path(provenance_path) if provenance_path else output.with_name("provenance.json")
    target.write_text(dump(provenance(projected)), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="downloaded api.github.com.json at the pinned revision")
    parser.add_argument("output", type=Path, help="where to write the projected openapi.json")
    parser.add_argument("--provenance", type=Path, help="default: provenance.json beside the output")
    args = parser.parse_args(argv)
    extract(args.source, args.output, args.provenance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
