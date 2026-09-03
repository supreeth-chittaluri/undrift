"""
The embeddable skill card: an SVG rendered server-side from live scores.

This exists so the README's hero image is real data rather than a screenshot
that goes stale the day after it is taken. GitHub renders it like any other
image, so the repository's front page shows whatever the last sync computed.

Everything is inlined by necessity. GitHub proxies images through camo, which
strips scripts, refuses external references, and will not load a webfont -- so
the card carries its own geometry, its own colours, and a generic font stack,
and uses no <style> block, no <script>, and no href. What survives that is
plain shapes and text, which is all this needs anyway.
"""

from typing import List, Optional
from xml.sax.saxutils import escape

from .scoring import FADING_THRESHOLD, FRESH_THRESHOLD

# Matched to the dashboard's tokens in index.css, deliberately duplicated:
# the card has to be a single self-contained file, so it cannot read them.
BG = "#0d1220"
BORDER = "#1e2941"
TEXT = "#e8edf7"
TEXT_DIM = "#96a3bd"
TEXT_FAINT = "#5f6d88"
TRACK = "#161f33"
FRESH = "#34d399"
FADING = "#fbbf24"
STALE = "#f87171"

FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
)

WIDTH = 640
PAD = 22
ROW_H = 38
HEADER_H = 74
FOOTER_H = 34


def _colour(freshness: float) -> str:
    if freshness >= FRESH_THRESHOLD:
        return FRESH
    if freshness >= FADING_THRESHOLD:
        return FADING
    return STALE


def _truncate(text: str, limit: int) -> str:
    """Trim a label to fit. SVG text does not wrap or ellipsize on its own."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_card(
    username: str,
    skills: List[dict],
    total_commits: int,
    synced_label: Optional[str] = None,
) -> str:
    """
    Build the SVG for one profile.

    `skills` is a list of dicts with at least `skill` and `freshness`, already
    sorted and already truncated to however many rows should appear.
    """
    rows = len(skills)
    height = HEADER_H + max(rows, 1) * ROW_H + FOOTER_H
    bar_x = 210
    bar_w = WIDTH - bar_x - PAD - 46

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{height}" viewBox="0 0 {WIDTH} {height}" '
        f'role="img" aria-label="Skill freshness for {escape(username)}">',
        # Rounded card. A plain rect would show square corners against the
        # README's own background.
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" '
        f'rx="12" fill="{BG}" stroke="{BORDER}"/>',
    ]

    # --- header ---
    # The mark: three bars of decreasing height in fresh/fading/stale order.
    # Bottom-aligned, so it reads as something falling away rather than as
    # three unrelated blocks.
    base = PAD + 16
    for dx, h, fill in ((0, 16, FRESH), (6, 10, FADING), (12, 5, STALE)):
        parts.append(
            f'<rect x="{PAD + dx}" y="{base - h}" width="4" height="{h}" '
            f'rx="2" fill="{fill}"/>'
        )
    parts.append(
        f'<text x="{PAD + 26}" y="{PAD + 13}" font-family="{FONT}" font-size="14" '
        f'font-weight="600" fill="{TEXT}">Undrift</text>'
        f'<text x="{PAD + 84}" y="{PAD + 13}" font-family="{FONT}" font-size="13" '
        f'fill="{TEXT_FAINT}">@{escape(username)}</text>'
    )
    parts.append(
        f'<text x="{PAD}" y="{PAD + 38}" font-family="{FONT}" font-size="11" '
        f'letter-spacing="0.8" fill="{TEXT_FAINT}">SKILL FRESHNESS — LIVE</text>'
    )

    # --- rows ---
    if not rows:
        parts.append(
            f'<text x="{PAD}" y="{HEADER_H + 20}" font-family="{FONT}" '
            f'font-size="13" fill="{TEXT_DIM}">No skills scored yet.</text>'
        )

    for i, skill in enumerate(skills):
        y = HEADER_H + i * ROW_H
        freshness = float(skill["freshness"])
        colour = _colour(freshness)
        filled = max(2.0, bar_w * min(freshness, 100.0) / 100.0)

        parts.append(
            f'<text x="{PAD}" y="{y + 14}" font-family="{FONT}" font-size="13" '
            f'fill="{TEXT}">{escape(_truncate(str(skill["skill"]), 22))}</text>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{y + 5}" width="{bar_w}" height="8" rx="4" '
            f'fill="{TRACK}"/>'
            f'<rect x="{bar_x}" y="{y + 5}" width="{filled:.1f}" height="8" rx="4" '
            f'fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{WIDTH - PAD}" y="{y + 14}" font-family="{FONT}" '
            f'font-size="13" font-weight="600" text-anchor="end" '
            f'fill="{colour}">{freshness:.0f}</text>'
        )

    # --- footer ---
    foot_y = height - 14
    caption = f"{total_commits} commits classified by Claude"
    if synced_label:
        caption += f" · synced {synced_label}"
    parts.append(
        f'<line x1="{PAD}" y1="{foot_y - 20}" x2="{WIDTH - PAD}" y2="{foot_y - 20}" '
        f'stroke="{BORDER}"/>'
    )
    parts.append(
        f'<text x="{PAD}" y="{foot_y}" font-family="{FONT}" font-size="11" '
        f'fill="{TEXT_FAINT}">{escape(caption)}</text>'
    )

    parts.append("</svg>")
    return "".join(parts)
