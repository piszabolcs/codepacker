# -*- coding: utf-8 -*-
#
# the content scanner: looks inside the files that passed the name rules (rules.py); the
# scanner (scanner.py) and the bundle builder (bundle.py) both run inspect(), so they agree
#
#   binary content         -> the file stays out, it can't be checked for secrets
#                             (encoding.py decides what is text, and in which codec)
#   a private key block    -> the whole file stays out
#   a token or a password  -> only the value is replaced by "[REDACTED:<type>]" in the
#                             package, the user's own file is never touched
#
# what it reports is the type and the line of each finding, never the secret value itself

import re
from dataclasses import dataclass
from typing import NamedTuple

from . import encoding, rules

# the first line of a private key: five dashes, "BEGIN <kind> PRIVATE KEY", five dashes, where
# the kind is RSA, OPENSSH, EC, ENCRYPTED, nothing, ... ("PGP" also ends in " BLOCK"); this
# comment doesn't spell such a line out, or the scanner would exclude its own source
PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY( BLOCK)?-----")

# the token formats, each with the type its replacement shows
# "sk-" and "eyJ" must not continue a word: "asterisk-linking-..." is not an OpenAI key, and
# a run like "eyJeyJeyJ..." would otherwise restart the JWT search at every "eyJ" (quadratic)
WORD_START = r"(?<![A-Za-z0-9_-])"
TOKEN_PATTERNS = (
    ("aws", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("anthropic", re.compile(WORD_START + r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai", re.compile(WORD_START + r"sk-[A-Za-z0-9_-]{20,}")),
    ("github", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("github", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("slack", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("google", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("jwt", re.compile(WORD_START + r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
)

# the generic rule: the value after a secret-looking key; only the value is replaced, so the
# code stays readable. A value is at least 8 characters long and holds no whitespace, so a
# text like "Password is required" is not a secret.
#
# the key: a key word with an optional name tail (SECRET_KEY, api_key_v2, secretAccessKey);
# the tail is bounded, so a long run of key words can't make the search quadratic
KEY_NAME = (r"(?:api[_-]?key|secret|password|token)"
            r"(?>(?:[_-][a-z0-9]{1,40}|(?-i:[A-Z][a-z0-9]{1,40})){0,6})")
# a quoted value: the key may itself be quoted or bracketed ("password": or ['SECRET_KEY'] =)
# and have a type annotation (password: str =); = : := => assign, == === != !== compare; a
# quoted value followed by "=" is a type, not a value (token: "Optional[str]" = None)
GENERIC_QUOTED = re.compile(
    KEY_NAME + r"""["']?\]?\s*"""
    r"""(?::\s*[a-z_][\w.\[\],| ]{0,80}=|===|!==|!=|=>|:=|==|[:=])\s*"""
    r"""(?:"(?P<double>[^"\s]{8,2048})"|'(?P<single>[^'\s]{8,2048})')(?!\s*=)""",
    re.IGNORECASE)
# an unquoted value, written KEY=value as in .env files, shells and URLs; it may hold any
# punctuation and ends at whitespace, a quote, "#" (a comment) or ";" (the next setting).
# Not a value: a keyword argument (see is_keyword_argument), a variable named after a key
# word (password=password, token=access_token, see VARIABLE_NAME) or a template that starts
# with a placeholder (see redact)
GENERIC_BARE = re.compile(
    KEY_NAME + r"""=(?![=>])(?P<bare>[^\s'"#;]{8,256}+)(?![^\s'"#;])""",
    re.IGNORECASE)
VARIABLE_NAME = re.compile(r"(?=[a-z_])\w*(?:api_?key|secret|password|token)\w*",
                           re.IGNORECASE | re.ASCII)
GENERIC = "generic"

# the generic rule's allow-list: values that are obviously not a real secret
PLACEHOLDER_VALUES = ("", "none", "null")   # the whole value, in any letter case
PLACEHOLDER_FORMS = re.compile(             # the whole value, as written
    r"<[^<>]*>"                 # <your-key>
    r"|\$\{[^{}]*\}"            # ${API_KEY}
    r"|\$[A-Z_][A-Z0-9_]*"      # $API_KEY
    r"|%[A-Z_][A-Z0-9_]*%"      # %API_KEY%
    r"|\{[^{}]*\}"              # {api_key}, a format or f-string field
    r"|\{\{[^{}]*\}\}"          # {{api_key}}
)
PLACEHOLDER_WORDS = re.compile(             # a whole word of the value, in any letter case
    r"(?<![a-z0-9])(?:changeme|change[_-]me|x{4,}|\*{4,}|example|sample|placeholder|your"
    r"|dummy|redacted|undefined)(?![a-z0-9])")


@dataclass(frozen=True)
class Redaction:
    # one token replaced in the package; deliberately without the value
    rel_path: str
    token_type: str
    line: int           # 1-based


@dataclass(frozen=True)
class SecretSummary:
    files_excluded: int     # files kept out by a secret rule, by name or by content
    tokens_redacted: int


class Inspection(NamedTuple):
    rule: object        # the rules.ExclusionRule that keeps the file out, or None
    data: bytes         # what the zip gets: the file with every token replaced (or None)
    findings: list      # [(type, line), ...] of the replaced tokens
    text: str = None    # what the MD gets: the same as text, without a byte-order mark
    codec: str = None   # the codec the file is written in, see encoding.py


def inspect(raw):
    # the one content check of a file, run by the scanner and again by the bundle builder:
    # binary content can't be checked for secrets, a private key keeps the file out, and every
    # token is replaced in what the package gets (the zip keeps the file's own codec)
    decoded = encoding.decode(raw)
    if decoded is None:
        return Inspection(rules.BINARY_CONTENT, None, [])
    codec, text, mark = decoded
    if has_private_key(text):
        return Inspection(rules.PRIVATE_KEY_CONTENT, None, [])

    redacted, findings = redact(text)
    if len(findings) == 0:
        return Inspection(None, raw, [], text, codec)
    return Inspection(None, mark + redacted.encode(codec), findings, redacted, codec)


def has_private_key(text):
    return PRIVATE_KEY_BLOCK.search(text) is not None


def is_keyword_argument(text, position):
    # whether the KEY=value whose key word starts at position is a keyword argument of a call,
    # f(x, password=...) or one per line after "(" or ",": the name before "=" (DB_PASSWORD,
    # --password, spring.datasource.password) follows a "(" or a "," over any whitespace and
    # over "# comments" at the ends of the lines before
    while position > 0 and (text[position - 1].isalnum() or text[position - 1] in "_.-"):
        position = position - 1
    while position > 0:
        character = text[position - 1]
        if character == "\n":
            line_start = text.rfind("\n", 0, position - 1) + 1
            comment = text.find("#", line_start, position - 1)
            position = comment if comment != -1 else position - 1
        elif character.isspace():
            position = position - 1
        else:
            break
    return position > 0 and text[position - 1] in "(,"


def is_placeholder(value):
    cleaned = value.strip()
    if cleaned.casefold() in PLACEHOLDER_VALUES or PLACEHOLDER_FORMS.fullmatch(cleaned):
        return True
    return PLACEHOLDER_WORDS.search(cleaned.casefold()) is not None


def redact(text):
    # replace every token in the text; returns (new text, [(type, line), ...])
    # a text without findings comes back as the very same string
    candidates = []
    for priority, (token_type, pattern) in enumerate(TOKEN_PATTERNS):
        for match in pattern.finditer(text):
            candidates.append((match.start(), -match.end(), priority, token_type))
    for pattern in (GENERIC_QUOTED, GENERIC_BARE):
        for match in pattern.finditer(text):
            group = match.lastgroup     # the one value group that matched
            value = match.group(group)
            if is_placeholder(value):
                continue
            # a bare value is no secret when it is a variable, a keyword argument or a template
            # that starts with a placeholder (token={token}&page={page})
            if group == "bare" and (VARIABLE_NAME.fullmatch(value)
                                    or is_keyword_argument(text, match.start())
                                    or PLACEHOLDER_FORMS.match(value)):
                continue
            candidates.append((match.start(group), -match.end(group),
                               len(TOKEN_PATTERNS), GENERIC))
    if not candidates:
        return text, []

    # the earliest match wins (the longest, then the most specific type, of those starting at
    # the same place); a later match that overlaps it only stretches it, so every matched
    # character is replaced and nothing is counted twice
    candidates.sort()
    spans = []
    for start, negative_end, _, token_type in candidates:
        end = -negative_end
        if spans and start < spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end, token_type])

    pieces = []
    findings = []
    position = 0
    line = 1
    for start, end, token_type in spans:
        line = line + text.count("\n", position, start)
        findings.append((token_type, line))
        pieces.append(text[position:start])
        pieces.append("[REDACTED:" + token_type + "]")
        line = line + text.count("\n", start, end)
        position = end
    pieces.append(text[position:])
    return "".join(pieces), findings
