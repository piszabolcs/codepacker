"""The exclusion rule table (spec S-1, T-1): which names never go into a package, and why.

One test per behaviour; each case list keeps one name per distinct rule plus every name a review
finding or ruling added (marked).
"""

import os
import re

from codepacker.core import rules
from codepacker.core.rules import Exclusion
from fixtures import (
    EDGE_CASE_FILES,
    PRIVATE_KEY_CONTENT_FILES,
    PUBLIC_KEY_FILES,
    SECRET_NAME_FILES,
    SECRET_RULE_BY_FILE,
    SOURCE_FILES,
    TOKEN_FILES,
)

# Ruling R1: the broad name rules leave files with these source-code extensions to the content
# scanner (".d.ts" ends in ".ts"). Shell and batch scripts are not on the list (fix round 2).
RULED_SOURCE_CODE_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".cs", ".java", ".kt", ".scala", ".go",
    ".rs", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift", ".m", ".mm", ".vue",
    ".svelte", ".dart", ".lua", ".pl",
}
SCRIPT_EXTENSIONS = {".sh", ".ps1", ".bat", ".cmd"}

# Secret rules the hostile tree does not exercise, one name each, plus the regressions.
MORE_SECRET_NAMES = {
    "app.env.bak": "secret.dotenv",
    ".env.js": "secret.dotenv",              # review I1: every ".env" prefix, code or not
    ".env~": "secret.dotenv",                # review I1
    "id_ecdsa_work": "secret.ssh_key",
    "tools/id_rsa_reader.py": "secret.ssh_key",  # key rules stay unconditional (ruling R1)
    "secrets.sh": "secret.secret_in_name",   # scripts are judged by name (fix round 2)
    "set_client_secret.cmd": "secret.client_secret",
    "terraform.tfstate.backup": "secret.terraform_state",
    ".netrc": "secret.login_config",
    ".htpasswd": "secret.htpasswd",
    "vault.kdbx": "secret.password_database",
    "office.ovpn": "secret.vpn_profile",
    "backup.tar.gpg": "secret.pgp",
    ".git-credentials": "secret.credential_in_name",
    "appsettings.Staging.json": "secret.appsettings",
    "k8s/secrets/db.yaml": "secret.secret_folder",   # ruling R2: secret folders, any depth
    "credentials/__init__.py": "secret.secret_folder",
    "user/.config/gcloud/configurations/config_default": "secret.secret_folder",
}

# Names that look a bit like the secret ones and must stay packable, one per reason.
NOT_SECRET_NAMES = [
    "id_rsa.pub", "appsettings.json", "appsettings.Development.json", "docker/config.json",
    "environment.py", "envoy.yaml", "tokens/vocab.json", "my_secrets/notes.md",
    ".config/other/settings.json",
    # source files: the content scanner guards them, not their name (ruling R1)
    "codepacker/core/secret_scan.py", "migrations/env.py", "src/env.d.ts",
    "components/PasswordInput.tsx",
]

# The check that excluded secrets before the rule table, as an oracle (review I1), and the
# names it flagged that the rule table must still flag.
OLD_EXACT_NAMES = {
    ".env", "credentials.json", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "secrets.json",
    "secrets.yaml", "secrets.yml", ".npmrc", ".pypirc", "service-account.json",
    "firebase-adminsdk.json",
}
OLD_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".ppk", ".asc")
OLD_CHECK_CORPUS = [
    *OLD_EXACT_NAMES, ".env.example", ".ENV.LOCAL", ".env_prod.json", ".envlocal", "x.PEM",
    "y.Key", "pub.asc", "top-secret.yml", "Passwords.TXT", "old_password.json",
    "secret.json.txt", "README.md", "secret.py",
]


def old_is_secret_file(name):
    lower_name = name.lower()
    if lower_name in OLD_EXACT_NAMES or lower_name.startswith(".env"):
        return True
    if lower_name.endswith(OLD_SUFFIXES):
        return True
    return (("secret" in lower_name or "password" in lower_name)
            and lower_name.endswith((".json", ".txt", ".yml")))


# The brief writes the .env rule as a regular expression on the file name.
BRIEF_DOTENV_PATTERN = re.compile(r"(^|.*\.)env(\..*)?$|^env\.(txt|json|ya?ml)$")


def _rule_id(path):
    rule = rules.secret_rule_for(path)
    return None if rule is None else rule.id


def test_every_secret_name_is_matched_by_its_rule():
    assert set(SECRET_RULE_BY_FILE) == set(SECRET_NAME_FILES)
    for path, rule_id in {**SECRET_RULE_BY_FILE, **MORE_SECRET_NAMES}.items():
        rule = rules.match_file(path)
        assert (rule.id, rule.kind) == (rule_id, rules.SECRET), path
        assert rules.secret_rule_for(path) == rule, path


def test_nothing_the_old_secret_check_excluded_comes_back():
    flagged = [name for name in OLD_CHECK_CORPUS if old_is_secret_file(name)]
    assert len(flagged) > 20
    assert [name for name in flagged if rules.secret_rule_for(name) is None] == []


def test_ordinary_names_and_the_rest_of_the_hostile_tree_are_not_secret():
    others = {*SOURCE_FILES, *PUBLIC_KEY_FILES, *TOKEN_FILES, *PRIVATE_KEY_CONTENT_FILES,
              *EDGE_CASE_FILES}
    assert [path for path in [*NOT_SECRET_NAMES, *others] if _rule_id(path)] == []


