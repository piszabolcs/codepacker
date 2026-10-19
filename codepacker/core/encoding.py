# -*- coding: utf-8 -*-
#
# reading a file as text: which codec it is written in, or whether it is binary at all
# the order (spec C-5): a byte-order mark, strict UTF-8, UTF-16 without a mark (recognized by
# where its zero bytes are), then cp1250 (Central European Windows) and latin-1, which reads
# any byte; the mark itself is never part of the text

import codecs

SNIFF_BYTES = 4096

# the UTF-32 LE mark starts with the UTF-16 LE one, so it is checked first
BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
FALLBACK_CODECS = ("utf-8", "cp1250", "latin-1")

# control characters that text doesn't hold (tab, line breaks, form feed and escape it does)
CONTROL_BYTES = bytes(sorted(set(range(32)) - {9, 10, 11, 12, 13, 27}))
MAX_CONTROL_RATIO = 0.10


def decode(raw):
    # (codec, text, byte-order mark) for text, None for binary content
    for mark, codec in BYTE_ORDER_MARKS:
        if raw.startswith(mark):
            return _strict(raw[len(mark):], codec, mark)

    sample = raw[:SNIFF_BYTES]
    if b"\x00" in sample:
        codec = utf16_without_mark(raw, sample)
        return None if codec is None else _strict(raw, codec, b"")

    controls = len(sample) - len(sample.translate(None, CONTROL_BYTES))
    if controls > len(sample) * MAX_CONTROL_RATIO:
        return None

    for codec in FALLBACK_CODECS:
        decoded = _strict(raw, codec, b"")
        if decoded is not None:
            return decoded
    return None


def utf16_without_mark(raw, sample):
    # UTF-16 text in a Latin script has a zero in most code units, always on the same side
    units = len(sample) // 2
    if units == 0 or len(raw) % 2 != 0:
        return None
    even_zeros = sample[0:units * 2:2].count(0)
    odd_zeros = sample[1:units * 2:2].count(0)
    if odd_zeros >= units * 0.3 and even_zeros <= units * 0.05:
        return "utf-16-le"
    if even_zeros >= units * 0.3 and odd_zeros <= units * 0.05:
        return "utf-16-be"
    return None


def _strict(data, codec, mark):
    try:
        return codec, data.decode(codec), mark
    except UnicodeDecodeError:
        return None
