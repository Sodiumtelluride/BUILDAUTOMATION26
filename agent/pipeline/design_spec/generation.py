"""
Design generation from the Stage 1 intake (BUI-64/65/66).

Split of responsibilities:
  - ``build_generation_input`` maps every frozen intake field into the
    generation input, with its role (hard constraint, inspiration, ...).
    Nothing the client told us is dropped on the floor.
  - The model only makes layout choices: a ``LayoutPlan`` picking approved
    catalog section types for each requested page, citing the intake fields
    behind each pick.
  - ``assemble_design_spec`` turns intake + plan into the full design_spec
    deterministically: tokens from brand inputs (or BUILD defaults), the page
    map, content blocks from the catalog's slot definitions, flags, and a D5
    decision log in which every value cites its source.

Stable IDs: on a rerun, section IDs are reused for the same section type on
the same page (revisions.py rules), and surviving sections keep their content
block IDs, so CODE_GENERATION and CONTENT work keyed by those IDs survives.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, get_args

from pydantic import Field

from .catalog import CATALOG_VERSION, FEATURE_SECTION_TYPES, SECTION_CATALOG, get_section_def
from .decisions import (
    flag_target,
    from_config,
    from_default,
    from_intake,
    from_rule,
    record_decision,
    superseded_ids,
)
from .intake import PAGE_SLUGS, BrandingField, DesignIntake, PageName, missing_branding
from .issues import ValidationIssue, format_issues_for_repair
from .schema import (
    ColorRole,
    ContentBlock,
    DataRecipe,
    DataRequirement,
    Decision,
    DefaultDesignTrackFlag,
    DesignSpec,
    Feature,
    Flag,
    Fonts,
    IntakeField,
    IntakeSource,
    NoFigmaFlag,
    NonEmptyUniqueList,
    Page,
    Rem,
    Section,
    SectionType,
    Source,
    Tokens,
    _Strict,
)

# ---------------------------------------------------------------------------
# BUILD default design track (D10): used for whatever branding is missing
# ---------------------------------------------------------------------------

DEFAULT_COLORS: Dict[ColorRole, str] = {
    "background": "#FFFFFF",
    "foreground": "#0F172A",
    "primary": "#1A3C6E",
    "primary_foreground": "#FFFFFF",
    "secondary": "#C9A84C",
    "secondary_foreground": "#1A1A1A",
    "muted": "#F1F5F9",
    "muted_foreground": "#475569",
    "accent": "#E0E7FF",
    "accent_foreground": "#1E1B4B",
    "border": "#E2E8F0",
}

DEFAULT_FONTS = ("Source Serif 4", "Inter")  # (heading, body)
DEFAULT_RADIUS = "0.5rem"

# D4: features that need storage, and the recipe that provides it.
FEATURE_DATA_RECIPES: Dict[Feature, DataRecipe] = {
    "contact_form": "form_submissions",
    "member_application_form": "form_submissions",
    "newsletter_signup": "form_submissions",
    "event_calendar": "events",
}


# ---------------------------------------------------------------------------
# Generation input: every intake field, with its role (BUI-64)
# ---------------------------------------------------------------------------


def build_generation_input(intake: DesignIntake) -> Dict[str, Any]:
    """
    Map the full Stage 1 intake into the design-generation input.

    Keys are exactly the ``IntakeField`` names, so a test (and a reviewer) can
    check that no intake field is missing from generation.
    """
    gen_input: Dict[str, Any] = {
        "organization_name": intake.organization_name,
        "organization_type": intake.organization_type,
        "primary_goal": intake.primary_goal,
        "organization_description": intake.organization_description,
        "target_audience": intake.target_audience,
        "pages": list(intake.pages),
        "features": list(intake.features),
        "tone": list(intake.tone),
        "visual_style": intake.visual_style,
        "brand_colors": list(intake.brand_colors),
        "brand_fonts": list(intake.brand_fonts),
        "logo": intake.logo,
        "brand_assets": list(intake.brand_assets),
        "reference_sites": {
            "urls": list(intake.reference_sites),
            "role": "inspiration_only",  # never content or designs to copy
        },
        "integrations": list(intake.integrations),
        "content_exclusions": {
            "text": intake.content_exclusions,
            "role": "hard_constraint",  # applies to every generated decision
        },
    }
    missing = set(get_args(IntakeField)) - set(gen_input)
    if missing:  # keeps this map in lockstep with the IntakeField vocabulary
        raise ValueError(f"intake fields not wired into generation: {sorted(missing)}")
    return gen_input


# ---------------------------------------------------------------------------
# What the model returns: a layout plan over approved section types
# ---------------------------------------------------------------------------


class PlannedSection(_Strict):
    type: SectionType
    sources: NonEmptyUniqueList[IntakeField]
    """The intake fields that motivated this section (D5, method="llm")."""


class PlannedPage(_Strict):
    page: PageName
    sections: List[PlannedSection] = Field(min_length=1)


class LayoutPlan(_Strict):
    pages: List[PlannedPage] = Field(min_length=1)
    radius: Rem = DEFAULT_RADIUS
    """Corner radius read from the visual style description."""


def render_plan_prompt(gen_input: Mapping[str, Any], previous_issues: Sequence[ValidationIssue] = ()) -> str:
    """The prompt for the layout plan. Includes repair feedback on a retry."""
    catalog_lines = "\n".join(
        f"- {d.type}: slots {', '.join(s.name + ('*' if s.required else '') for s in d.slots)}"
        for d in SECTION_CATALOG.values()
    )
    feature_hints = "\n".join(
        f"- {feature} -> {section_type}"
        for feature, section_type in FEATURE_SECTION_TYPES.items()
        if section_type is not None and feature in gen_input["features"]
    )
    exclusions = gen_input["content_exclusions"]["text"]
    reference_sites = gen_input["reference_sites"]["urls"]
    lines = [
        "You are the BUILD UMass design planner. Choose the sections for each requested page.",
        "",
        "Client intake:",
        f"- Organization: {gen_input['organization_name']} ({gen_input['organization_type']})",
        f"- Primary goal: {gen_input['primary_goal']}",
        f"- Description: {gen_input['organization_description']}",
        f"- Target audience: {gen_input['target_audience']}",
        f"- Requested pages: {', '.join(gen_input['pages'])}",
        f"- Requested features: {', '.join(gen_input['features']) or 'none'}",
        f"- Tone (use all, at most three): {', '.join(gen_input['tone'])}",
        f"- Visual style: {gen_input['visual_style']}",
        f"- Brand colors: {', '.join(gen_input['brand_colors']) or 'none provided'}",
        f"- Brand fonts: {', '.join(gen_input['brand_fonts']) or 'none provided'}",
        f"- Logo: {gen_input['logo'] or 'none provided'}",
        f"- Brand assets: {', '.join(gen_input['brand_assets']) or 'none'}",
        f"- Integrations: {', '.join(gen_input['integrations']) or 'none'}",
        "",
        f"Approved BUILD section catalog, version {CATALOG_VERSION} (the ONLY allowed types; * = required slot):",
        catalog_lines,
        "",
        "Rules:",
        "- Produce one entry per requested page, and no other pages.",
        "- Pick and order sections for each page from the catalog types above. Never invent a type.",
        "- For every section, cite the intake fields that motivated it in `sources`.",
    ]
    if feature_hints:
        lines += ["- Every requested feature needs its section somewhere:", feature_hints]
    if reference_sites:
        lines.append(
            f"- Reference sites ({', '.join(reference_sites)}) are inspiration only: "
            "do not copy their content, structure, or designs."
        )
    if exclusions:
        lines.append(
            f'- Hard constraint — the client\'s "never say or do": "{exclusions}". '
            "No section choice may conflict with it."
        )
    if previous_issues:
        lines += [
            "",
            "Your previous plan produced an invalid design spec. Fix exactly these problems:",
            format_issues_for_repair(previous_issues),
        ]
    lines += [
        "",
        "Reply with JSON only, shaped as:",
        '{"pages": [{"page": "<requested page>", "sections": [{"type": "<catalog type>", '
        '"sources": ["<intake field>", ...]}]}], "radius": "<css rem value, e.g. 0.5rem>"}',
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic assembly: intake + plan -> full design_spec dict
# ---------------------------------------------------------------------------


def page_key(slug: str) -> str:
    """First segment of a content block ID, e.g. "/" -> "home", "/join" -> "join"."""
    return "home" if slug == "/" else slug.strip("/").replace("/", "-")


def assemble_design_spec(
    job_id: uuid.UUID,
    intake: DesignIntake,
    plan: LayoutPlan,
    previous: Optional[DesignSpec] = None,
    revision: int = 1,
) -> Dict[str, Any]:
    """
    Build the design_spec dict for validation. Pure function.

    The result still goes through ``validate_design_spec`` — a plan that used
    an unknown section type or skipped a requested page assembles into a spec
    that validation rejects, which feeds the retry loop.
    """
    # -- Tokens -------------------------------------------------------------
    colors: Dict[ColorRole, str] = dict(DEFAULT_COLORS)
    brand_roles: List[ColorRole] = []
    if intake.brand_colors:
        colors["primary"] = intake.brand_colors[0]
        brand_roles.append("primary")
        if len(intake.brand_colors) > 1:
            colors["secondary"] = intake.brand_colors[1]
            brand_roles.append("secondary")
    default_roles: List[ColorRole] = [r for r in colors if r not in brand_roles]

    if intake.brand_fonts:
        fonts = Fonts(
            heading=intake.brand_fonts[0],
            body=intake.brand_fonts[1] if len(intake.brand_fonts) > 1 else intake.brand_fonts[0],
        )
    else:
        fonts = Fonts(heading=DEFAULT_FONTS[0], body=DEFAULT_FONTS[1])

    tokens = Tokens(colors=colors, fonts=fonts, radius=plan.radius, contrast_adjustments=[])

    # -- Page map with stable IDs (BUI-65/66) --------------------------------
    planned_by_page = {p.page: p for p in plan.pages}
    prev_queue: Dict[Tuple[str, str], List[Section]] = {}
    reserved_ids = set()
    if previous is not None:
        for prev_page in previous.pages:
            for old_section in prev_page.sections:
                prev_queue.setdefault((prev_page.slug, old_section.type), []).append(old_section)
                reserved_ids.add(old_section.id)

    pages: List[Page] = []
    section_sources: Dict[str, List[Source]] = {}
    assigned_ids: Set[str] = set()
    for name in intake.pages:
        planned_page = planned_by_page.get(name)
        if planned_page is None:
            continue  # validation reports the missing requested page
        slug = PAGE_SLUGS[name]
        key = page_key(slug)
        sections: List[Section] = []
        for planned in planned_page.sections:
            reused = prev_queue.get((slug, planned.type), [])
            prev_section: Optional[Section] = reused.pop(0) if reused else None
            if prev_section is not None:
                section_id = prev_section.id
            else:
                n = 1
                while f"{planned.type}-{n}" in reserved_ids | assigned_ids:
                    n += 1
                section_id = f"{planned.type}-{n}"
            assigned_ids.add(section_id)
            sections.append(_build_section(planned.type, section_id, key, prev_section))
            section_sources[section_id] = list(from_intake(*planned.sources))
        if sections:
            pages.append(Page(slug=slug, sections=sections))

    # -- Features, data requirements, integrations ---------------------------
    features = list(intake.features)
    recipes: List[DataRecipe] = []
    for feature in features:
        recipe = FEATURE_DATA_RECIPES.get(feature)
        if recipe is not None and recipe not in recipes:
            recipes.append(recipe)
    data_requirements = [DataRequirement(recipe=r) for r in recipes]
    integrations = list(intake.integrations)

    # -- Flags ----------------------------------------------------------------
    flags: List[Flag] = []
    missing = missing_branding(intake)
    if missing:
        flags.append(DefaultDesignTrackFlag(code="default_design_track", missing=missing))
    # Figma generation is out of scope for this milestone slice (PRD §5 flag off).
    flags.append(NoFigmaFlag(code="no_figma", reason="figma_disabled"))

    # -- Decision log (D5): cover every part of the spec with its source -----
    log = _build_decisions(
        previous=previous,
        revision=revision,
        intake=intake,
        tokens=tokens,
        brand_roles=brand_roles,
        default_roles=default_roles,
        pages=pages,
        section_sources=section_sources,
        features=features,
        recipes=recipes,
        integrations=integrations,
        flags=flags,
        missing=missing,
    )

    spec = DesignSpec(
        job_id=job_id,
        tokens=tokens,
        pages=pages,
        features=features,
        data_requirements=data_requirements,
        integrations=integrations,
        flags=flags,
        decisions=log,
        figma_url=None,
    )
    return spec.model_dump(mode="json", by_alias=True)


def _build_section(section_type: str, section_id: str, key: str, prev_section: Optional[Section]) -> Section:
    """Content blocks come from the catalog's slot definitions (BUI-66).

    A surviving section keeps the block IDs it had for each slot; new slots
    get ``<page>.<section id>.<slot>``, which is unique across the spec.
    """
    sdef = get_section_def(section_type)
    if sdef is None:
        # Assemble something schema-shaped; validation rejects the unknown
        # type with a targeted issue so the retry can fix it.
        return Section(
            id=section_id,
            type=section_type,
            components=[],
            content_blocks=[ContentBlock(id=f"{key}.{section_id}.body", kind="body", max_chars=300)],
        )
    prev_block_ids: Dict[str, str] = {}
    if prev_section is not None:
        prev_block_ids = {block.id.rsplit(".", 1)[-1]: block.id for block in prev_section.content_blocks}
    blocks = [
        ContentBlock(
            id=prev_block_ids.get(slot.name, f"{key}.{section_id}.{slot.name}"),
            kind=slot.kind,
            max_chars=slot.max_chars,
        )
        for slot in sdef.slots
    ]
    return Section(id=section_id, type=section_type, components=list(sdef.components), content_blocks=blocks)


def _build_decisions(
    *,
    previous: Optional[DesignSpec],
    revision: int,
    intake: DesignIntake,
    tokens: Tokens,
    brand_roles: List[ColorRole],
    default_roles: List[ColorRole],
    pages: List[Page],
    section_sources: Dict[str, List[Source]],
    features: List[Feature],
    recipes: List[DataRecipe],
    integrations: Sequence[str],
    flags: List[Flag],
    missing: List[BrandingField],
) -> List[Decision]:
    """Append decisions until every part of the spec has a current one.

    Starts from the previous log (append-only, D5): decisions whose targets
    survive stay current and are not repeated; anything new or uncovered gets
    a decision citing its source.
    """
    log: List[Decision] = list(previous.decisions) if previous is not None else []

    exists = {f"tokens.colors.{role}" for role in tokens.colors}
    exists |= {"tokens.fonts.heading", "tokens.fonts.body", "tokens.radius"}
    for page in pages:
        exists.add(f"page:{page.slug}")
        exists |= {f"section:{s.id}" for s in page.sections}
    exists |= {f"feature:{f}" for f in features}
    exists |= {f"data_requirement:{r}" for r in recipes}
    exists |= {f"integration:{i}" for i in integrations}
    exists |= {flag_target(f) for f in flags}

    gone = superseded_ids(log)
    covered = set()
    for d in log:
        if d.id not in gone and all(t in exists for t in d.targets):
            covered.update(d.targets)

    def cover(kind: str, targets: List[str], sources: List[Source], method: str, **kwargs: Any) -> Optional[str]:
        nonlocal log
        if all(t in covered for t in targets):
            return None
        log = record_decision(
            log, kind=kind, targets=targets, sources=sources, method=method, revision=revision, **kwargs  # type: ignore[arg-type]
        )
        covered.update(targets)
        return log[-1].id

    if brand_roles:
        cover("token", [f"tokens.colors.{r}" for r in brand_roles], from_intake("brand_colors"), "code")
    cover("token", [f"tokens.colors.{r}" for r in default_roles], from_default("build_tokens"), "code")
    cover(
        "token",
        ["tokens.fonts.heading", "tokens.fonts.body"],
        from_intake("brand_fonts") if intake.brand_fonts else from_default("build_tokens"),
        "code",
    )

    # The radius is the model's reading of the visual style; on a rerun a
    # changed value supersedes the old decision instead of editing history.
    radius_supersedes: Optional[str] = None
    if previous is not None and previous.tokens.radius != tokens.radius:
        radius_supersedes = next(
            (d.id for d in log if d.id not in superseded_ids(log) and "tokens.radius" in d.targets),
            None,
        )
        covered.discard("tokens.radius")
    if "tokens.radius" not in covered:
        cover("token", ["tokens.radius"], from_intake("visual_style"), "llm", supersedes=radius_supersedes)

    cover("page", [f"page:{p.slug}" for p in pages], from_intake("pages"), "code")

    for page in pages:
        for section in page.sections:
            cover("section", [f"section:{section.id}"], section_sources[section.id], "llm")

    feature_decision_ids: Dict[Feature, str] = {}
    for feature in features:
        dec_id = cover("feature", [f"feature:{feature}"], from_intake("features"), "code")
        if dec_id is not None:
            feature_decision_ids[feature] = dec_id
    for recipe in recipes:
        caused_by = [
            feature_decision_ids[f]
            for f in features
            if FEATURE_DATA_RECIPES.get(f) == recipe and f in feature_decision_ids
        ]
        cover(
            "data_requirement",
            [f"data_requirement:{recipe}"],
            from_rule("feature_data_recipe"),
            "code",
            derived_from=caused_by,
        )
    for integration in integrations:
        cover("integration", [f"integration:{integration}"], from_intake("integrations"), "code")

    if missing:
        cover(
            "flag",
            ["flag:default_design_track"],
            from_intake(*missing) + from_default("default_design_track"),
            "code",
        )
    cover("flag", ["flag:no_figma"], from_config("figma_generation"), "code")

    # Record the "never say or do" constraint for the reviewer panel.
    if intake.content_exclusions:
        already = any(
            d.id not in superseded_ids(log)
            and any(isinstance(s, IntakeSource) and s.ref == "content_exclusions" for s in d.sources)
            for d in log
        )
        if not already:
            log = record_decision(
                log,
                kind="assumption",
                targets=["spec"],
                sources=from_intake("content_exclusions"),
                method="code",
                revision=revision,
                summary="The intake content exclusions were applied as a hard constraint on every generated design decision.",
            )

    return log


def requested_slugs(intake: DesignIntake) -> List[str]:
    """The slugs validation must find in the page map (one per requested page)."""
    return [PAGE_SLUGS[name] for name in intake.pages]


def content_block_index(spec: DesignSpec) -> Dict[str, ContentBlock]:
    """Stage 4 lookup: every content block in the spec, addressable by its ID.

    IDs are validated to be unique across the whole spec, so this never drops
    a block.
    """
    return {block.id: block for page in spec.pages for section in page.sections for block in section.content_blocks}
