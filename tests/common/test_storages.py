"""Spaces storage class location and ACL defaults."""
from apps.common.storages import MediaStorage, StaticStorage


def test_static_storage_is_public_under_static():
    assert StaticStorage.location == "static"
    assert StaticStorage.default_acl == "public-read"


def test_media_storage_is_private_under_media():
    assert MediaStorage.location == "media"
    assert MediaStorage.default_acl == "private"
