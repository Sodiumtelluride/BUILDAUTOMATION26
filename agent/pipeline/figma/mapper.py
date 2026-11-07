"""
Lists the shadcn/ui components a Figma design uses, per screen size.

How it works:
  1. Each top-level frame on a Figma page is one screen (e.g. "Home – Desktop").
  2. The frame's width tells us if it's the desktop, tablet, or mobile version.
  3. Every layer inside the frame is matched to a shadcn component: first by the
     Figma component it's an instance of, then by the layer's own name.

Run it (from the agent/ folder):
  .venv/bin/python -m pipeline.figma.mapper <figma-url or file.json> --page Screens --out report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from pipeline.figma.catalog import CONTAINERS, find_component
from pipeline.figma.client import load_figma_file

# agent/.env -- holds FIGMA_TOKEN (ignored by git)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Display order for the screen sizes
VIEWPORTS = ["desktop", "tablet", "mobile"]

# Instances whose names contain these words are decoration, not components to review
IGNORED_WORDS = ("icon", "lucide")


def get_viewport(width: float) -> str:
    """Name the screen size from a frame's width (BUILD designs use 1440, 768, and 390/375)."""
    if width >= 1024:
        return "desktop"
    if width >= 600:
        return "tablet"
    return "mobile"


def get_screen_name(frame_name: str) -> str:
    """Drop size words so "Home – Desktop" and "Home / Mobile 375" both become "Home"."""
    name = re.sub(r"(?i)\b(desktop|mobile|tablet|iphone\s*\d*|phone|\d+\s*px|\d{3,4})\b", " ", frame_name)
    name = re.sub(r"[\s\-–—/|()]+", " ", name).strip()  # clean up leftover dashes and slashes
    return name or frame_name


def find_screens(document: dict[str, Any], page_names: list[str]) -> list[dict[str, Any]]:
    """
    Return every screen (top-level frame) in the file.

    page_names limits the search to those Figma pages (lowercase); empty means all pages.
    Component definitions on the kit's own pages are not frames, so they're skipped.
    """
    screens: list[dict[str, Any]] = []
    for page in document.get("children", []):  # the document's children are Figma pages
        if page_names and page["name"].lower() not in page_names:
            continue
        for node in page.get("children", []):
            if node["type"] == "FRAME":
                screens.append(node)
            elif node["type"] == "SECTION":  # a section is just a box around frames
                screens.extend(child for child in node.get("children", []) if child["type"] == "FRAME")
    return screens


def get_instance_name(node: dict[str, Any], figma_file: dict[str, Any]) -> str | None:
    """
    For a component instance, return the name of the Figma component it comes from.
    Variants (e.g. "Variant=Outline, Size=sm") belong to a component set named
    like "Button", so the set's name is returned when there is one.
    """
    component = figma_file.get("components", {}).get(node.get("componentId", ""))
    if component is None:
        return None
    component_set = figma_file.get("componentSets", {}).get(component.get("componentSetId", ""))
    if component_set is not None:
        return str(component_set["name"])
    return str(component["name"])


def find_components_in(
    node: dict[str, Any],
    figma_file: dict[str, Any],
    path: str,
    matches: list[dict[str, str]],
    needs_review: list[str],
) -> None:
    """
    Walk a layer and everything inside it, recording each shadcn component found.
    matches gets {"component", "layer", "matched_by"} for every hit.
    needs_review gets the names of component instances we couldn't map.
    """
    if node.get("visible") is False:  # hidden layers aren't part of the design
        return

    component = None
    matched_by = ""
    source_name = None

    # 1) Instance of a kit component? Use that component's name (most reliable).
    if node["type"] == "INSTANCE":
        source_name = get_instance_name(node, figma_file)
        if source_name:
            component = find_component(source_name)
            matched_by = "component"

    # 2) Otherwise, try the layer's own name (e.g. a frame renamed "Divider").
    if component is None and node["type"] in ("INSTANCE", "FRAME", "GROUP", "RECTANGLE"):
        component = find_component(node["name"])
        matched_by = "layer name"

    if component:
        matches.append({"component": component, "layer": path, "matched_by": matched_by})
        if component not in CONTAINERS:
            return  # don't look inside a Button: its text and icon aren't components
    elif node["type"] == "INSTANCE":
        name = source_name or node["name"]
        if not any(word in name.lower() for word in IGNORED_WORDS):
            needs_review.append(name)

    for child in node.get("children", []):
        find_components_in(child, figma_file, f"{path} > {child['name']}", matches, needs_review)


def map_design(figma_file: dict[str, Any], page_names: list[str] | None = None) -> dict[str, Any]:
    """Build the report: for each screen, the shadcn components used at each screen size."""
    screens: dict[str, dict[str, Any]] = {}

    for frame in find_screens(figma_file["document"], page_names or []):
        width = frame["absoluteBoundingBox"]["width"]
        viewport = get_viewport(width)
        name = get_screen_name(frame["name"])
        if viewport in screens.get(name, {}):  # same name and size twice: keep both
            name = frame["name"]

        matches: list[dict[str, str]] = []
        needs_review: list[str] = []
        for child in frame.get("children", []):
            find_components_in(child, figma_file, f"{frame['name']} > {child['name']}", matches, needs_review)

        screens.setdefault(name, {})[viewport] = {
            "frame": frame["name"],
            "width": width,
            "components": sorted({m["component"] for m in matches}),
            "matches": matches,
            "needs_review": sorted(set(needs_review)),
        }

    all_components = sorted(
        {c for versions in screens.values() for version in versions.values() for c in version["components"]}
    )
    return {
        "file_name": figma_file.get("name", ""),
        "screens": screens,
        "all_components": all_components,
        "install_command": f"npx shadcn@latest add {' '.join(all_components)}" if all_components else "",
    }


def print_report(report: dict[str, Any]) -> None:
    """Print the report as a short, readable summary."""
    print(f"\nFigma file: {report['file_name']}")
    for screen_name, versions in report["screens"].items():
        print(f"\n{screen_name}")
        for viewport in VIEWPORTS:
            if viewport not in versions:
                continue
            version = versions[viewport]
            components = ", ".join(version["components"]) or "(none found)"
            print(f"  {viewport:<8} {version['width']:>5.0f}px  {components}")
            if version["needs_review"]:
                print(f"  {'':<16}needs review: {', '.join(version['needs_review'])}")
    print(f"\nAll components: {', '.join(report['all_components']) or '(none)'}")
    if report["install_command"]:
        print(f"Install with:   {report['install_command']}")


def main() -> None:
    """Command-line entry point. Run with --help to see the options."""
    parser = argparse.ArgumentParser(description="List the shadcn/ui components used in a Figma design.")
    parser.add_argument("source", help="Figma file URL, or a saved Figma .json file")
    parser.add_argument("--page", action="append", default=[], help="only read this Figma page (can repeat)")
    parser.add_argument("--out", help="also save the full report as JSON to this file")
    parser.add_argument("--refresh", action="store_true", help="download again even if a cached copy exists")
    args = parser.parse_args()

    load_dotenv(ENV_FILE)  # makes FIGMA_TOKEN from agent/.env available
    try:
        figma_file = load_figma_file(args.source, refresh=args.refresh)
    except (RuntimeError, ValueError, OSError) as error:
        sys.exit(f"Error: {error}")

    report = map_design(figma_file, [page.lower() for page in args.page])
    print_report(report)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"Saved full report to {args.out}")


if __name__ == "__main__":
    main()
