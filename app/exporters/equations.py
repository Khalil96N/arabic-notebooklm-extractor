import os
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree


MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"

_TOKEN_RE = re.compile(
    r"∑_\([^)]+\)\^[A-Za-z0-9]+|"
    r"[A-Za-z]+(?:')?(?:\d+)?"
    r"(?:_(?:[A-Za-z0-9]+|\([A-Za-z0-9,]+\)))*|"
    r"\d+(?:\.\d+)?|"
    r">=|<=|!=|\.\.\.|\S"
)


def _office_xslt_candidates() -> list[Path]:
    roots = [
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        r"C:\Program Files (x86)",
        r"C:\Program Files",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root:
            continue
        candidate = (
            Path(root)
            / "Microsoft Office"
            / "root"
            / "Office16"
            / "MML2OMML.XSL"
        )
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


@lru_cache(maxsize=1)
def _mml2omml_transform():
    for candidate in _office_xslt_candidates():
        if candidate.is_file():
            return etree.XSLT(etree.parse(str(candidate)))
    return None


def _mathml_element(parent, name: str, text: str | None = None):
    element = etree.SubElement(parent, f"{{{MATHML_NAMESPACE}}}{name}")
    if text is not None:
        element.text = text
    return element


def _append_identifier(parent, token: str) -> None:
    if token == "y_hat":
        mover = _mathml_element(parent, "mover")
        _mathml_element(mover, "mi", "y")
        accent = _mathml_element(mover, "mo", "^")
        accent.set("accent", "true")
        return

    match = re.fullmatch(
        r"(?P<base>[A-Za-z]+)(?P<prime>')?(?P<digits>\d+)?"
        r"(?P<suffix>(?:_(?:[A-Za-z0-9]+|\([A-Za-z0-9,]+\)))*)",
        token,
    )
    if match:
        base = match.group("base")
        if match.group("prime"):
            base += "′"
        subscript_parts = []
        if match.group("digits"):
            subscript_parts.append(match.group("digits"))
        suffix = match.group("suffix")
        if suffix:
            subscript_parts.extend(
                part.strip("()") for part in suffix.split("_") if part
            )
    else:
        base = token
        subscript_parts = []

    if subscript_parts:
        msub = _mathml_element(parent, "msub")
        _mathml_element(msub, "mi", base)
        subscript = ",".join(subscript_parts)
        tag = "mn" if subscript.isdigit() else "mi"
        _mathml_element(msub, tag, subscript)
        return

    identifier = _mathml_element(parent, "mi", token)
    if len(token) > 1:
        identifier.set("mathvariant", "normal")


def _append_summation(parent, token: str) -> bool:
    match = re.fullmatch(r"∑_\(([^)]+)\)\^([A-Za-z0-9]+)", token)
    if not match:
        return False

    nary = _mathml_element(parent, "munderover")
    _mathml_element(nary, "mo", "∑")
    lower = _mathml_element(nary, "mrow")
    for lower_token in _TOKEN_RE.findall(match.group(1)):
        if lower_token[0].isalpha():
            _append_identifier(lower, lower_token)
        elif lower_token[0].isdigit():
            _mathml_element(lower, "mn", lower_token)
        else:
            _mathml_element(lower, "mo", lower_token)
    upper = _mathml_element(nary, "mrow")
    for upper_token in _TOKEN_RE.findall(match.group(2)):
        if upper_token[0].isalpha():
            _append_identifier(upper, upper_token)
        else:
            _mathml_element(upper, "mn", upper_token)
    return True


def linear_equation_to_omml(expression: str):
    """Convert the limited UnicodeMath used by NotebookLM into native OMML."""
    transform = _mml2omml_transform()
    if transform is None:
        return None

    math = etree.Element(
        f"{{{MATHML_NAMESPACE}}}math",
        nsmap={None: MATHML_NAMESPACE},
    )
    row = _mathml_element(math, "mrow")

    for token in _TOKEN_RE.findall(expression.strip()):
        if _append_summation(row, token):
            continue
        if token[0].isalpha():
            _append_identifier(row, token)
        elif token[0].isdigit():
            _mathml_element(row, "mn", token)
        else:
            operator = {
                ">=": "≥",
                "<=": "≤",
                "!=": "≠",
                "...": "…",
                "-": "−",
                "*": "×",
            }.get(token, token)
            _mathml_element(row, "mo", operator)

    result = transform(math)
    root = result.getroot()
    if root is None:
        return None
    return etree.fromstring(etree.tostring(root))
