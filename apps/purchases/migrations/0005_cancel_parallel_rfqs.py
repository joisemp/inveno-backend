"""Cancel older parallel RFQs so each PR keeps only its newest active RFQ."""

from django.db import migrations
from django.db.models import Count


def cancel_older_parallel_rfqs(apps, schema_editor):
    """Keep newest non-cancelled RFQ per PR; set older siblings to cancelled."""
    QuoteRequest = apps.get_model("purchases", "QuoteRequest")
    cancelled = "cancelled"
    duplicates = (
        QuoteRequest.objects.exclude(status=cancelled)
        .values("purchase_request_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for row in duplicates:
        qs = list(
            QuoteRequest.objects.filter(
                purchase_request_id=row["purchase_request_id"],
            )
            .exclude(status=cancelled)
            .order_by("-created_at", "-id")
        )
        # Keep index 0 (newest); cancel the rest
        for rfq in qs[1:]:
            rfq.status = cancelled
            rfq.save(update_fields=["status", "updated_at"])


def noop_reverse(apps, schema_editor):
    """Cannot restore which RFQs were cancelled by this migration."""


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0004_purchaserequestlineaward"),
    ]

    operations = [
        migrations.RunPython(cancel_older_parallel_rfqs, noop_reverse),
    ]
