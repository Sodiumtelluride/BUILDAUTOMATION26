"""
Where every value in a design spec came from, for reviewers.

The log is a list of plain dicts, one per value:

    {revision, target, value, source, fields, note, assumptions}

``source`` is one of:
  - ``intake``  the client gave it (``fields`` names the intake fields)
  - ``logo``    derived from the uploaded logo because no colors were given
  - ``rule``    fixed by the template or by code, not a choice
  - ``claude``  chosen by the model; ``fields`` are the intake fields it cited
                and ``assumptions`` the guesses it reported for those fields

The log is append-only across revisions: a rerun adds a row only for a value
that is new, changed or removed, so the history of each target stays readable.

The spec itself stays in the template's contract. The model replies with
assumptions as ``{text, field}`` so each links to an intake field exactly;
``split_assumptions`` records the links and writes plain strings back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .intake import DesignIntake
from .prompt import FLAG_FONT_SUBSTITUTED, FLAG_LOGO_UNREADABLE, FLAG_UNSUPPORTED_FEATURE
from .validate import BODY_FONT, FEATURE_SECTIONS

INTAKE_FIELDS: Tuple[str, ...] = tuple(DesignIntake.model_fields)

BrandColorsSource = str  # "intake" | "logo"

# For a value the model chose freely, the assumptions shown beside it are the
# ones citing these intake fields.
_COLOR_FIELDS = ("brand_colors", "logo", "visual_style", "organization_type")
_FONT_FIELDS = ("brand_fonts", "visual_style", "tone")
_RADIUS_FIELDS = ("visual_style", "tone")


@dataclass(frozen=True)
class AssumptionLink:
    text: str
    field: Optional[str]
    """The intake field the guess is about; None only for a spec written before links existed."""


def split_assumptions(spec: Dict[str, Any], *, require_links: bool = True) -> Tuple[List[AssumptionLink], List[str]]:
    """Read ``{text, field}`` assumptions and write plain strings back into ``spec``.

    Returns (links, issues). With ``require_links=False`` a plain string is
    accepted as an unlinked assumption (an already-final spec being re-checked).
    """
    raw = spec.get("assumptions")
    if not isinstance(raw, list):
        return [], []  # the schema check reports it
    links: List[AssumptionLink] = []
    issues: List[str] = []
    for i, item in enumerate(raw):
        if isinstance(item, str) and not require_links:
            links.append(AssumptionLink(text=item, field=None))
        elif not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            issues.append(f'assumptions[{i}]: must be {{"text": "...", "field": "<intake field>"}}')
        elif item.get("field") not in INTAKE_FIELDS:
            issues.append(f"assumptions[{i}].field: {item.get('field')!r} is not an intake field; use one of: {', '.join(INTAKE_FIELDS)}")
        else:
            links.append(AssumptionLink(text=item["text"], field=item["field"]))
    if not issues:
        spec["assumptions"] = [link.text for link in links]
    return links, issues


def to_reply_shape(spec: Mapping[str, Any], links: Sequence[AssumptionLink]) -> Dict[str, Any]:
    """A final spec as the model must write it: assumptions back as ``{text, field}``.

    The inverse of ``split_assumptions``; used to show the model its previous spec on a rerun.
    """
    return {**spec, "assumptions": [{"text": link.text, "field": link.field} for link in links]}


def source_issues(spec: Mapping[str, Any]) -> List[str]:
    """Problems that would leave a value without a source. ``spec`` must be schema-valid."""
    issues: List[str] = []
    for p, page in enumerate(spec["pages"]):
        for s, section in enumerate(page["sections"]):
            at = f"pages[{p}].sections[{s}].source_fields"
            if not section["source_fields"]:
                issues.append(f"{at}: name at least one intake field")
            for name in section["source_fields"]:
                if name not in INTAKE_FIELDS:
                    issues.append(f"{at}: {name!r} is not an intake field")
    colors: Mapping[str, str] = spec["tokens"]["colors"]
    for i, item in enumerate(spec["tokens"]["contrast_adjustments"]):
        at = f"tokens.contrast_adjustments[{i}]"
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("role", "from", "to")):
            issues.append(f'{at}: must be {{"role": "<color role>", "from": "#RRGGBB", "to": "#RRGGBB"}}')
        elif item["role"] not in colors:
            issues.append(f"{at}.role: {item['role']!r} is not a color role")
        elif item["to"].upper() != colors[item["role"]].upper():
            issues.append(f"{at}.to: must equal tokens.colors.{item['role']} ({colors[item['role']]})")
    return issues


def _entry(target: str, value: Any, source: str, fields: Sequence[str] = (), note: str = "", assumptions: Sequence[str] = ()) -> Dict[str, Any]:
    return {"target": target, "value": value, "source": source, "fields": list(fields), "note": note, "assumptions": list(assumptions)}


def _current_entries(
    spec: Mapping[str, Any],
    intake: DesignIntake,
    links: Sequence[AssumptionLink],
    brand_colors_source: Optional[BrandColorsSource],
) -> List[Dict[str, Any]]:
    def guesses(fields: Sequence[str]) -> List[str]:
        return [link.text for link in links if link.field in fields]

    entries: List[Dict[str, Any]] = []
    tokens = spec["tokens"]

    brand = [c.upper() for c in intake.brand_colors]
    from_logo = brand_colors_source == "logo"
    brand_source, brand_field = ("logo", "logo") if from_logo else ("intake", "brand_colors")
    adjusted = {a["role"]: a["from"].upper() for a in tokens["contrast_adjustments"]}
    for role, value in tokens["colors"].items():
        target = f"tokens.colors.{role}"
        if value.upper() in brand:
            entries.append(_entry(target, value, brand_source, [brand_field]))
        elif adjusted.get(role) in brand:
            entries.append(_entry(target, value, brand_source, [brand_field], note=f"adjusted for contrast from {adjusted[role]}"))
        else:
            entries.append(_entry(target, value, "claude", assumptions=guesses(_COLOR_FIELDS)))

    heading = tokens["fonts"]["heading"]
    if heading in intake.brand_fonts:
        entries.append(_entry("tokens.fonts.heading", heading, "intake", ["brand_fonts"]))
    elif intake.brand_fonts:
        requested = ", ".join(intake.brand_fonts)
        entries.append(_entry("tokens.fonts.heading", heading, "rule", ["brand_fonts"], note=f"substituted for {requested}, which the template does not bundle"))
    else:
        entries.append(_entry("tokens.fonts.heading", heading, "claude", assumptions=guesses(_FONT_FIELDS)))
    entries.append(_entry("tokens.fonts.body", tokens["fonts"]["body"], "rule", note=f"the template's body font is always {BODY_FONT}"))
    entries.append(_entry("tokens.radius", tokens["radius"], "claude", assumptions=guesses(_RADIUS_FIELDS)))

    feature_of = {type_id: feature for feature, type_id in FEATURE_SECTIONS.items()}
    for page in spec["pages"]:
        entries.append(_entry(f"pages.{page['slug']}", page["slug"], "intake", ["pages"]))
        for section in page["sections"]:
            value = {"type": section["type"], "page": page["slug"]}
            feature = feature_of.get(section["type"])
            note = f"the {feature} feature requires this section" if feature else ""
            entries.append(_entry(f"sections.{section['id']}", value, "rule" if feature else "claude", section["source_fields"], note=note))

    entries.append(_entry("features", spec["features"], "intake", ["features"]))
    entries.append(_entry("integrations", spec["integrations"], "intake", ["integrations"]))
    entries.append(_entry("data_requirements", spec["data_requirements"], "rule", note="set by the sections that need stored data"))

    seen: Dict[str, int] = {}
    for flag in spec["flags"]:
        n = seen.get(flag["code"], 0)
        seen[flag["code"]] = n + 1
        target = f"flags.{flag['code']}[{n}]"
        if flag["code"] == FLAG_FONT_SUBSTITUTED:
            entries.append(_entry(target, flag["detail"], "rule", ["brand_fonts"]))
        elif flag["code"] == FLAG_UNSUPPORTED_FEATURE:
            entries.append(_entry(target, flag["detail"], "rule", ["features"]))
        elif flag["code"] == FLAG_LOGO_UNREADABLE:
            entries.append(_entry(target, flag["detail"], "rule", ["logo"]))
        else:
            entries.append(_entry(target, flag["detail"], "claude"))

    # Keyed by field and text, not position, so reordering or dropping one guess does not touch the others.
    # A reworded guess is therefore one removed row and one added row. Exact duplicates collapse into one.
    keyed = {f"assumptions.{link.field or 'unlinked'}: {link.text}": link for link in links}
    for target, link in keyed.items():
        entries.append(_entry(target, link.text, "claude", [link.field] if link.field else []))
    return entries


def build_source_log(
    spec: Mapping[str, Any],
    intake: DesignIntake,
    links: Sequence[AssumptionLink],
    *,
    brand_colors_source: Optional[BrandColorsSource],
    revision: int,
    previous_log: Sequence[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """The previous log plus one row per value that is new, changed or removed in this revision."""
    latest: Dict[str, Mapping[str, Any]] = {}
    for row in previous_log:
        latest[row["target"]] = row

    log: List[Dict[str, Any]] = [dict(row) for row in previous_log]
    current = _current_entries(spec, intake, links, brand_colors_source)
    for entry in current:
        before = latest.get(entry["target"])
        if before is None or any(before[k] != entry[k] for k in ("value", "source", "fields", "note", "assumptions")):
            log.append({"revision": revision, **entry})
    present = {entry["target"] for entry in current}
    for target, before in latest.items():
        if target not in present and before["source"] != "removed":
            log.append({"revision": revision, **_entry(target, None, "removed", note=f"no longer in the spec as of revision {revision}")})
    return log
