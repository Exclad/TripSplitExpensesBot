from __future__ import annotations

BUILT_IN_CATEGORIES = ("Food", "Transit", "Stay", "Activities", "Shopping", "Misc")


def category_key(category: str) -> str:
    return " ".join(category.strip().lower().split())


def normalize_category(category: str, custom_categories: list[str] | tuple[str, ...] = ()) -> str:
    clean = category.strip().lower()
    for built_in in BUILT_IN_CATEGORIES:
        if clean == built_in.lower():
            return built_in
    clean_key = category_key(category)
    for custom in custom_categories:
        if clean_key == category_key(custom):
            return custom.strip()
    allowed = list(BUILT_IN_CATEGORIES) + [custom.strip() for custom in custom_categories]
    raise ValueError(f"Choose one of: {', '.join(allowed)}")


def validate_custom_category_name(name: str) -> str:
    clean = " ".join(name.strip().split())
    if not clean:
        raise ValueError("Enter a category name.")
    if len(clean) > 40:
        raise ValueError("Keep category names under 40 characters.")
    if category_key(clean) in {category_key(category) for category in BUILT_IN_CATEGORIES}:
        raise ValueError("That category already exists.")
    return clean
