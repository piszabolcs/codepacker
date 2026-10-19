"""The content scanner (spec S-2, T-2): private keys found by content, tokens redacted."""

import codecs
import importlib.util
import time
from pathlib import Path

from codepacker import core
from codepacker.core import secret_scan

DASHES = "-" * 5

# Fake tokens, assembled at runtime so that this file holds none a secret scanner would flag.
AWS_KEY = "AKIA" + "Q7" * 8
GITHUB_TOKEN = "gh" + "p_" + "B7" * 18
JWT = "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxMjM0In0" + ".c2lnbmF0dXJl_x-Y"
TOKEN_CASES = [  # one per pattern
    (AWS_KEY, "aws"),
    ("sk-" + "proj-" + "A1b2" * 10, "openai"),
    ("sk-" + "ant-api03-" + "x1Y" * 15, "anthropic"),
    (GITHUB_TOKEN, "github"),
    ("github" + "_pat_" + "11ABCDEFG" + "_c3" * 10, "github"),
    ("xo" + "xb-" + "123456789012-abcdefXYZ", "slack"),
    ("AI" + "za" + "SyD" + "x" * 32, "google"),
    (JWT, "jwt"),
]

# The value after a secret-looking key is redacted, the rest of the line stays readable; one
# line per form (ruling R3: JSON keys, bare KEY=value, name tails, brackets, annotations, ==,
# and fix round 2: punctuation in bare values, === != !==).
GENERIC_CASES = [
    ('password = "hunter2-hunter2"', 'password = "[REDACTED:generic]"'),
    ('{"password": "hunter2-hunter2"}', '{"password": "[REDACTED:generic]"}'),
    ("export DB_PASSWORD=hunter2-hunter2", "export DB_PASSWORD=[REDACTED:generic]"),
    ("https://api.test/v1?token=kZ2u9notarealkey&page=2",
     "https://api.test/v1?token=[REDACTED:generic]"),
    ("DB_PASSWORD=aB3$(xy)zQ9", "DB_PASSWORD=[REDACTED:generic]"),
    ("PASSWORD=hunter2-hunter2#a comment", "PASSWORD=[REDACTED:generic]#a comment"),
    ("Server=db;Password=hunter2-hunter2;Database=app",
     "Server=db;Password=[REDACTED:generic];Database=app"),
    ("cli --password=hunter2-hunter2 --verbose", "cli --password=[REDACTED:generic] --verbose"),
    ('SECRET_KEY = "django-insecure-k3y"', 'SECRET_KEY = "[REDACTED:generic]"'),
    ("app.config['SECRET_KEY'] = 'kZ2u9-not-a-real-key'",
     "app.config['SECRET_KEY'] = '[REDACTED:generic]'"),
    ('const password: string = "hunter2-hunter2";',
     'const password: string = "[REDACTED:generic]";'),
    ('if password == "hunter2-hunter2":', 'if password == "[REDACTED:generic]":'),
    ('if (password === "hunter2-hunter2")', 'if (password === "[REDACTED:generic]")'),
    ('if password != "hunter2-hunter2":', 'if password != "[REDACTED:generic]":'),
    ('secretAccessKey: "kZ2u9-not-a-real-key",', 'secretAccessKey: "[REDACTED:generic]",'),
    ('apiKey := "kZ2u9-not-a-real-key"', 'apiKey := "[REDACTED:generic]"'),
    ("'password' => 'hunter2-hunter2',", "'password' => '[REDACTED:generic]',"),
]

# Lines with a secret-looking key whose value is not a secret, one per reason.
NOT_A_SECRET_LINES = [
    "password: 'Password is required'",  # a text: a value with whitespace is never redacted
    'token: "Optional[str]" = None',  # a quoted type annotation, not a value
    "login(username=user, password=password)",  # keyword arguments pass variables
    "connect(\n    host=settings.DB_HOST,\n    password=settings.DB_PASSWORD,\n)",
    # markdown_it/rules_inline/strikethrough.py: the line before ends in a comment
    "Delimiter(\n    length=0,  # no length checks\n    # the token index\n"
    "    token=len(state.tokens) - 1,\n)",
    'url = f"https://api.test/v1?token={self.token}&page={page}"',  # a template, not a value
    # pip/_vendor/truststore/_api.py: the last keyword argument of a call split over lines
    "            certfile=certfile, keyfile=keyfile, password=password",
    'tokenizer = "bert-base-uncased"',  # a longer word, not a key name
    'password = request.form["password"]',
    "MAX_TOKENS = 4096",
]

