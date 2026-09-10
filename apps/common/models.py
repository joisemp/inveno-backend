"""
Abstract base models shared across all domain apps.

UUIDModel  — provides a UUID primary key (all new models inherit this).
SlugMixin  — auto-generates a unique slug on first save.
             Subclasses override get_slug_source() to control the source string.

Convention: User is the only model exempt from SlugMixin.
"""
import uuid

from django.db import models

from apps.common.slugs import assign_unique_slug


class UUIDModel(models.Model):
    """Abstract model providing a UUID primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class SlugMixin(models.Model):
    """
    Abstract mixin that adds an auto-generated unique slug field.

    On first save, if slug is blank, get_slug_source() is called to get the
    string to slugify.  The slug is stable once set — it is NOT rewritten
    when the source field changes.

    Subclasses that need custom logic should override get_slug_source().
    """

    slug = models.SlugField(max_length=255, unique=True, db_index=True, blank=True)

    class Meta:
        abstract = True

    def get_slug_source(self) -> str:
        """Return the string to derive the slug from. Override in subclasses."""
        return ""

    def save(self, *args, **kwargs):
        if not self.slug:
            source = self.get_slug_source()
            if source:
                self.slug = assign_unique_slug(self, source)
        super().save(*args, **kwargs)
