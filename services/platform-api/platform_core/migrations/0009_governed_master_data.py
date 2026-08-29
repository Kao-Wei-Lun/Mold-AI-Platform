import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower

SEED = (
    ("dataset", "public-demo-v1", "Public Demo", "公開 Demo", 10, {}),
    ("dataset", "curated-cad-demo-v1", "Curated CAD Demo", "精選 CAD Demo", 20, {}),
    (
        "dataset",
        "manual-cad-upload-v1",
        "Manual CAD uploads",
        "手動 CAD 上傳",
        30,
        {"purpose": "cad_upload", "default": True},
    ),
    ("product_type", "housing", "Housing", "外殼", 10, {}),
    ("product_type", "connector_housing", "Connector housing", "連接器外殼", 20, {}),
    ("product_type", "electronics_cover", "Electronics cover", "電子產品上蓋", 30, {}),
    ("product_type", "thin_wall_tray", "Thin-wall tray", "薄壁托盤", 40, {}),
    ("material", "PA6-GF30", "PA6 GF30", "PA6 玻纖 30%", 10, {"family": "PA6", "grade": "GF30"}),
    ("material", "ABS-GENERAL", "General ABS", "通用 ABS", 20, {"family": "ABS"}),
    ("material", "PP-HOMO", "PP homopolymer", "PP 均聚物", 30, {"family": "PP"}),
    ("material", "PC_ABS", "PC/ABS", "PC/ABS 合金", 40, {"family": "PC/ABS"}),
    ("machine", "IM-120T", "Injection machine 120T", "120 噸射出機", 10, {"tonnage": 120}),
    ("machine", "IM-180T", "Injection machine 180T", "180 噸射出機", 20, {"tonnage": 180}),
    ("machine", "IM-220T", "Injection machine 220T", "220 噸射出機", 30, {"tonnage": 220}),
    (
        "defect",
        "short_shot",
        "Short shot",
        "短射",
        10,
        {"default_severity": "major", "inspection_method": "visual"},
    ),
    (
        "defect",
        "sink_mark",
        "Sink mark",
        "縮痕",
        20,
        {"default_severity": "major", "inspection_method": "visual"},
    ),
    (
        "defect",
        "warpage",
        "Warpage",
        "翹曲",
        30,
        {"default_severity": "major", "inspection_method": "fixture"},
    ),
    (
        "defect",
        "flash",
        "Flash",
        "毛邊",
        40,
        {"default_severity": "minor", "inspection_method": "visual"},
    ),
    ("location", "far_flow_end", "Far flow end", "流動末端", 10, {}),
    ("location", "gate_area", "Gate area", "澆口區", 20, {}),
    ("location", "core_side", "Core side", "公模側", 30, {}),
    ("location", "cavity_side", "Cavity side", "母模側", 40, {}),
    ("location", "parting_line", "Parting line", "分模線", 50, {}),
    ("unit", "mm", "Millimetre", "毫米", 10, {"dimension": "length", "symbol": "mm"}),
    ("unit", "MPa", "Megapascal", "百萬帕", 20, {"dimension": "pressure", "symbol": "MPa"}),
    ("unit", "degC", "Degree Celsius", "攝氏度", 30, {"dimension": "temperature", "symbol": "°C"}),
    ("unit", "s", "Second", "秒", 40, {"dimension": "time", "symbol": "s"}),
)


def seed_master_data(apps, schema_editor):
    AccessRole = apps.get_model("platform_core", "AccessRole")
    DataScope = apps.get_model("platform_core", "DataScope")
    MasterDataItem = apps.get_model("platform_core", "MasterDataItem")
    scope = DataScope.objects.get(code="public-demo")
    for kind, code, name_en, name_zh_tw, sort_order, attributes in SEED:
        MasterDataItem.objects.get_or_create(
            scope=scope,
            kind=kind,
            code=code,
            defaults={
                "name_en": name_en,
                "name_zh_tw": name_zh_tw,
                "sort_order": sort_order,
                "attributes": attributes,
                "source_system": "public_demo_seed",
                "source_refs": ["phase-2:canonical-master-data"],
                "classification": "public_demo",
                "created_by": "system:migration",
                "updated_by": "system:migration",
            },
        )
    for role in AccessRole.objects.all():
        permissions = list(role.permissions)
        if "master-data:read" not in permissions:
            permissions.append("master-data:read")
        if (
            role.code in {"data_steward", "platform_admin"}
            and "master-data:manage" not in permissions
        ):
            permissions.append("master-data:manage")
        role.permissions = permissions
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0008_identity_foundation")]

    operations = [
        migrations.CreateModel(
            name="MasterDataItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("dataset", "Dataset"),
                            ("product_type", "Product type"),
                            ("material", "Material"),
                            ("machine", "Machine"),
                            ("defect", "Defect"),
                            ("location", "Location"),
                            ("unit", "Unit"),
                        ],
                        max_length=32,
                    ),
                ),
                ("code", models.CharField(max_length=128)),
                ("name_en", models.CharField(max_length=255)),
                ("name_zh_tw", models.CharField(max_length=255)),
                ("description_en", models.TextField(blank=True)),
                ("description_zh_tw", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("inactive", "Inactive"),
                            ("archived", "Archived"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=100)),
                ("attributes", models.JSONField(blank=True, default=dict)),
                ("aliases", models.JSONField(blank=True, default=list)),
                ("source_system", models.CharField(default="platform_demo", max_length=64)),
                ("source_refs", models.JSONField(blank=True, default=list)),
                ("classification", models.CharField(default="public_demo", max_length=32)),
                ("effective_from", models.DateField(blank=True, null=True)),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("row_version", models.PositiveIntegerField(default=1)),
                ("created_by", models.CharField(max_length=128)),
                ("updated_by", models.CharField(max_length=128)),
                ("archive_reason", models.CharField(blank=True, max_length=512)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="master_data_items",
                        to="platform_core.datascope",
                    ),
                ),
            ],
            options={"ordering": ["kind", "sort_order", "code"]},
        ),
        migrations.AddConstraint(
            model_name="masterdataitem",
            constraint=models.UniqueConstraint(
                Lower("code"), "scope", "kind", name="unique_master_data_scope_kind_code"
            ),
        ),
        migrations.AddIndex(
            model_name="masterdataitem",
            index=models.Index(
                fields=["scope", "kind", "status"], name="master_scope_kind_status_idx"
            ),
        ),
        migrations.RunPython(seed_master_data, migrations.RunPython.noop),
    ]
