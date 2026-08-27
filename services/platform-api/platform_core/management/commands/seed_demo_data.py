from django.core.management.base import BaseCommand

from platform_core.cae_connectors import seed_demo_cae_studies
from platform_core.knowledge_fixtures import seed_demo_knowledge
from platform_core.process_connectors import seed_demo_process_trials


class Command(BaseCommand):
    help = "Idempotently load the governed public Demo datasets used by Web and MCP flows."

    def handle(self, *args, **options) -> None:
        knowledge = seed_demo_knowledge()
        process = seed_demo_process_trials()
        cae = seed_demo_cae_studies()
        self.stdout.write(
            self.style.SUCCESS(
                "Demo data ready: "
                f"knowledge={knowledge.indexed}, "
                f"process={process.created + process.existing}, "
                f"cae={cae.created + cae.existing}, "
                f"relabeled_smoke={knowledge.relabeled_smoke_documents}"
            )
        )
