from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class HistoryPerformanceSmokeTests(TestCase):
    def test_read_only_history_probes_emit_machine_readable_p95(self):
        output = StringIO()
        call_command(
            "history_performance_smoke",
            iterations=5,
            budget_ms=5000,
            stdout=output,
        )
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["schema_version"], "history-performance-v1")
        self.assertIn("analysis_index", payload["results"])
