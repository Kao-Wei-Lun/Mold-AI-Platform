from django.core.management.base import BaseCommand

from platform_core.master_data import seed_master_data


class Command(BaseCommand):
    help = "Idempotently seed the governed public Demo master-data catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        created, updated = seed_master_data(dry_run=options["dry_run"])
        mode = "would create/update" if options["dry_run"] else "created/updated"
        self.stdout.write(self.style.SUCCESS(f"Master data {mode}: {created}/{updated}"))
