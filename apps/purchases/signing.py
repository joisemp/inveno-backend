"""Hash-chain + HMAC signatures for purchase-flow process events."""
import hashlib
import hmac
import json

from django.conf import settings
from django.utils import timezone

from apps.purchases.models import ProcessEvent

GENESIS_HASH = "genesis"


def _canonical(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def sign_content_hash(content_hash: str) -> str:
    """HMAC-SHA256 of a content hash using PROCESS_SIGNING_KEY."""
    key = settings.PROCESS_SIGNING_KEY.encode("utf-8")
    return hmac.new(key, content_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(*, content_hash: str, signature: str) -> bool:
    """Return True when *signature* matches HMAC(content_hash)."""
    expected = sign_content_hash(content_hash)
    return hmac.compare_digest(expected, signature)


def record_process_event(
    *,
    org,
    purchase_request,
    resource_type: str,
    resource_slug: str,
    action: str,
    actor,
    payload: dict,
) -> ProcessEvent:
    """
    Append an immutable signed event for a purchase-flow movement.

    Must run in the same atomic transaction as the domain write.
    """
    prev = (
        ProcessEvent.objects.filter(purchase_request=purchase_request)
        .order_by("-created_at")
        .first()
        if purchase_request is not None
        else None
    )
    prev_hash = prev.content_hash if prev else GENESIS_HASH
    created_at = timezone.now().isoformat()
    body = {
        "action": action,
        "actor_slug": actor.slug,
        "resource_type": resource_type,
        "resource_slug": resource_slug,
        "payload": payload,
        "created_at": created_at,
        "prev_hash": prev_hash,
    }
    content_hash = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    event = ProcessEvent(
        org=org,
        purchase_request=purchase_request,
        resource_type=resource_type,
        resource_slug=resource_slug,
        action=action,
        actor_slug=actor.slug,
        actor_user_type=actor.user_type,
        payload=payload,
        prev_hash=prev_hash,
        content_hash=content_hash,
        signature=sign_content_hash(content_hash),
    )
    event.save()
    return event
