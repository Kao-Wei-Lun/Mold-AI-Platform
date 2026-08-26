from django.test import SimpleTestCase

from platform_core.tasks import echo


class TaskTests(SimpleTestCase):
    def test_echo_task_preserves_json_payload(self) -> None:
        payload = {"message": "worker-ready", "count": 1}

        self.assertEqual(echo.run(payload), payload)