# The generic rule's allow-list: values like these are never redacted.
PLACEHOLDER_LINES = [
    'api_key = "<your-key>"', 'password = "changeme"', 'token = "xxxxxxxxxxxxxxxx"',
    'secret = "example-secret-value"', 'API_KEY = "${OPENAI_API_KEY}"', "PASSWORD=$DB_PASSWORD",
    'password = "%DB_PASSWORD%"', 'secret = "{{ vault_secret }}"',
    'f\'OPENAI_API_KEY = "{FAKE_OPENAI_KEY}"\\n\'',  # an f-string field, e.g. tests/fixtures.py
    'password = "********"', 'token = "undefined"', 'api_key = "[REDACTED:generic]"',
    'token = None', 'password = ""', 'secret = "short"',
]

# Values the allow-list must not mistake for placeholders (review M5): a placeholder word only
# counts as a whole word, $NAME and %NAME% only in capitals, {{...}} only as the whole value.
NOT_PLACEHOLDERS = [
    "hunter2-hunter2", "Yourself2024!", "$uperSecret123", "%notAName",
    "{{a}}realsecretvalue{{b}}", "boxxxxer-2024", "counterexample1",
]

# pip's own sources: no file of it may be excluded for its content (spec T-2). Its CA bundle is
# excluded by name, by the *.pem rule: certificates only, but the brief keeps *.pem a hard rule.
PIP_SECRET_NAMES = {"_vendor/certifi/cacert.pem"}
# The known false-positive redactions in pip's sources, (path, type, line); a new one fails the
# guard until the rules are tightened or it is documented here.
PIP_KNOWN_REDACTIONS = []


def test_private_key_blocks_are_found_and_certificates_or_prose_are_not():
    for label in ["RSA PRIVATE KEY", "PRIVATE KEY", "OPENSSH PRIVATE KEY", "EC PRIVATE KEY",
                  "ENCRYPTED PRIVATE KEY", "PGP PRIVATE KEY BLOCK"]:
        assert secret_scan.has_private_key(f"notes\n{DASHES}BEGIN {label}{DASHES}\nMIIEow\n")
    for text in [f"{DASHES}BEGIN CERTIFICATE{DASHES}\n", f"{DASHES}BEGIN PUBLIC KEY{DASHES}\n",
                 f"{DASHES}BEGIN PGP PUBLIC KEY BLOCK{DASHES}\n",
                 "a key file starts with the BEGIN PRIVATE KEY line\n"]:
        assert not secret_scan.has_private_key(text), text


def test_one_content_check_serves_the_scanner_and_the_bundle():
    # review M7: the scanner and the bundle builder both call inspect(), so they always agree
    key = f"{DASHES}BEGIN PRIVATE KEY{DASHES}\nMIIEow\n"
    assert secret_scan.inspect(b"\x00\x01\x02 binary").rule.id == "binary.content"
    utf16_key = codecs.BOM_UTF16_LE + key.encode("utf-16-le")
    assert secret_scan.inspect(utf16_key).rule.id == "secret.private_key_content"
    assert secret_scan.inspect(key.encode("utf-8")).rule.id == "secret.private_key_content"

    plain = "print('hello')\n".encode("utf-8")
    assert secret_scan.inspect(plain) == (None, plain, [], "print('hello')\n", "utf-8")

    # a file that is not UTF-8 keeps its own codec in the zip
    legacy = f"# café\nkey = {AWS_KEY}\n".encode("cp1250")
    assert secret_scan.inspect(legacy) == (
        None, "# café\nkey = [REDACTED:aws]\n".encode("cp1250"), [("aws", 2)],
        "# café\nkey = [REDACTED:aws]\n", "cp1250")


def test_the_scanners_own_source_is_not_mistaken_for_a_private_key():
    # ruling R1 includes codepacker/core/secret_scan.py by name; its text must pass too
    assert not secret_scan.has_private_key(Path(secret_scan.__file__).read_text(encoding="utf-8"))


def test_each_kind_of_token_is_replaced_by_its_type():
    for token, token_type in TOKEN_CASES:
        text = f'value = "{token}"\nprint(value)\n'
        assert secret_scan.redact(text) == (
            f'value = "[REDACTED:{token_type}]"\nprint(value)\n', [(token_type, 1)]), token


