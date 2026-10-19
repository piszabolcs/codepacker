"""Test-data generators and small shared helpers for the CodePacker test suite.

This is a helper module imported by the tests, not a test module. Every tree is written into a
temporary folder at test time and is never committed. The fake secrets are assembled at runtime,
so the repository itself never contains a literal private-key block or token that a secret
scanner would flag.
"""

import codecs
import contextlib
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TypeVar

# A file's content: text is written as UTF-8 (no newline translation), bytes are written verbatim.
Content = str | bytes
T = TypeVar("T")

# ------------------------------------------------------------------------------------------------
# Fake secret material (obviously fake, assembled at runtime)
# ------------------------------------------------------------------------------------------------

_DASHES = "-" * 5


def _pem(label: str) -> str:
    return (
        f"{_DASHES}BEGIN {label}{_DASHES}\n"
        "MIIEowIBAAKCAQEAFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE\n"
        f"{_DASHES}END {label}{_DASHES}\n"
    )


FAKE_RSA_PRIVATE_KEY = _pem("RSA PRIVATE KEY")
FAKE_PRIVATE_KEY = _pem("PRIVATE KEY")
FAKE_AWS_ACCESS_KEY_ID = "AKIA" + "IOSFODNN7EXAMPLE"  # the example key id from the AWS docs
FAKE_OPENAI_KEY = "sk-" + "a" * 48
FAKE_GITHUB_TOKEN = "ghp_" + "a" * 36

# ------------------------------------------------------------------------------------------------
# The hostile tree, grouped by what a correct scanner must do with each file
# (spec section 4.2, findings S-1 and S-2, plus the exclusion matrix)
# ------------------------------------------------------------------------------------------------

# Ordinary sources in several languages: always included.
SOURCE_FILES: dict[str, Content] = {
    "README.md": "# Demo project\n\nOrdinary sources next to files that must never be uploaded.\n",
    "main.py": (
        "from src.config import DEBUG\n\n\n"
        "def main():\n    print('hello', DEBUG)\n\n\n"
        "if __name__ == '__main__':\n    main()\n"
    ),
    "src/app.js": "export function greet(name) {\n  return 'hello ' + name;\n}\n",
    "src/components/Button.tsx": (
        "export function Button(props: { label: string }) {\n"
        "  return <button>{props.label}</button>;\n}\n"
    ),
    "src/utils/helpers.go": "package utils\n\nfunc Add(a, b int) int { return a + b }\n",
    "src/lib/lib.rs": "pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n",
    "web/index.html": '<!doctype html>\n<title>Demo</title>\n<script src="../src/app.js"></script>\n',
    "web/site.css": "body { font-family: sans-serif; }\n",
    "scripts/build.sh": "#!/bin/sh\nset -e\necho building\n",
    "Dockerfile": "FROM python:3.12-slim\nCOPY . /app\n",
}

# Inside junk folders that are never scanned.
JUNK_FILES: dict[str, Content] = {
    "node_modules/x/index.js": "module.exports = 42;\n",
    ".git/HEAD": "ref: refs/heads/main\n",
}

