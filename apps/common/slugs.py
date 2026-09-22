"""
Slug utilities.

assign_unique_slug() generates a URL-safe identifier from a source string.
The first slug is slugify(source). Collisions use {base}-{YYYYMMDD}-{letter}
(local date, no time) instead of -2, -3.
"""
from django.utils import timezone
from django.utils.text import slugify


def letter_suffix(index: int) -> str:
    """Map 1-based *index* to a, b, … z, aa, ab, …"""
    if index < 1:
        raise ValueError("letter suffix index must be >= 1")
    chars = []
    n = index
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("a") + rem))
    return "".join(reversed(chars))


def assign_unique_slug(instance, source: str) -> str:
    """
    Return a unique slug for *instance* derived from *source*.

    - Slugifies and lowercases *source*.
    - Falls back to "item" when the slugified result is empty.
    - On clash, appends -{YYYYMMDD}-{letter} using the local date (no time).
    - Excludes the instance's own pk so this function is safe on updates.
    """
    model = instance.__class__
    base = slugify(source).lower() or "item"
    slug = base
    suffix_index = 0
    date_part = timezone.localdate().strftime("%Y%m%d")
    while True:
        qs = model.objects.filter(slug=slug)
        if instance.pk:
            qs = qs.exclude(pk=instance.pk)
        if not qs.exists():
            return slug
        suffix_index += 1
        slug = f"{base}-{date_part}-{letter_suffix(suffix_index)}"