def test_source_files_are_never_secret_by_name_but_scripts_are():
    assert set(rules.SOURCE_CODE_EXTENSIONS) == RULED_SOURCE_CODE_EXTENSIONS
    for extension in RULED_SOURCE_CODE_EXTENSIONS:
        for stem in ("secret_store", "passwords", "credentials", "env", "client_secret"):
            assert _rule_id(stem + extension) is None, stem + extension
    for extension in SCRIPT_EXTENSIONS:
        assert [_rule_id(stem + extension) for stem in ("secret_store", "passwords", "env")] == [
            "secret.secret_in_name", "secret.password_in_name", "secret.dotenv"]


def test_secret_names_match_in_any_letter_case_and_every_path_form_windows_accepts():
    # review I2: separators, trailing dots and spaces, and the long s are the same name
    forms = {
        ".ENV": "secret.dotenv", "Config/.Env.Local": "secret.dotenv",
        "APPSETTINGS.PRODUCTION.JSON": "secret.appsettings",
        "SECRETS/Notes.MD": "secret.secret_folder", "sub\\.npmrc": "secret.login_config",
        ".docker\\config.json": "secret.docker_config", "secret.yaml.": "secret.secret_in_name",
        ".npmrc ": "secret.login_config", "config. /.env . ": "secret.dotenv",
        "ſecret.yaml": "secret.secret_in_name", "secrets\\notes.md": "secret.secret_folder",
    }
    assert {path: _rule_id(path) for path in forms} == forms


def test_the_dotenv_rule_is_the_briefs_pattern_or_the_old_prefix_but_no_source_file():
    for name in [".env", "env", "env.txt", "env.py", "env.", "my.env", "a.env.b", ".envrc",
                 "envoy.yaml", "dev_env.txt", "vite-env.d.ts", "my.envy", ".env.js",
                 ".env-local", "env.d.ts", "env.sh"]:
        source_file = os.path.splitext(name)[1] in RULED_SOURCE_CODE_EXTENSIONS
        expected = ((bool(BRIEF_DOTENV_PATTERN.match(name)) and not source_file)
                    or (name.startswith(".env") and name != ".envrc"))
        assert (_rule_id(name) == "secret.dotenv") == expected, name


def test_folders_files_and_extensions_get_a_rule_of_their_own_kind():
    for folder, rule_id in [("web/Node_Modules", "junk_dir.node_modules"),
                            (".git", "junk_dir.git"), ("src/__pycache__", "junk_dir.__pycache__")]:
        assert (rules.match_dir(folder).id, rules.match_dir(folder).kind) == (rule_id, "junk_dir")
    assert [rules.match_dir(folder) for folder in ("src", "docs", ".github")] == [None] * 3
    for path, rule_id, kind in [("assets/logo.png", "binary.png", rules.BINARY),
                                ("tools/setup.EXE", "binary.exe", rules.BINARY),
                                ("api/poetry.lock", "lock.poetry.lock", rules.LOCK),
                                ("logs2/app.log.1", "log.file", rules.LOG)]:
        assert (rules.match_file(path).id, rules.match_file(path).kind) == (rule_id, kind), path
    assert [path for path in SOURCE_FILES if rules.match_file(path) is not None] == []


def test_a_rule_turns_a_path_into_an_exclusion_with_its_id_kind_and_reason():
    rule = rules.secret_rule_for("config/.env")
    assert rule.exclusion("config/.env") == Exclusion(
        "config/.env", "secret.dotenv", "secret", rule.reason)
    assert rule.reason != ""


def test_every_rule_has_a_known_kind_and_one_reason_per_id():
    table = [*rules.SECRET_RULES, *rules.JUNK_DIR_RULES, *rules.LOCK_RULES, *rules.BINARY_RULES,
             *rules.LOG_RULES, rules.NO_EXTENSION, rules.EMPTY_FILE, rules.TOO_LARGE,
             rules.BINARY_CONTENT, rules.PRIVATE_KEY_CONTENT, rules.LINK_RULE,
             rules.OUTSIDE_PROJECT, rules.SELF_OUTPUT_RULE, rules.UNREADABLE, rules.SECRET_FOLDER]
    kinds = {rules.SECRET, rules.JUNK_DIR, rules.BINARY, rules.LOCK, rules.SIZE, rules.USER,
             rules.LOG, rules.LINK, rules.SELF_OUTPUT, rules.ERROR}
    assert {rule.kind for rule in table} <= kinds
    meaning_by_id = {}
    for rule in table:
        assert rule.reason != ""
        meaning_by_id.setdefault(rule.id, set()).add((rule.kind, rule.reason))
    assert [rule_id for rule_id, meanings in meaning_by_id.items() if len(meanings) > 1] == []


def test_the_also_exclude_text_becomes_user_globs_not_substrings():
    # spec C-13: "test" used to drop legacy/latest.py and contest/
    user = rules.user_rules(" test , *.BAK ,, docs/** , tests/ ")
    assert [rule.kind for rule in user] == [rules.USER] * 4
    assert rules.match_file("legacy/latest.py", user) is None
    assert rules.match_dir("contest", user) is None
    assert rules.match_dir("src/Test", user) in user
    assert rules.match_file("notes/old.bak", user) in user
    assert rules.match_dir("docs", user) in user and rules.match_dir("api/docs", user) in user
    assert rules.match_dir("pkg/tests", user) in user
    assert rules.match_file("tests", user) is None
    assert rules.match_file("src/app.js", user) is None
    assert rules.user_rules("") == ()


def test_a_user_rule_cannot_turn_a_secret_into_an_ordinary_exclusion():
    assert rules.match_file(".env", rules.user_rules("env")).kind == rules.SECRET
