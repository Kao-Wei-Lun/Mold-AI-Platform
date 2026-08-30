import io
import json
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from openpyxl import Workbook

from platform_core.identity import ensure_account_profile
from platform_core.models import AccessRole, DataScope, MasterDataItem, RoleAssignment


@override_settings(DEMO_AUTH_MODE="local")
class MasterDataIngestionAdapterTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.scope = DataScope.objects.get(code="public-demo")
        self.user = get_user_model().objects.create_user(
            username="reference-importer", password="Reference-Import-2026!"
        )
        ensure_account_profile(self.user)
        role = AccessRole.objects.get(code="platform_admin")
        RoleAssignment.objects.create(
            user=self.user,
            role=role,
            data_scope=self.scope,
            granted_by=self.user,
            reason="Reference data adapter test",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def _create_and_upload(self, name: str, content: bytes, content_type: str):
        batch = self.client.post(
            "/api/v1/ingestions",
            data=json.dumps(
                {
                    "scope": "public-demo",
                    "domain": "master_data",
                    "source_name": name,
                    "idempotency_key": f"reference-{name}",
                }
            ),
            content_type="application/json",
        ).json()
        return self.client.post(
            f"/api/v1/ingestions/{batch['batch_id']}/files",
            {"file": SimpleUploadedFile(name, content, content_type=content_type)},
        )

    def test_csv_json_and_xlsx_are_normalized_by_one_adapter(self):
        csv_response = self._create_and_upload(
            "materials.csv",
            b"kind,code,name_en,name_zh_tw\nmaterial,FMT-CSV,CSV Material,CSV Material\n",
            "text/csv",
        )
        json_response = self._create_and_upload(
            "materials.json",
            json.dumps(
                [
                    {
                        "kind": "material",
                        "code": "FMT-JSON",
                        "name_en": "JSON Material",
                        "name_zh_tw": "JSON Material",
                    }
                ]
            ).encode(),
            "application/json",
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["kind", "code", "name_en", "name_zh_tw"])
        sheet.append(["material", "FMT-XLSX", "XLSX Material", "XLSX Material"])
        stream = io.BytesIO()
        workbook.save(stream)
        xlsx_response = self._create_and_upload(
            "materials.xlsx",
            stream.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        for response in (csv_response, json_response, xlsx_response):
            self.assertEqual(response.status_code, 201)
            batch_id = response.json()["batch_id"]
            validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")
            self.assertEqual(validated.status_code, 200)
            self.assertTrue(validated.json()["validation"]["valid"])
        self.assertFalse(
            MasterDataItem.objects.filter(code__in=["FMT-CSV", "FMT-JSON", "FMT-XLSX"]).exists()
        )

    def test_invalid_canonical_kind_is_a_row_level_blocking_issue(self):
        uploaded = self._create_and_upload(
            "invalid.json",
            b'[{"kind":"unknown-kind","code":"BAD","name_en":"Bad"}]',
            "application/json",
        )
        batch_id = uploaded.json()["batch_id"]
        validated = self.client.post(f"/api/v1/ingestions/{batch_id}/validate")

        self.assertFalse(validated.json()["validation"]["valid"])
        self.assertEqual(validated.json()["issues"][0]["code"], "INVALID_KIND")
        self.assertFalse(MasterDataItem.objects.filter(code="BAD").exists())

    def test_versioned_template_is_downloadable(self):
        response = self.client.get("/api/v1/import-templates/master_data")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Schema-Version"], "1.0")
        self.assertIn("kind,code,name_en,name_zh_tw", response.content.decode())
