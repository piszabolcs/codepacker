# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [1.0.0] - 2026-10-19

### Added
- PySide6 desktop app that packs a project folder into one upload-ready Markdown file (file tree plus every
  file in a fenced code block) or a base64-encoded zip TXT.
- Hard exclusion of secret files by name (`.env*`, keys, keystores, cloud credentials, Terraform state,
  secret folders) and by content (private-key blocks).
- Token redaction in the package (AWS, GitHub, Slack, Google, JWT, AI-provider API keys, secret-looking
  key/value pairs); the user's own files are never changed.
- Exclusion log and Excluded tab with the reason and rule for every skipped file or folder; junk folders,
  lock files, binaries, logs, links and the app's own output folder are left out.
- Size-based splitting of the Markdown output without cutting files, with stale parts removed.
- Ad-hoc packages from dropped or chosen files, "Copy as Markdown" with a token estimate.
- Encoding detection (UTF-8, UTF-16/32 with or without BOM, cp1250, latin-1).
- Command line `python -m codepacker` on the Qt-free core, with per-format result lines and exit codes.
- Settings in `%APPDATA%\CodePacker\settings.ini`, `--version`, About card, PyInstaller build to a single
  `CodePacker.exe`, offscreen pytest suite and Windows CI.
