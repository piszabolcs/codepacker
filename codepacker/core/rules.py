# -*- coding: utf-8 -*-
#
# the exclusion rules: which folders, files and extensions never go into a package, and why
# every rule is a row of data (id, kind, glob pattern, reason); the scanner (scanner.py) applies
# them and the bundle builder (bundle.py) checks the secret ones again; nothing here touches
# the disk
#
# matching is case-insensitive, with fnmatch-style globs: a pattern without "/" is checked
# against the file or folder name, a pattern with "/" against the project-relative path (at
# any depth); so "*secret*" never hides a whole folder, and ".docker/config.json" only
# matches that one file
#
# a path is matched in the form Windows resolves it to: "\" or "/" both separate the parts,
# trailing dots and spaces of a part don't count, and letter case doesn't either (casefold,
# so "ſecret.yaml" is "secret.yaml")

import fnmatch
import functools
import re
from dataclasses import dataclass

# the kinds of exclusion; "secret" is the hard one, such a file can never be put back
SECRET = "secret"
JUNK_DIR = "junk_dir"
BINARY = "binary"
LOCK = "lock"
SIZE = "size"
USER = "user"
LOG = "log"
LINK = "link"                   # a link, junction or anything else that leads out of the project
SELF_OUTPUT = "self_output"     # the app's own output folder inside the project
ERROR = "error"                 # the operating system refused to read it


@dataclass(frozen=True)
class Exclusion:
    # one file or folder that stays out of the package, and why
    rel_path: str       # project-relative, with "/" separators
    rule_id: str
    kind: str
    reason: str


@dataclass(frozen=True)
class ExclusionRule:
    id: str
    kind: str
    pattern: str        # an fnmatch glob (see the top of the file), "" for the rules the
                        # scanner applies itself by size or content
    reason: str         # shown to the user, never contains anything from the file itself
    unless: tuple = ()  # globs this rule leaves alone, e.g. "*.pub" for the ssh keys

    def exclusion(self, rel_path):
        return Exclusion(rel_path, self.id, self.kind, self.reason)

    def _matches(self, path, name):
        # path and name are already normalized, see normalized_path()
        if not _glob_matches(self.pattern, path, name):
            return False
        for exception in self.unless:
            if _glob_matches(exception, path, name):
                return False
        return True


def normalized_path(rel_path):
    # the path as Windows resolves it, in the one form the globs are matched against
    parts = rel_path.replace("\\", "/").split("/")
    return "/".join(part.rstrip(". ") for part in parts).casefold()


@functools.lru_cache(maxsize=None)
def _compiled(pattern):
    # (regex, whether it applies to the whole path) for one glob
    if "/" in pattern:
        # the glob may start at any folder of the path
        return re.compile("(?:.*/)?" + fnmatch.translate(pattern.casefold())), True
    return re.compile(fnmatch.translate(pattern.casefold())), False


def _glob_matches(pattern, path, name):
    regex, on_path = _compiled(pattern)
    return regex.match(path if on_path else name) is not None


def _family(rule_id, kind, patterns, reason, unless=()):
    # several patterns that mean the same thing: one rule each, sharing the id and the reason
    return tuple(ExclusionRule(rule_id, kind, pattern, reason, tuple(unless))
                 for pattern in patterns)


# ============================================================
# SECRETS, NEVER INCLUDED AND CANNOT BE PUT BACK
# ============================================================

# the broad name rules leave source files alone: a file with one of these extensions is code,
# and the content scanner (secret_scan.py) guards code; the key and certificate rules, the
# names that start with ".env" and the secret folders apply whatever the extension
# shell and batch scripts (.sh .ps1 .bat .cmd) are not on the list: they often are where the
# secrets themselves live, so secrets.sh or passwords.ps1 stay out by their name
SOURCE_CODE_EXTENSIONS = [
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".cs", ".java", ".kt", ".scala",
    ".go", ".rs", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".m", ".mm",
    ".vue", ".svelte", ".dart", ".lua", ".pl",
]   # ".d.ts" ends in ".ts"
SOURCE_CODE = tuple("*" + extension for extension in SOURCE_CODE_EXTENSIONS)

# the folders that hold secrets: every file below one of them stays out
SECRET_FOLDERS = [
    "secrets", ".secrets", "credentials", ".ssh", ".aws", ".gnupg", ".kube", ".azure",
    ".config/gcloud",
]

DOTENV_REASON = "environment file (.env), holds secrets"