# Secrets recognizable by their name or path: always excluded.
SECRET_NAME_FILES: dict[str, Content] = {
    ".env": "DB_PASSWORD=fake-password\n",
    ".env.local": "API_TOKEN=fake-local-token\n",
    ".env.production": "DATABASE_URL=postgres://app:fake@db.example/prod\n",
    "config/.ENV": "UPPERCASE_ENV=fake\n",  # not next to ".env": names are case-insensitive on Windows
    ".envrc": "export AWS_PROFILE=fake\n",
    "my.env": "SECRET=fake\n",
    "prod.env": "SECRET=fake\n",
    "env.txt": "SECRET=fake\n",
    "secret.yaml": "token: fake\n",
    "secret.yml": "token: fake\n",
    "secret_notes.md": "# Notes\n\nThe bank PIN is 0000 (fake).\n",
    "secrets.json": '{"api_key": "fake"}\n',
    "client_secret_123.json": '{"installed": {"client_secret": "fake"}}\n',
    "credentials.json": '{"client_secret": "fake"}\n',
    "gcp-credentials.json": '{"type": "service_account", "private_key_id": "fake"}\n',
    "service-account.json": '{"type": "service_account", "private_key_id": "fake"}\n',
    "myproj-firebase-adminsdk-ab12c.json": '{"type": "service_account", "project_id": "fake"}\n',
    "passwords.yml": "admin: fake\n",
    "token.json": '{"refresh_token": "fake"}\n',
    "id_rsa": FAKE_RSA_PRIVATE_KEY,
    "id_rsa.bak": FAKE_RSA_PRIVATE_KEY,
    "id_ed25519_old.txt": FAKE_PRIVATE_KEY,
    "AuthKey_ABC123.p8": FAKE_PRIVATE_KEY,
    "server.pem": FAKE_PRIVATE_KEY,
    "cert.pfx": b"\x30\x82\x01\x00FAKE-PFX",
    "key.p12": b"\x30\x82\x01\x00FAKE-P12",
    "keystore.jks": b"\xfe\xed\xfe\xedFAKE-JKS",
    "putty.ppk": "PuTTY-User-Key-File-" + "3: ssh-rsa\nEncryption: none\n",
    "sub/dir/private.key": "fake key material\n",
    "terraform.tfstate": '{"version": 4, "outputs": {"db_password": {"value": "fake"}}}\n',
    "prod.tfvars": 'db_password = "fake"\n',
    ".docker/config.json": '{"auths": {"registry.example.com": {"auth": "ZmFrZTpmYWtl"}}}\n',
    "appsettings.Production.json": (
        '{"ConnectionStrings": {"Db": "Server=db;User Id=sa;Password=fake;"}}\n'
    ),
    "local.settings.json": (
        '{"Values": {"AzureWebJobsStorage": "DefaultEndpointsProtocol=https;AccountKey=fake"}}\n'
    ),
    ".npmrc": "//registry.npmjs.org/:_authToken=fake-npm-token\n",
    ".pypirc": "[pypi]\nusername = __token__\npassword = fake\n",
}
# The rule (codepacker.core.rules) that must exclude each of them.
SECRET_RULE_BY_FILE: dict[str, str] = {
    ".env": "secret.dotenv",
    ".env.local": "secret.dotenv",
    ".env.production": "secret.dotenv",
    "config/.ENV": "secret.dotenv",
    ".envrc": "secret.envrc",
    "my.env": "secret.dotenv",
    "prod.env": "secret.dotenv",
    "env.txt": "secret.dotenv",
    "secret.yaml": "secret.secret_in_name",
    "secret.yml": "secret.secret_in_name",
    "secret_notes.md": "secret.secret_in_name",
    "secrets.json": "secret.secret_in_name",
    "client_secret_123.json": "secret.client_secret",
    "credentials.json": "secret.credential_in_name",
    "gcp-credentials.json": "secret.credential_in_name",
    "service-account.json": "secret.service_account",
    "myproj-firebase-adminsdk-ab12c.json": "secret.firebase_adminsdk",
    "passwords.yml": "secret.password_in_name",
    "token.json": "secret.token_json",
    "id_rsa": "secret.ssh_key",
    "id_rsa.bak": "secret.ssh_key",
    "id_ed25519_old.txt": "secret.ssh_key",
    "AuthKey_ABC123.p8": "secret.private_key_file",
    "server.pem": "secret.private_key_file",
    "cert.pfx": "secret.keystore",
    "key.p12": "secret.keystore",
    "keystore.jks": "secret.keystore",
    "putty.ppk": "secret.private_key_file",
    "sub/dir/private.key": "secret.private_key_file",
    "terraform.tfstate": "secret.terraform_state",
    "prod.tfvars": "secret.terraform_vars",
    ".docker/config.json": "secret.docker_config",
    "appsettings.Production.json": "secret.appsettings",
    "local.settings.json": "secret.azure_local_settings",
    ".npmrc": "secret.login_config",
    ".pypirc": "secret.login_config",
}

