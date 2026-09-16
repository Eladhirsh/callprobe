# Changelog

## 0.4.0

First public release.

- Package the default suite inside the wheel, so `pip install callprobe`
  works outside a git checkout. Previously the packaged CLI could not find
  `suites/core` at all.
- Add `callprobe validate [--suite PATH]`, which checks task expectations
  against tool schemas without needing a model.
- Add CI: pytest on Python 3.10 through 3.13, plus a wheel-install smoke
  test that would have caught the packaging bug above.
- Retry request errors (429, 5xx, connection and timeout errors) with
  exponential backoff and jitter instead of scoring them as model failures.
  Configurable with `--retries` (default 3). Reports honor `Retry-After`.
- Reports now exclude errored requests from every success/selection/schema
  /args rate, and warn when errors exceed 2% of requests. Error counts are
  still shown.
- Stop tracking log files and the overnight sweep log in git.
- Add `__version__` and `callprobe --version`.
- `--api-key` falls back to `API_KEY`, then `OPENAI_API_KEY`.
- Add PyPI packaging metadata (urls, keywords, classifiers, authors) and a
  trusted-publishing release workflow.