def test_the_values_of_secret_looking_keys_are_redacted():
    for line, expected in GENERIC_CASES:
        assert secret_scan.redact(line + "\n") == (expected + "\n", [("generic", 1)]), line


def test_texts_types_variables_and_placeholders_after_a_key_are_left_alone():
    for line in [*NOT_A_SECRET_LINES, *PLACEHOLDER_LINES]:
        assert secret_scan.redact(line + "\n") == (line + "\n", []), line


def test_the_allow_list_holds_placeholders_but_no_real_looking_value():
    for value in ["<your-key>", "changeme", "xxxx", "example", "${VAR}", "None", "",
                  "$GITHUB_TOKEN", "%DB_PASSWORD%", "{api_key}", "{{vault_secret}}", "********",
                  "change_me_please", "your-api-key-here"]:
        assert secret_scan.is_placeholder(value), value
    assert [value for value in NOT_PLACEHOLDERS if secret_scan.is_placeholder(value)] == []


def test_long_runs_of_token_starts_are_scanned_in_linear_time():
    # review M6: a pattern that may start again at every "eyJ" (or key word) of a run made the
    # search quadratic; 300 kB, the default size limit, must take well under a second
    for text in ["eyJ" * 100_000, "password_" * 33_000, "password=" * 33_000,
                 "PasswordKey" * 27_000]:
        started = time.perf_counter()
        secret_scan.redact(text)
        assert time.perf_counter() - started < 2.0, text[:12]


def test_a_token_in_a_secret_assignment_is_redacted_once_under_its_own_type():
    token = "sk-" + "A1b2" * 12
    assert secret_scan.redact(f'OPENAI_API_KEY = "{token}"\n') == (
        'OPENAI_API_KEY = "[REDACTED:openai]"\n', [("openai", 1)])


def test_overlapping_matches_are_merged_so_no_part_of_a_token_survives():
    assert secret_scan.redact(f'secret = "prefix-{GITHUB_TOKEN}"\n') == (
        'secret = "[REDACTED:generic]"\n', [("generic", 1)])


def test_findings_give_the_line_of_each_token_and_never_its_value():
    text = f"first line\n\nkey = {AWS_KEY}\nother = '{GITHUB_TOKEN}' and {AWS_KEY}\n"
    redacted, findings = secret_scan.redact(text)
    assert findings == [("aws", 3), ("github", 4), ("aws", 4)]
    assert AWS_KEY not in redacted and GITHUB_TOKEN not in redacted
    assert AWS_KEY not in repr(findings) and GITHUB_TOKEN not in repr(findings)


def test_text_without_secrets_comes_back_unchanged():
    text = "# árvíztűrő\r\nprint('ok')\n\ttoken_count = 3\nkey = 'value'\n"
    assert secret_scan.redact(text) == (text, [])


def test_a_quoted_prompt_does_not_start_a_value_that_runs_into_the_next_lines():
    # pip/_internal/network/auth.py: an unbounded value would swallow the code after the prompt
    text = 'password = ask_password("Password: ")\n        return username, password, True\n'
    assert secret_scan.redact(text) == (text, [])


def test_sk_inside_a_word_is_not_an_openai_key():
    # pip/_vendor/packaging/licenses/_spdx.py
    text = "    'asterisk-linking-protocols-exception': {'id': 'Asterisk-linking-protocols'},\n"
    assert secret_scan.redact(text) == (text, [])


def test_the_pip_sources_raise_no_false_alarm():
    """False-positive guard: scanning pip's own sources (hundreds of ordinary files) excludes
    nothing for its content and redacts only the known values (each finding is printed)."""
    spec = importlib.util.find_spec("pip")
    assert spec is not None and spec.origin is not None, (
        "pip is not installed in this environment; the false-positive guard scans its sources")
    result = core.scan_project(str(Path(spec.origin).parent), 300, "")
    secret_exclusions = [e for e in result.excluded if e.kind == "secret"]
    for item in secret_exclusions + result.redactions:
        print("pip:", item)

    assert len(result.included) >= 400
    assert [e for e in secret_exclusions if e.rule_id == "secret.private_key_content"] == []
    assert {e.rel_path for e in secret_exclusions} <= PIP_SECRET_NAMES
    found = [(r.rel_path, r.token_type, r.line) for r in result.redactions]
    assert found == PIP_KNOWN_REDACTIONS
