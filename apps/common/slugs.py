"""
Slug utilities.

assign_unique_slug() generates a URL-safe identifier from a source string,
appending a numeric suffix (-2, -3, …) until the slug is unique on the
given model class.
"""
from django.utils.text import slugify


def assign_unique_slug(instance, source: str) -> str:
    """
    Return a unique slug for *instance* derived from *source*.

    - Slugifies and lowercases *source*.
    - Falls back to "item" when the slugified result is empty.
    - Appends -2, -3, … until unique.
    - Excludes the instance's own pk so this function is safe on updates.
    """
    Model = instance.__class__
    base = slugify(source).lower() or "item"
    slug = base
    counter = 2
    while True:
        qs = Model.objects.filter(slug=slug)
        if instance.pk:
            qs = qs.exclude(pk=instance.pk)
        if not qs.exists():
            break
        slug = f"{base}-{counter}"
        counter += 1
    return slug
