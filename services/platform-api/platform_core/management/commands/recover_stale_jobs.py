import json

from django.core.management.base import BaseCommand, CommandError

from platform_core.job_recovery import recover_stale_jobs


class Command(BaseCommand):
    help = "Preview or recover stale queued/running Demo jobs using the bounded recovery policy."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--stale-minutes", type=int, default=15)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirmation", default="")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options) -> None:
        stale_minutes = options["stale_minutes"]
        limit = options["limit"]
        if not 1 <= stale_minutes <= 1440:
            raise CommandError("--stale-minutes must be between 1 and 1440.")
        if not 1 <= limit <= 1000:
            raise CommandError("--limit must be between 1 and 1000.")
        if options["apply"] and options["confirmation"] != "RECOVER STALE JOBS":
            raise CommandError('Applying recovery requires --confirmation "RECOVER STALE JOBS".')

        result = recover_stale_jobs(
            stale_minutes=stale_minutes,
            limit=limit,
            apply=options["apply"],
        )
        if options["json"]:
            self.stdout.write(json.dumps(result, sort_keys=True))
            return
        mode = "APPLIED" if options["apply"] else "DRY RUN"
        self.stdout.write(
            f"Stale job recovery {mode}: candidates={result['counts']['total']}, "
            f"queued={result['counts']['queued']}, running={result['counts']['running']}, "
            f"requeued={result['actions']['requeued']}, failed={result['actions']['failed']}"
        )
