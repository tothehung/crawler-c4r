from __future__ import annotations

from src.services.evidence.snippet_cleaner import clean


def test_strips_line_number_prefixes() -> None:
    raw = "12 | contract Vault {\n13 |     uint x;\n14 | }"

    assert clean(raw) == "contract Vault {\n    uint x;\n}\n"


def test_strips_colon_line_numbers() -> None:
    raw = "10: function a() {}\n11: function b() {}"

    assert clean(raw) == "function a() {}\nfunction b() {}\n"


def test_strips_diff_markers_and_headers() -> None:
    raw = (
        "diff --git a/src/Vault.sol b/src/Vault.sol\n"
        "index abc..def 100644\n"
        "--- a/src/Vault.sol\n"
        "+++ b/src/Vault.sol\n"
        "@@ -1,4 +1,4 @@\n"
        "-uint x = 1;\n"
        "+uint x = 2;\n"
        " uint y;"
    )

    cleaned = clean(raw)

    assert cleaned == "uint x = 2;\nuint y;\n"
    assert "diff --git" not in cleaned
    assert "@@" not in cleaned
    assert "+++" not in cleaned


def test_strips_ansi_escapes() -> None:
    raw = "\x1b[31m-uint x = 1;\x1b[0m"

    assert clean(raw) == "uint x = 1;\n"


def test_empty_snippet_returns_empty_string() -> None:
    assert clean("") == ""
    assert clean("\n\n") == ""


def test_preserves_minus_sign_inside_code() -> None:
    raw = "uint delta = a - b;"

    assert "- b;" in clean(raw)
    assert clean(raw) == "uint delta = a - b;\n"
