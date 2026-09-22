# GitHub issue comments: a real-API evaluation example

This example evaluates whether a model proposes the right next tool call for
three real GitHub REST operations:

- `GET /repos/{owner}/{repo}/issues/{issue_number}`
- `GET /repos/{owner}/{repo}/issues/{issue_number}/comments`
- `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

## Provenance and projection

`openapi.json` is **not** the full GitHub description. It is a small OpenAPI
3.0.3 request-contract projection made by `extract.py` from
[api.github.com.json at revision `338cb199baa4f326790b0b1c246d8d4f481a82a0`](https://raw.githubusercontent.com/github/rest-api-description/338cb199baa4f326790b0b1c246d8d4f481a82a0/descriptions/api.github.com/api.github.com.json)
(SHA256 `4fbdc7d0102276803a07f9880d14ed543ba1afc10a4c9fd7bd3782408d9abaf7`).

- Copied verbatim: `operationId`, `summary`, `description`, `parameters`,
  `requestBody`, and the local components those reference. No schema
  constraints were added, removed, or shortened.
- Replaced: responses are one placeholder each (200 for GET, 201 for POST);
  the scorer never reads them.
- Dropped: every other operation and component, tags, servers, security, and
  GitHub-specific metadata. A small `info` block was added and says so.
- `provenance.json` records the URL, revision, SHA256, and transform scope.
- The upstream MIT license is in `LICENSE.md`. This is not an official GitHub
  artifact.

To regenerate, download the pinned file, then run the script from the
repository root. The script refuses a file with a different SHA256. Network
access is needed only for the source download; the extractor itself is offline.

```bash
curl -fsSL -o /tmp/callprobe-github-upstream.json \
  https://raw.githubusercontent.com/github/rest-api-description/338cb199baa4f326790b0b1c246d8d4f481a82a0/descriptions/api.github.com/api.github.com.json
python3 examples/github-issues/extract.py /tmp/callprobe-github-upstream.json \
  examples/github-issues/openapi.json
```

## Execution boundary

Callprobe imports the argument contract and scores the model's proposed call.
It never sends requests to the GitHub API or needs GitHub credentials. Running
a model does contact your model endpoint (Ollama by default). The tests and
the extractor do no network I/O. The repository `octo-org/widget` and
all issue numbers and texts are fabricated.

## Run it

From the repository root with Callprobe 0.6.0 or newer installed:

```bash
callprobe init --from-openapi examples/github-issues/openapi.json --out github-issues-suite
cp examples/github-issues/tasks.yaml github-issues-suite/tasks.yaml
callprobe validate --suite github-issues-suite
callprobe run --suite github-issues-suite --model qwen2.5:7b \
  --pad 0 --repeats 1 --max-tokens 4096 --out github-issues-suite/qwen2.5-7b.json
callprobe run --suite github-issues-suite --model qwen3:8b \
  --pad 0 --repeats 1 --max-tokens 4096 --out github-issues-suite/qwen3-8b.json
callprobe compare github-issues-suite/qwen2.5-7b.json github-issues-suite/qwen3-8b.json
```

Ollama must be running with both models installed. Arguments are grouped
under `path`, `query`, and `body`; the imported tool names are the
`operationId` (with `/` replaced by `_`) plus a short hash of the method and
path, e.g. `issues_get_cf0062ad`.

## The 18 cases

5 select, 5 args, 5 abstain, and 3 depth cases cover: integer path values,
owner and repo parsed from a URL, page and per-page values, an exact
multi-line comment body and one with punctuation, corrections and references
to earlier turns, missing repository or issue data, an explicit instruction
not to post, unsupported close/delete requests, and choosing the wrong
operation.

## Limits

- Each case expects exactly one next call or none. Multi-step plans are not
  scored.
- The schema declares `page` and `per_page` as integers only (the "max 100"
  is in prose), so the pagination cases check values the user states, not
  schema-enforced bounds.
- 18 authored cases are not representative of real usage, and passing
  them says nothing about API business outcomes.

## Recorded comparison

The [recorded local evaluation](../../results/github-issues/README.md) scored
Qwen2.5 7B at 5/18 and Qwen3 8B at 11/18. Qwen3 improved eight cases but
regressed on two, so the strict regression gate failed. Both runs completed
without request errors or truncation. Inspect the case-level evidence before
treating the higher aggregate score as a reason to switch models.
