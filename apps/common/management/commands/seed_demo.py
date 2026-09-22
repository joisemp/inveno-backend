"""
Seed a development demo org after migrate.

First boot creates data. If the demo org already exists, pause on a TTY and
ask whether to keep it or wipe and recreate. Non-TTY keeps existing data.
"""
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.demo import (
    DEMO_ORG_SUFFIX,
    format_demo_logins,
    get_demo_org,
    seed_demo,
    wipe_demo,
)

_WIPE_HINT = (
    "No TTY — keeping existing demo data. Wipe with:\n"
    "  docker compose exec -it api python manage.py seed_demo --reset"
)


class Command(BaseCommand):
    """Create or refresh the development demo organisation."""

    help = (
        "Seed the demo org (development only). Prompts keep vs wipe when "
        "demo data already exists and stdin is a TTY."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--keep",
            action="store_true",
            help="Leave existing demo data as-is (seed only if missing).",
        )
        group.add_argument(
            "--reset",
            action="store_true",
            help="Wipe the demo org and recreate it (no prompt).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stdout.write("Skipping demo seed (DEBUG is False).")
            return
        if not getattr(settings, "SEED_DEMO", False):
            self.stdout.write("Skipping demo seed (SEED_DEMO is False).")
            return

        org = get_demo_org()
        if options["reset"]:
            wipe_demo()
            seed_demo()
            self.stdout.write(self.style.SUCCESS(format_demo_logins()))
            return

        if org is None:
            seed_demo()
            self.stdout.write(self.style.SUCCESS(format_demo_logins()))
            return

        if options["keep"] or not self._should_prompt():
            if not options["keep"]:
                self.stdout.write(_WIPE_HINT)
            self.stdout.write(f'Keeping existing demo data (org "{DEMO_ORG_SUFFIX}").')
            return

        if self._ask_wipe():
            wipe_demo()
            seed_demo()
            self.stdout.write(self.style.SUCCESS(format_demo_logins()))
            return

        self.stdout.write(f'Keeping existing demo data (org "{DEMO_ORG_SUFFIX}").')

    def _should_prompt(self) -> bool:
        if "pytest" in sys.modules:
            return False
        return bool(sys.stdin and sys.stdin.isatty())

    def _ask_wipe(self) -> bool:
        self.stdout.write(
            f'\nDemo data already exists (org "{DEMO_ORG_SUFFIX}").\n'
            "  [k] Keep existing data\n"
            "  [w] Wipe demo org and recreate\n"
        )
        raw = input("Choice [k/w]: ").strip().lower()
        return raw in {"w", "wipe"}
