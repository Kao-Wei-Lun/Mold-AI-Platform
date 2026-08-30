from __future__ import annotations

import json
import math
import time

from django.core.management.base import BaseCommand, CommandError

from platform_core.history_views import _analysis_rows
from platform_core.models import Job, Project
from platform_core.process_trial import trial_case_queryset


class Command(BaseCommand):
    help = "Measure representative read-only historical data queries against the current database."

    def add_arguments(self, parser):
        parser.add_argument("--iterations", type=int, default=20)
        parser.add_argument("--budget-ms", type=float, default=800.0)

    def handle(self, *args, **options):
        iterations = max(5, min(200, options["iterations"]))
        budget_ms = options["budget_ms"]
        probes = {
            "registry_page": lambda: list(
                Project.objects.select_related("scope").order_by("code")[:25]
            ),
            "trial_page": lambda: list(trial_case_queryset().order_by("case_code")[:25]),
            "job_page": lambda: list(
                Job.objects.select_related("input_artifact_version").order_by("-created_at")[:25]
            ),
            "analysis_index": _analysis_rows,
        }
        results: dict[str, dict[str, float]] = {}
        failed: list[str] = []
        for name, probe in probes.items():
            samples = []
            for _ in range(iterations):
                started = time.perf_counter()
                probe()
                samples.append((time.perf_counter() - started) * 1000)
            samples.sort()
            p95 = samples[max(0, math.ceil(len(samples) * 0.95) - 1)]
            results[name] = {
                "p50_ms": round(samples[len(samples) // 2], 3),
                "p95_ms": round(p95, 3),
                "budget_ms": budget_ms,
            }
            if p95 > budget_ms:
                failed.append(name)
        payload = {
            "schema_version": "history-performance-v1",
            "iterations": iterations,
            "results": results,
            "passed": not failed,
            "failed_probes": failed,
            "note": (
                "ORM smoke budget; validate end-to-end p95 with production-sized data "
                "before cutover."
            ),
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        if failed:
            raise CommandError(f"History performance budget exceeded: {', '.join(failed)}")