# the first matching rule wins, so the specific ones come before the broad name rules at the end
SECRET_RULES = (
    *_family("secret.envrc", SECRET, [".envrc"], "direnv environment file"),
    # every name that starts with ".env"; then "env" as a dot-separated part of any other
    # name, the regex (^|.*\.)env(\..*)?$ as globs: prod.env, env.txt, app.env.bak, ...
    *_family("secret.dotenv", SECRET, [".env*"], DOTENV_REASON),
    *_family("secret.dotenv", SECRET, ["env", "env.*", "*.env", "*.env.*"], DOTENV_REASON,
             unless=SOURCE_CODE),
    *_family("secret.ssh_key", SECRET, ["id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*"],
             "SSH private key", unless=["*.pub"]),
    *_family("secret.private_key_file", SECRET, ["*.pem", "*.key", "*.p8", "*.ppk"],
             "private key or certificate file"),
    *_family("secret.keystore", SECRET, ["*.p12", "*.pfx", "*.jks", "*.keystore"],
             "certificate keystore"),
    *_family("secret.pgp", SECRET, ["*.asc", "*.gpg"], "PGP key or encrypted file"),
    *_family("secret.password_database", SECRET, ["*.kdbx"], "password database"),
    *_family("secret.vpn_profile", SECRET, ["*.ovpn"], "VPN profile, may embed keys"),
    *_family("secret.htpasswd", SECRET, [".htpasswd"], "web server password file"),
    *_family("secret.login_config", SECRET, [".npmrc", ".pypirc", ".netrc"],
             "package registry or login credentials"),
    *_family("secret.docker_config", SECRET, [".docker/config.json"],
             "Docker registry credentials"),
    *_family("secret.terraform_state", SECRET, ["*.tfstate*"],
             "Terraform state, holds secrets in plain text"),
    *_family("secret.terraform_vars", SECRET, ["*.tfvars"],
             "Terraform variables, often hold secrets"),
    *_family("secret.appsettings", SECRET, ["appsettings.*.json"],
             ".NET environment settings, hold connection strings",
             unless=["appsettings.json", "appsettings.development.json"]),
    *_family("secret.azure_local_settings", SECRET, ["local.settings.json"],
             "Azure Functions local settings, hold connection strings"),
    *_family("secret.client_secret", SECRET, ["*client_secret*"], "OAuth client secret",
             unless=SOURCE_CODE),
    *_family("secret.service_account", SECRET, ["*service-account*", "*service_account*"],
             "cloud service-account key", unless=SOURCE_CODE),
    *_family("secret.firebase_adminsdk", SECRET, ["*firebase-adminsdk*"],
             "Firebase Admin SDK key", unless=SOURCE_CODE),
    *_family("secret.credential_in_name", SECRET, ["*credential*"],
             "the name says it holds credentials", unless=SOURCE_CODE),
    *_family("secret.secret_in_name", SECRET, ["*secret*"], "the name says it holds secrets",
             unless=SOURCE_CODE),
    *_family("secret.password_in_name", SECRET, ["*password*"],
             "the name says it holds passwords", unless=SOURCE_CODE),
    *_family("secret.token_json", SECRET, ["*token*.json"], "token file"),
    *_family("secret.secret_folder", SECRET, [folder + "/*" for folder in SECRET_FOLDERS],
             "inside a folder that holds secrets"),
)


# ============================================================
# BASE RULES, WHAT WE NEVER INCLUDE
# ============================================================

# we don't even enter these folders, they only contain junk
SKIP_DIRS = [
    "node_modules", ".git", ".svn", ".hg", "__pycache__", ".venv", "venv",
    "env", "dist", "build", "out", ".next", ".nuxt", "target", "bin", "obj",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "coverage", ".cache", "logs", "tmp", "temp", ".gradle", "vendor",
    "release", "installer", ".turbo", "site-packages", ".parcel-cache",
    "electron-builder-output", "app-builds", ".eggs", "htmlcov",
    ".tox", ".nox", "bower_components", "jspm_packages", ".sass-cache",
]

# these extensions are binary or simply not useful
SKIP_EXT = [
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".db", ".sqlite",
    ".sqlite3", ".zip", ".rar", ".7z", ".gz", ".bz2", ".xz", ".tar",
    ".jar", ".war", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
    ".webp", ".tif", ".tiff", ".svg", ".mp4", ".mov", ".avi", ".mkv",
    ".webm", ".mp3", ".wav", ".flac", ".ogg", ".pdf", ".psd", ".ai",
    ".raw", ".cr2", ".nef", ".arw", ".dng", ".pyc", ".pyo", ".pyd",
    ".class", ".o", ".obj", ".lib", ".pdb", ".ttf", ".otf", ".woff",
    ".woff2", ".eot", ".map", ".msi", ".node", ".wasm", ".blend",
    ".xlsx", ".docx", ".pptx", ".onnx", ".pt", ".pth", ".safetensors",
    ".gguf", ".ckpt", ".h5", ".pkl", ".npy", ".npz",
]

# we never include these file names, they're just long and say nothing
SKIP_FILES = [
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
    "Cargo.lock", "composer.lock", "go.sum", "Gemfile.lock", ".DS_Store",
    "Thumbs.db", "desktop.ini", "npm-debug.log", "yarn-error.log",
]

