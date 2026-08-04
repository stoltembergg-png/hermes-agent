"""@mention parser.

Implements PR-002 of the vector roadmap
(docs/roadmap/prs/PR-002-mention-parser.md).

A pure function that extracts `@<handle>` mentions from chat text.
Handles word boundaries, multi-word display names (longest-first match
against a known set), and code-fence / inline-code exclusion so that
`` `@gandalf` `` inside backticks is not matched.

Adapted from ``stoltembergg-png/buzz``'s ``crates/buzz-sdk/src/mentions.rs``,
but stripped of Nostr specifics and made Pythonic.
"""

from __future__ import annotations

from collections.abc import Iterable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Hard upper bound on how many distinct mentions a single message can
#: produce. Matches the cap enforced by Buzz message builders and the
#: legacy MCP inline implementation.
MENTION_CAP: int = 50

#: Characters allowed inside a handle. ASCII alphanumerics plus . _ -.
_HANDLE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


# ---------------------------------------------------------------------------
# Code-region stripping
# ---------------------------------------------------------------------------


def _strip_code_regions(text: str) -> str:
    """Replace fenced and inline code with spaces of equal length.

    Preserves offsets so the rest of the parser can scan in place.
    A ``@handle`` inside a code region is matched against spaces /
    non-@ characters only, never as a real mention.
    """
    out = list(text)
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "`":
            # Fenced code block: ``` ... ```
            if i + 2 < n and text[i + 1] == "`" and text[i + 2] == "`":
                # Find closing ```
                j = i + 3
                while j + 2 < n and not (text[j] == "`" and text[j + 1] == "`" and text[j + 2] == "`"):
                    j += 1
                end = min(j + 3, n)
                for k in range(i, end):
                    if text[k] != "\n":
                        out[k] = " "
                i = end
                continue
            # Inline code span: ` ... `
            j = i + 1
            while j < n and text[j] != "`":
                # A newline inside backticks is allowed only if it
                # closes a fenced block (handled above). For inline,
                # backtick must close on same line.
                if text[j] == "\n":
                    break
                j += 1
            if j < n and text[j] == "`":
                # Closed inline span — blank it.
                for k in range(i, j + 1):
                    out[k] = " "
                i = j + 1
                continue
            # Unclosed backtick — leave as-is and advance.
            i += 1
            continue
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Mention extraction
# ---------------------------------------------------------------------------


def _scan_known(
    text: str,
    known_names: list[str],
    out: list[str],
    seen: set[str],
) -> None:
    """Try known names longest-first at every ``@`` token.

    Updates ``out`` (preserving insertion order) and ``seen`` (for
    deduplication). When a known name matches, the matched region is
    blanked in a working copy so subsequent scans don't re-match.
    """
    if not known_names:
        return
    work = list(text)
    n = len(work)
    i = 0
    while i < n:
        if work[i] != "@":
            i += 1
            continue
        # Word-boundary check: @ must be at start-of-string or
        # preceded by whitespace.
        if i > 0 and not work[i - 1].isspace():
            i += 1
            continue
        matched_name: str | None = None
        matched_end = i + 1
        for name in known_names:
            end = i + 1 + len(name)
            if end > n:
                continue
            candidate = text[i + 1 : end]
            if candidate.lower() != name.lower():
                continue
            # Word boundary on the right: char after name must be
            # whitespace, end-of-string, or non-handle punctuation.
            if end < n and work[end] in _HANDLE_CHARS:
                continue
            matched_name = name.lower()
            matched_end = end
            break
        if matched_name is not None:
            if matched_name not in seen:
                seen.add(matched_name)
                out.append(matched_name)
            # Blank the matched region so single-word fallback below
            # doesn't double-match.
            for k in range(i, matched_end):
                work[k] = " "
            i = matched_end
        else:
            i += 1


def _scan_single_word(text: str, out: list[str], seen: set[str]) -> None:
    """Fallback: extract single-word ``@handle`` mentions.

    Used when ``known_names`` is empty or when no known name matched.
    Each handle is a maximal run of `_HANDLE_CHARS` immediately after
    a word-bounded ``@``.
    """
    n = len(text)
    i = 0
    while i < n:
        if text[i] != "@":
            i += 1
            continue
        if i > 0 and not text[i - 1].isspace():
            i += 1
            continue
        end = i + 1
        while end < n and text[end] in _HANDLE_CHARS:
            end += 1
        if end > i + 1:
            name = text[i + 1 : end].lower()
            if name not in seen:
                seen.add(name)
                out.append(name)
            i = end
        else:
            i += 1


def extract_mentions(
    text: str,
    known_names: Iterable[str] | None = None,
) -> list[str]:
    """Extract ``@handle`` mentions from ``text``.

    Args:
        text: The chat message to scan.
        known_names: Optional iterable of canonical display names. When
            provided, multi-word names are tried longest-first at each
            ``@`` token. The single-word fallback still runs for any
            ``@`` that no known name matched.

    Returns:
        A deduplicated, ordered list of lowercased handles. Never
        exceeds :data:`MENTION_CAP` entries.

    The function is pure (no I/O, no globals) and deterministic for
    any given input.
    """
    if not isinstance(text, str) or not text:
        return []
    if "@" not in text:
        return []

    # Strip code regions first so mentions inside ``code`` are
    # invisible to the scanner.
    scrubbed = _strip_code_regions(text)

    seen: set[str] = set()
    out: list[str] = []

    # Normalise known_names: drop blanks, keep longest-first order.
    if known_names is not None:
        # Stable-sort longest-first; known_names order is preserved
        # among ties so the spec deterministic-output guarantee holds.
        names = [n for n in known_names if n and n.strip()]
        names.sort(key=lambda s: (-len(s),))
        _scan_known(scrubbed, names, out, seen)

    _scan_single_word(scrubbed, out, seen)

    if len(out) > MENTION_CAP:
        out = out[:MENTION_CAP]

    return out