# Innocent names, private-key content: excluded by a content scan, by this rule.
PRIVATE_KEY_CONTENT_FILES: dict[str, Content] = {
    "disguised_pem.txt": "Looks like notes.\n" + FAKE_RSA_PRIVATE_KEY,
    "private_key_renamed.cfg": FAKE_PRIVATE_KEY,
}
PRIVATE_KEY_CONTENT_RULE = "secret.private_key_content"

# Ordinary files with hard-coded tokens: included, with every token redacted.
TOKEN_FILES: dict[str, Content] = {
    "aws.txt": f"[default]\naws_access_key_id = {FAKE_AWS_ACCESS_KEY_ID}\nregion = eu-central-1\n",
    "src/config.py": (
        f'OPENAI_API_KEY = "{FAKE_OPENAI_KEY}"\n'
        f'GITHUB_TOKEN = "{FAKE_GITHUB_TOKEN}"\n'
        "DEBUG = True\n"
    ),
}
TOKENS_BY_FILE: dict[str, tuple[str, ...]] = {
    "aws.txt": (FAKE_AWS_ACCESS_KEY_ID,),
    "src/config.py": (FAKE_OPENAI_KEY, FAKE_GITHUB_TOKEN),
}
# In the bundle each token becomes "[REDACTED:<type>]" with this type.
TOKEN_TYPES: dict[str, str] = {
    FAKE_AWS_ACCESS_KEY_ID: "aws",
    FAKE_OPENAI_KEY: "openai",
    FAKE_GITHUB_TOKEN: "github",
}

# Public keys are not secrets: always included.
PUBLIC_KEY_FILES: dict[str, Content] = {
    "id_rsa.pub": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQFAKE user@example\n",
}

# Size, encoding and naming edge cases.
OVERSIZED_FILE = "generated/big_data.json"  # 350 kB, above the default 300 kB limit
EMPTY_FILE = "empty.py"
CP1250_FILE = "legacy/cp1250_hu.txt"
LATIN1_FILE = "legacy/latin1.py"
UTF16_FILE = "scripts/deploy_utf16.ps1"
UTF8_BOM_FILE = "src/Program.cs"
HUNGARIAN_NAME_FILE = "árvíztűrő tükörfúrógép.md"
LONG_PATH_FILE = "/".join(f"deep_{letter * 45}" for letter in "abcdef") + "/very_deep_file.py"


