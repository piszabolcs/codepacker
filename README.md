<div align="center">

<img src="docs/assets/logo.png" alt="CodePacker logo" width="120" />

# CodePacker

**Pack a source folder into one upload-ready Markdown file for AI chats, minus the secrets**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.12-41CD52?style=flat-square&logo=qt&logoColor=white)
![Status](https://img.shields.io/badge/status-active-2EA44F?style=flat-square)
![License](https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square)

[Features](#features) · [Screenshots](#screenshots) · [Architecture](#architecture) · [Installation](#installation)

</div>

<p align="center">
  <img src="docs/screenshots/01-main.png" alt="CodePacker main window after scanning a demo project" width="900" />
</p>

## The problem

Many AI chats refuse zip uploads, so sharing a project means pasting it file by file. Copying a whole
folder by hand also drags along `.env` files, private keys, logs and `node_modules`, and a token buried
in a config file is easy to miss. Once it is in the chat, it is out of your hands.

## The solution

CodePacker walks the project, leaves out junk and secret files, replaces tokens it finds inside the
remaining files, and writes one Markdown file: the file tree plus every file in a fenced code block. As a
fallback it writes the project as a base64-encoded zip that a chat with a code sandbox can unpack. Every
file it leaves out is listed with its reason and rule, so nothing disappears silently, and your own files
are never changed.

## Features

- **Two output formats.** `<project>_combined.md` (recommended) and `<project>_zip.b64.txt` for chats with a code sandbox.
- **Secret files stay out.** `.env*`, SSH and TLS keys, keystores, cloud credentials, Terraform state and secret folders are a hard exclusion that cannot be checked back in.
- **Token redaction.** AWS, GitHub, Slack, Google, JWT and AI-provider API keys and secret-looking key/value pairs become `[REDACTED:<type>]` in the package.
- **Exclusions with reasons.** Every skipped file or folder appears in the log and the Excluded tab with its reason and the rule that matched.
- **Split by size.** The Markdown output can be split into parts under a size limit, never cutting a file in two.
- **Ad-hoc packages.** Drop a few files instead of a folder and get the same filtering, with paths relative to their common parent.
- **Copy as Markdown.** Puts the checked files on the clipboard and shows the size and a token estimate.
- **Command line.** `python -m codepacker` runs the Qt-free core for scripts and CI.

## Screenshots

<table>
  <tr>
    <td align="center" width="50%"><img src="docs/screenshots/02-excluded.png" alt="Excluded tab with reasons and rules" /><br/><sub>Every exclusion with its reason and rule</sub></td>
    <td align="center" width="50%"><img src="docs/screenshots/03-settings.png" alt="Settings panel unfolded" /><br/><sub>Formats, part size, size limit, exclude globs, output folder</sub></td>
  </tr>
  <tr>
    <td align="center" width="50%"><img src="docs/screenshots/04-build-result.png" alt="Build result dialog" /><br/><sub>Per-format build result</sub></td>
    <td align="center" width="50%"><img src="docs/screenshots/05-about.png" alt="About card" /><br/><sub>About card</sub></td>
  </tr>
</table>

The screenshots are generated offscreen from a synthetic demo project by `tools/make_demo.py`; the paths
they show are masked to `C:\demo`.

## Architecture

```mermaid
flowchart LR
    F[("Project folder")]
    subgraph UI["Interface"]
        W["Desktop window (PySide6)"]
        C["Command line"]
    end
    subgraph Workers["Workers"]
        T["Scan and build threads (QThread)"]
    end
    subgraph Core["Core (Qt-free)"]
        S["Scanner and exclusion rules"]
        X["Secret scan and redaction"]
        E["Encoding detection"]
        B["Bundle writer"]
    end
    subgraph Output["Output"]
        M["Markdown file(s)"]
        Z["base64 zip TXT"]
    end
    W --> T --> S
    C --> S
    F --> S --> X --> B
    E --> X
    B --> M
    B --> Z
```

`codepacker/core` holds all scanning, filtering, secret detection and bundle writing and never imports Qt,
so the command line runs without PySide6. The desktop window runs the same core in `QThread` workers, so
scans and builds can be cancelled and the window stays responsive. Files are read in their own encoding
(UTF-8, UTF-16/32 with or without BOM, cp1250, latin-1) before they reach the Markdown output.

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ (tested with 3.12) |
| Desktop UI | PySide6 (Qt 6) |
| Background work | `QThread` workers |
| Core | Python standard library only (`zipfile`, `base64`, `re`, `fnmatch`) |
| Packaging | PyInstaller, single `CodePacker.exe` |
| Tests and CI | pytest, pytest-qt (offscreen), pip-audit, GitHub Actions on Windows |

## Installation

Prerequisites: Windows 10 or 11 and Python 3.11 or newer (the secret-scanner patterns use atomic groups
and possessive quantifiers).

1. Clone the repository:
   ```powershell
   git clone https://github.com/piszabolcs/codepacker.git
   cd codepacker
   ```
2. Create the virtual environment and install the runtime dependency:
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
3. Start the app (or double-click `run.bat`, which uses `.venv` when it exists):
   ```powershell
   .venv\Scripts\python.exe main.py
   ```
4. Optional, build the standalone exe (installs the pinned tools from `requirements-dev.txt` into `.venv`):
   ```powershell
   build.bat
   ```
   The result is `dist\CodePacker.exe`; `CodePacker.exe --version` prints the version and exits.
5. Optional, run the tests (offscreen, no window appears):
   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   .venv\Scripts\python.exe -m pytest -q
   ```

## Usage

1. Drop a project folder on the window, or click "Browse folder…" and press Enter to scan.
2. Check the file list and the Excluded tab, adjust the checked files if needed.
3. Press "Build package" (Ctrl+B). Without an output folder the package goes to `<project>_codepacker`
   next to the project.

Command line:

```powershell
python -m codepacker <path...> [--md] [--b64] [--max-part SIZE] [--out DIR] [--exclude GLOB...] [--quiet]
```

One folder is a project; files or several paths make an ad-hoc package. `--max-part` takes sizes such as
`500k` or `2M`. The exit code is 0 on success and 1 on any failure or read error.

Notes:

- Settings live in `%APPDATA%\CodePacker\settings.ini`; the app writes no registry key of its own
  (Qt's file dialogs remember their last folder under `HKCU\Software\QtProject`). File > "Clear recent
  folders" forgets the recent-folder list.
- Nothing is sent anywhere. The log names files and token types, never file contents or secret values.
- Known limits: a secret in a source file that is neither a known token format nor a key/value pair is
  packed; unquoted values with spaces are not redacted; `*.pem` is excluded even when it holds only public
  certificates. Review the package before you upload it.

## Project structure

```text
codepacker/
├── codepacker/           # application package
│   ├── core/             # scanner, rules, secret scan, encoding, bundle writer (Qt-free)
│   ├── ui/               # PySide6 window, file tree, theme, About card
│   ├── workers.py        # QThread wrappers for scan and build
│   ├── settings.py       # INI settings in %APPDATA%
│   └── __main__.py       # command line
├── tests/                # pytest suite, runs offscreen
├── tools/                # make_demo.py: demo project and screenshots
├── assets/               # app icon
├── docs/                 # logo and screenshots
├── .github/workflows/    # CI: tests and pip-audit on Windows
├── main.py               # desktop entry point
├── run.bat, build.bat    # start from source, build the exe
└── codepacker.spec       # PyInstaller spec
```

## Roadmap

- [ ] Recognise more lock files (`uv.lock`, `bun.lockb`, `packages.lock.json`).
- [ ] Redact unquoted secret values that contain spaces.
- [ ] Let public certificate bundles (`*.pem` without a private key) through on request.
- [ ] Publish `CodePacker.exe` as a GitHub Release.

## License

Apache License 2.0, see [LICENSE](LICENSE). The standalone exe bundles third-party software: Qt for Python
and the Qt 6 libraries (LGPL-3.0) and the PyInstaller bootloader (GPL-2.0-or-later with the bootloader
exception); the notices are in [NOTICE](NOTICE).

---

<div align="center">
<sub>Built by Szabolcs Pintér · <a href="https://github.com/piszabolcs">GitHub</a> · <a href="https://www.linkedin.com/in/piszabolcs">LinkedIn</a></sub>
</div>
