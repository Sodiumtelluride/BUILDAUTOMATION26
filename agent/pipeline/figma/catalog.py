"""
The shadcn/ui components we can recognize in a Figma file.
Each key is the component's shadcn name (what you pass to `npx shadcn add`).
Each value lists names a designer might give that component in Figma.
"""

from __future__ import annotations

import re

# shadcn component -> names it might have in Figma (lowercase)
SHADCN_COMPONENTS: dict[str, list[str]] = {
    "accordion": ["accordion", "faq"],
    "alert": ["alert", "banner", "callout"],
    "avatar": ["avatar", "profile picture", "avatar group"],
    "badge": ["badge", "chip", "tag", "pill"],
    "breadcrumb": ["breadcrumb", "breadcrumbs"],
    "button": ["button", "btn", "cta"],
    "calendar": ["calendar", "date picker"],
    # Card parts (CardHeader, CardFooter, ...) count as the card itself
    "card": ["card", "card header", "card footer", "card content", "card title", "card description"],
    "carousel": ["carousel", "slideshow"],
    "checkbox": ["checkbox"],
    "dialog": ["dialog", "modal", "popup"],
    "dropdown-menu": ["dropdown menu"],
    "input": ["input", "text field", "text input", "search bar"],
    "label": ["label"],
    "navigation-menu": ["navigation menu", "navbar", "nav bar", "navigation"],
    "pagination": ["pagination"],
    "progress": ["progress", "progress bar"],
    "radio-group": ["radio group", "radio"],
    "select": ["select", "dropdown"],
    "separator": ["separator", "divider"],
    "sheet": ["sheet", "side panel", "mobile menu"],
    "skeleton": ["skeleton"],
    "slider": ["slider"],
    "sonner": ["sonner", "toast"],
    "switch": ["switch"],
    "table": ["table", "data table"],
    "tabs": ["tabs"],
    "textarea": ["textarea", "text area"],
    "toggle": ["toggle"],
    "tooltip": ["tooltip"],
}

# Components that can hold other components, so we keep looking inside them.
# (Everything else, like a Button, is not searched inside: its text isn't a component.)
CONTAINERS = {"accordion", "card", "carousel", "dialog", "navigation-menu", "sheet", "table", "tabs"}


def find_component(figma_name: str) -> str | None:
    """
    Return the shadcn component for a Figma name, or None if there's no match.

    Examples: "Button" -> "button", "Button/Primary" -> "button",
    "❖ Navbar" -> "navigation-menu", "CardHeader" -> "card", "Frame 12" -> None.
    """
    # Figma groups variants with slashes ("Button/Primary"), so use the first part
    first_part = figma_name.split("/")[0]
    # split CamelCase into words ("CardHeader" -> "Card Header")
    first_part = re.sub(r"([a-z])([A-Z])", r"\1 \2", first_part)
    # lowercase and turn symbols/punctuation into spaces ("❖ Nav-Bar" -> "nav bar")
    cleaned = " ".join(re.sub(r"[^a-z0-9]+", " ", first_part.lower()).split())
    for component, names in SHADCN_COMPONENTS.items():
        if cleaned in names:
            return component
    return None
