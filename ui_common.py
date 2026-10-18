"""HTML fragments shared by the Gradio tabs and the sign-in page.

Every interpolated value goes through :func:`esc`, so user-entered habitat notes,
session names and usernames can never inject markup into the page.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

RISK_LABELS = {"low": "Low risk", "moderate": "Moderate risk", "high": "High risk"}
RISK_HELP = {
    "low": "Narrow cap with open gills",
    "moderate": "Worth a second look before logging",
    "high": "Broad cap and crowded gills — check against the lookalike key",
}
DISCLAIMER = (
    "Heuristic only — this score weighs cap width and gill crowding, it does not identify "
    "a species and never replaces a spore print key. Never eat anything based on this tool."
)


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_int(value: float | int) -> str:
    return f"{int(round(value)):,}"


def humanize_iso(value: str | None) -> str:
    """Relative date that never renders leak strings like 'Invalid Date'."""
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return "—"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed
    seconds = delta.total_seconds()
    if seconds < 0:
        return parsed.strftime("%d %b %Y")
    if seconds < 3600:
        minutes = max(1, int(seconds // 60))
        return f"{minutes} min ago"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} h ago" if hours > 1 else "1 h ago"
    days = int(seconds // 86400)
    if days < 7:
        return f"{days} days ago" if days > 1 else "yesterday"
    return parsed.strftime("%d %b %Y")


def swatch_chip(hex_colour: str, size: str = "md") -> str:
    return (
        f'<span class="chip chip--{esc(size)}" style="--chip:{esc(hex_colour)}" '
        f'aria-hidden="true"></span>'
    )


def risk_pill(band: str) -> str:
    label = RISK_LABELS.get(band, band)
    return f'<span class="pill pill--{esc(band)}">{esc(label)}</span>'


def empty_state(title: str, body: str, action: str = "") -> str:
    action_html = f'<p class="empty__action">{action}</p>' if action else ""
    return (
        '<div class="empty">'
        f'<p class="empty__title">{esc(title)}</p>'
        f'<p class="empty__body">{esc(body)}</p>'
        f"{action_html}"
        "</div>"
    )


def section_header(title: str, meta: str = "", step: str = "") -> str:
    step_html = f'<span class="step">{esc(step)}</span>' if step else ""
    meta_html = f'<span class="section__meta">{esc(meta)}</span>' if meta else ""
    return (
        f'<div class="section__header">{step_html}<h2 class="section__title">{esc(title)}</h2>'
        f"{meta_html}</div>"
    )


# --- matcher ---------------------------------------------------------------
def match_card(result: dict | None, photo_name: str | None = None) -> str:
    if not result:
        return (
            '<div class="match match--empty">'
            '<p class="match__eyebrow">Closest swatch class</p>'
            '<p class="match__placeholder">Drop a spore print photo to see the closest of the six '
            "colour classes, its hex chip, delta-E and confidence.</p>"
            "</div>"
        )
    source = f'<p class="match__source">Matched from {esc(photo_name or "your photo")}</p>' if photo_name else ""
    print_stat = ""
    if result.get("print_hex"):
        print_stat = f'<div><dt>Print colour</dt><dd>{esc(result["print_hex"])}</dd></div>'
    lab = ""
    if all(result.get(key) is not None for key in ("lab_l", "lab_a", "lab_b")):
        lab = (
            f'<div><dt>Lab centroid</dt><dd>{result["lab_l"]:.1f} · {result["lab_a"]:.1f} · '
            f'{result["lab_b"]:.1f}</dd></div>'
        )
    return (
        '<div class="match">'
        '<p class="match__eyebrow">Closest swatch class</p>'
        '<div class="match__head">'
        f"{swatch_chip(result['hex'], 'lg')}"
        f'<div><p class="match__name">{esc(result["name"])}</p>'
        f'<p class="match__hex">{esc(result["hex"])}</p></div>'
        f'<span class="match__confidence"><span class="match__confidence-value">'
        f'{result.get("confidence", 0.0):.1f}%</span><span class="match__confidence-label">confidence</span></span>'
        "</div>"
        '<dl class="match__stats">'
        f'<div><dt>Delta-E (CIE76)</dt><dd>{result.get("delta_e", 0.0):.2f}</dd></div>'
        f"{print_stat}"
        f"{lab}"
        "</dl>"
        f"{source}"
        "</div>"
    )


def score_card(score: dict, cap_mm: float, gill_mm: float) -> str:
    band = score["risk_band"]
    factors = "".join(
        f'<li class="factor"><span class="factor__tag">{esc(item["component"])}</span>'
        f'<span class="factor__text">{esc(item["text"])}</span></li>'
        for item in score["factors"]
    )
    return (
        '<div class="score">'
        '<div class="score__head">'
        '<p class="match__eyebrow">Lookalike warning score</p>'
        f"{risk_pill(band)}"
        "</div>"
        '<div class="score__gauge">'
        f'<span class="score__value">{score["score"]:.0f}</span>'
        f'<span class="score__unit">/ 100 · {esc(RISK_HELP.get(band, ""))}</span>'
        "</div>"
        f'<div class="score__track" role="img" aria-label="Warning score {score["score"]:.0f} out of 100">'
        f'<span class="score__fill score__fill--{esc(band)}" style="width:{score["score"]:.0f}%"></span>'
        "</div>"
        '<ul class="factors">'
        f"{factors}"
        "</ul>"
        f'<p class="disclaimer">{esc(DISCLAIMER)}</p>'
        "</div>"
    )


# --- foray -----------------------------------------------------------------
def findings_table(findings: list[dict], session_name: str = "") -> str:
    if not findings:
        where = f" in “{esc(session_name)}”" if session_name else ""
        return empty_state(
            "No finds logged yet",
            f"There are no spore print finds{where}. Upload a print on the Matcher tab and save it here.",
            "Every saved find keeps its swatch, confidence, habitat and risk band.",
        )
    rows = []
    for index, row in enumerate(findings):
        thumb = ""
        if row.get("image_path"):
            filename = str(row["image_path"]).split("/")[-1]
            thumb = (
                f'<img class="thumb" src="/media/{esc(filename)}" width="36" height="36" '
                f'alt="Spore print for {esc(row["habitat"])}" loading="lazy">'
            )
        rows.append(
            f'<tr style="--i:{min(index, 7)}">'
            f'<td data-label="Swatch"><span class="cell-swatch">{thumb}{swatch_chip(row["swatch_hex"])}'
            f'<span class="cell-swatch__name">{esc(row["swatch_name"])}</span>'
            f'<span class="cell-swatch__hex">{esc(row["swatch_hex"])}</span></span></td>'
            f'<td data-label="Confidence" class="num">{row["match_confidence"]:.1f}%</td>'
            f'<td data-label="Habitat" class="wrap">{esc(row["habitat"])}</td>'
            f'<td data-label="Cap" class="num">{row["cap_diameter_mm"]:.0f} mm</td>'
            f'<td data-label="Gill spacing" class="num">{row["gill_spacing"]:.1f} mm</td>'
            f'<td data-label="Risk band">{risk_pill(row["risk_band"])}</td>'
            f'<td data-label="Logged" class="num">{esc(humanize_iso(row["created_at"]))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="data-table">'
        "<thead><tr>"
        '<th scope="col">Swatch</th>'
        '<th scope="col" class="num">Confidence</th>'
        '<th scope="col">Habitat</th>'
        '<th scope="col" class="num">Cap ⌀</th>'
        '<th scope="col" class="num">Gill spacing</th>'
        '<th scope="col">Risk band</th>'
        '<th scope="col" class="num">Logged</th>'
        "</tr></thead>"
        f'<tbody>{"".join(rows)}</tbody>'
        "</table></div>"
    )


# --- dashboard -------------------------------------------------------------
def kpi_strip(payload: dict, session_label: str) -> str:
    swatches_present = len([row for row in payload["swatch_counts"] if row["count"] > 0])
    cells = [
        ("Finds", fmt_int(payload["total_findings"]), session_label, "finds"),
        ("Mean confidence", f'{payload["mean_confidence"]:.1f}%', "across these finds", "confidence"),
        ("High-risk finds", fmt_int(payload["high_risk_count"]), "broad cap + crowded gills", "high-risk"),
        ("Swatch classes", f"{swatches_present} / 6", "represented in the selection", "swatches"),
    ]
    html_cells = "".join(
        f'<div class="kpi" style="--i:{index}">'
        f'<p class="kpi__label">{esc(label)}</p>'
        f'<p class="kpi__value">{esc(value)}</p>'
        f'<p class="kpi__meta">{esc(meta)}</p>'
        "</div>"
        for index, (label, value, meta, _key) in enumerate(cells)
    )
    return f'<div class="kpi-strip">{html_cells}</div>'


def swatch_key(payload: dict) -> str:
    chips = "".join(
        f'<span class="key__item">{swatch_chip(row["hex"], "sm")}<span>{esc(row["name"])}</span></span>'
        for row in payload["swatch_counts"]
    )
    return f'<p class="key">{chips}</p>' if chips else ""
