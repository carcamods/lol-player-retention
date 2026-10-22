# Changelog

Notable changes, newest first. Each entry says what changed and why.

## [2026-10-22]

### Added
- Project foundation: `lolret` package with typed settings (secrets as `SecretStr`), the
  project logging format, and a CLI with `version` and `config` commands.
- Tooling: uv, ruff, mypy (strict), pytest, and pre-commit with gitleaks, large-file and
  notebook-output checks. The 2024 version leaked credentials and committed 40 MB CSVs;
  these hooks block both.
- CI on GitHub Actions: lint, types and tests on Python 3.12 (Colab) and 3.13, plus a
  full-history gitleaks scan.
- Docs: requirements, engineering standards, and ADRs 0001–0004 (fresh repo, static snapshot
  site, point-in-time labels, neural nets on Colab).
