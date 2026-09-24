"""Spaces media storage location and ACL defaults."""
from apps.common.storages import MediaStorage


def test_media_storage_is_private_under_media():
    assert MediaStorage.location == "media"
    assert MediaStorage.default_acl == "private"
