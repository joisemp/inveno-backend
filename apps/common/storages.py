"""
DigitalOcean Spaces backends used in production.

Static files are public (admin, Swagger). Media stays private and is only
streamed through authenticated API views.
"""
from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    """Collectstatic target: public objects under static/, no manifest hashing."""

    location = "static"
    default_acl = "public-read"


class MediaStorage(S3Boto3Storage):
    """User uploads under media/. ACL is private; do not put a CDN custom_domain."""

    location = "media"
    default_acl = "private"
