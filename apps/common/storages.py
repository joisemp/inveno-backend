"""
DigitalOcean Spaces backend for production media.

Uploads stay private and are only streamed through authenticated API views.
Admin and Swagger static files are served by WhiteNoise, not this module.
"""
from storages.backends.s3boto3 import S3Boto3Storage


class MediaStorage(S3Boto3Storage):
    """User uploads under media/. ACL is private; do not set a CDN custom_domain."""

    location = "media"
    default_acl = "private"