# the same lists as rules
JUNK_DIR_RULES = (
    # only ".git" itself: ".github" holds workflows worth sharing (spec C-8)
    ExclusionRule("junk_dir.git", JUNK_DIR, ".git", "version control folder"),
    *(ExclusionRule("junk_dir." + name.lstrip("."), JUNK_DIR, name,
                    "dependency, build or cache folder")
      for name in SKIP_DIRS if name != ".git"),
)
LOCK_RULES = tuple(
    ExclusionRule("lock." + name.lstrip(".").lower(), LOCK, name,
                  "lock file or tool-generated file")
    for name in SKIP_FILES
)
BINARY_RULES = tuple(
    ExclusionRule("binary." + extension[1:], BINARY, "*" + extension, "binary or media file")
    for extension in SKIP_EXT
)
# log files often hold tokens, e-mail addresses and internal URLs (spec S-5)
LOG_RULES = _family("log.file", LOG, ["*.log", "*.log.*"], "log file, may hold tokens")

# for files the secrets come first: their reason is the one that matters most
FILE_RULES = SECRET_RULES + LOCK_RULES + BINARY_RULES + LOG_RULES

# rules the scanner applies itself, by extension, size or content rather than by a glob
NO_EXTENSION = ExclusionRule("binary.no_extension", BINARY, "",
                             "no extension and not a known text file name")
EMPTY_FILE = ExclusionRule("size.empty", SIZE, "", "empty file")
TOO_LARGE = ExclusionRule("size.too_large", SIZE, "", "larger than the size limit")
BINARY_CONTENT = ExclusionRule("binary.content", BINARY, "", "binary content")
PRIVATE_KEY_CONTENT = ExclusionRule("secret.private_key_content", SECRET, "",
                                    "private key material")
LINK_RULE = ExclusionRule("link.not_followed", LINK, "", "link or junction, not followed")
OUTSIDE_PROJECT = ExclusionRule("link.outside_project", LINK, "",
                                "really lies outside the project folder")
SELF_OUTPUT_RULE = ExclusionRule("self_output.folder", SELF_OUTPUT, "",
                                 "the output folder of this app")
UNREADABLE = ExclusionRule("error.unreadable", ERROR, "",
                           "the operating system refused to read it")
SECRET_FOLDER_ID = "secret.secret_folder"
SECRET_FOLDER = ExclusionRule(SECRET_FOLDER_ID, SECRET, "", "inside a folder that holds secrets")

# we include these file names even without an extension
EXTENSIONLESS_NAME_PREFIXES = [
    "dockerfile", "makefile", "procfile", "rakefile", "gemfile",
    "license", "readme", "changelog", "authors", "contributing",
    ".gitignore", ".dockerignore", ".editorconfig", ".gitattributes",
    ".eslintrc", ".prettierrc", ".babelrc",
]


# ============================================================
# MATCHING
# ============================================================


def _first_match(rel_path, rule_lists):
    path = normalized_path(rel_path)
    name = path.rsplit("/", 1)[-1]
    for rule_list in rule_lists:
        for rule in rule_list:
            if rule._matches(path, name):
                return rule
    return None


def match_dir(rel_path, extra_rules=()):
    # the rule that keeps this folder out, or None; a path glob such as "docs/**" keeps the
    # folder out as a whole (it is checked as "docs/")
    rule = _first_match(rel_path, (JUNK_DIR_RULES, extra_rules))
    if rule is None:
        path = normalized_path(rel_path) + "/"
        rule = next((user for user in extra_rules
                     if "/" in user.pattern and user._matches(path, "")), None)
    return rule


def match_file(rel_path, extra_rules=()):
    # the rule that keeps this file out by its name, or None
    return _first_match(rel_path, (FILE_RULES, extra_rules))


def secret_rule_for(rel_path):
    # the secret rule this file's name falls under, or None
    return _first_match(rel_path, (SECRET_RULES,))


def secret_folder_of(rel_path):
    # the folder of SECRET_FOLDERS this file lies in ("k8s/secrets"), or None
    parts = rel_path.replace("\\", "/").split("/")[:-1]
    normalized = normalized_path("/".join(parts)).split("/")
    for end in range(1, len(parts) + 1):
        tail = "/".join(normalized[:end])
        if any(tail == folder or tail.endswith("/" + folder) for folder in SECRET_FOLDERS):
            return "/".join(parts[:end])
    return None


def user_rules(raw_text):
    # the "Also exclude" field: comma-separated globs, case-insensitive like the built-in rules
    # (spec C-13): "*.log" or "teszt" match a file or folder name, "docs/**" the relative path
    # at any depth, "tests/" a folder; a folder that matches is not entered at all
    found = []
    for piece in raw_text.split(","):
        cleaned = piece.strip().replace("\\", "/")
        if cleaned == "":
            continue
        pattern = cleaned[3:] if cleaned.startswith("**/") else cleaned
        if pattern.endswith("/"):
            pattern = pattern + "**"
        found.append(ExclusionRule("user." + cleaned.casefold(), USER, pattern,
                                   "matches your exclude pattern"))
    return tuple(found)


def is_known_extensionless(name):
    # a file without an extension is only included if we recognize its name
    lower_name = name.lower()
    for prefix in EXTENSIONLESS_NAME_PREFIXES:
        if lower_name.startswith(prefix):
            return True
    return False