def _generated_data(size: int) -> str:
    """Deterministic ASCII text of exactly ``size`` bytes, shaped like a generated JSON file."""
    row = '  {"id": 0, "label": "generated"},\n'
    return ("[\n" + row * (size // len(row) + 1))[: size - 2] + "]\n"


EDGE_CASE_FILES: dict[str, Content] = {
    OVERSIZED_FILE: _generated_data(350 * 1024),
    EMPTY_FILE: b"",
    CP1250_FILE: "árvíztűrő tükörfúrógép ŐŰ\n".encode("cp1250"),
    LATIN1_FILE: "# café naïve\nprint('latin-1')\n".encode("latin-1"),
    UTF16_FILE: codecs.BOM_UTF16_LE + "Write-Host 'UTF-16 PowerShell'\r\n".encode("utf-16-le"),
    UTF8_BOM_FILE: codecs.BOM_UTF8 + (
        b"using System;\n\nclass Program\n{\n"
        b'    static void Main() => Console.WriteLine("BOM");\n}\n'
    ),
    HUNGARIAN_NAME_FILE: "# Árvíztűrő tükörfúrógép\n",
    LONG_PATH_FILE: "print('more than 260 characters deep')\n",
}

# Directory junctions (created only when possible; see hostile_tree).
LINK_OUTSIDE = "link_outside"  # points to a sibling folder outside the project
LOOP_TO_ROOT = "src/loop_to_root"  # points back to the project root
OUTSIDE_FILES: dict[str, Content] = {
    "outside_source.py": "print('I live outside the project')\n",
    "outside_notes.md": "# Outside notes\n",
}

BIG_TREE_FOLDERS = 60


# ------------------------------------------------------------------------------------------------
# Generators
# ------------------------------------------------------------------------------------------------


def long_path_safe(path: str | os.PathLike) -> str:
    """Return ``path`` as an absolute string that Windows accepts beyond 260 characters."""
    text = os.path.abspath(path)
    if sys.platform != "win32" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def write_tree(root: str | os.PathLike, files: Mapping[str, Content]) -> Path:
    """Write ``files`` ({"relative/path": content}) below ``root`` and return ``root`` as a Path.

    The bytes on disk are exactly the given content. Keys must be plain relative paths with
    forward slashes; anything that could escape ``root`` raises ValueError. Every key is checked
    before anything is written, and ``root`` is created even when ``files`` is empty.
    """
    root = Path(root)
    for relative in files:
        parts = relative.split("/")
        if "\\" in relative or ":" in relative or any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"expected a plain 'relative/path', got {relative!r}")
    os.makedirs(long_path_safe(root), exist_ok=True)
    for relative, content in files.items():
        target = long_path_safe(root.joinpath(*relative.split("/")))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(content.encode("utf-8") if isinstance(content, str) else content)
    return root


def hostile_files() -> dict[str, Content]:
    """Every regular file of the hostile tree: {"relative/path": content}."""
    return {
        **SOURCE_FILES,
        **JUNK_FILES,
        **SECRET_NAME_FILES,
        **PRIVATE_KEY_CONTENT_FILES,
        **TOKEN_FILES,
        **PUBLIC_KEY_FILES,
        **EDGE_CASE_FILES,
    }


def _make_junction(link: Path, target: Path) -> None:
    """Try to create a directory junction (no admin rights needed); never raise."""
    if sys.platform != "win32":
        return
    with contextlib.suppress(OSError):
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def hostile_tree(root: str | os.PathLike, *, junctions: bool = True) -> Path:
    """Write the hostile project tree below ``root`` and return ``root`` as a Path.

    With ``junctions=True`` it also tries to create ``LINK_OUTSIDE`` (pointing to a sibling folder
    ``<root>_outside`` that holds ``OUTSIDE_FILES``) and ``LOOP_TO_ROOT`` (pointing back to
    ``root``). If ``mklink /J`` fails, the tree is simply left without them; tests that need them
    check ``os.path.isjunction`` and skip.
    """
    root = write_tree(root, hostile_files())
    if junctions:
        outside = write_tree(root.parent / f"{root.name}_outside", OUTSIDE_FILES)
        _make_junction(root / LINK_OUTSIDE, outside)
        _make_junction(root.joinpath(*LOOP_TO_ROOT.split("/")), root)
    return root


def only(items: list[T], description: str) -> T:
    """Return the single item of ``items`` (e.g. the widgets a window lookup found); raise a
    LookupError that names what was looked for when there is none or more than one."""
    if len(items) != 1:
        raise LookupError(f"expected one {description} in the window, found {len(items)}")
    return items[0]


def big_tree(root: str | os.PathLike, n: int = 6000) -> Path:
    """Write ``n`` small Python files spread evenly over 60 folders below ``root``; return it."""
    files = {
        f"pkg{index % BIG_TREE_FOLDERS:02d}/module_{index:05d}.py": (
            f'"""Generated module {index}."""\n\n\ndef value_{index}():\n    return {index}\n'
        )
        for index in range(n)
    }
    return write_tree(root, files)
