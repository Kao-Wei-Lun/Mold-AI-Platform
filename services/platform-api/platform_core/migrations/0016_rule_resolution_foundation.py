import hashlib
import json
import uuid

import django.db.models.deletion
from django.db import migrations, models


REFERENCE_DATA_SEED = (
    (
        "mold_type",
        "injection",
        "General injection mold",
        "一般射出模具",
        10,
        {"process_family": "injection"},
    ),
    (
        "mold_type",
        "two_plate",
        "Two-plate mold",
        "二板模",
        20,
        {"process_family": "injection", "plate_count": 2},
    ),
    (
        "mold_type",
        "three_plate",
        "Three-plate mold",
        "三板模",
        30,
        {"process_family": "injection", "plate_count": 3},
    ),
    (
        "mold_type",
        "hot_runner",
        "Hot-runner mold",
        "熱澆道模具",
        40,
        {"process_family": "injection", "hot_runner": True},
    ),
    (
        "mold_type",
        "insert_overmolding",
        "Insert / overmolding mold",
        "埋入／包覆成型模具",
        50,
        {"process_family": "overmolding"},
    ),
    (
        "mold_type",
        "unscrewing",
        "Unscrewing mold",
        "旋牙／退牙模具",
        60,
        {"process_family": "injection", "unscrewing": True},
    ),
    (
        "mold_type",
        "multi_cavity",
        "Multi-cavity mold",
        "多穴模具",
        70,
        {"process_family": "injection", "multi_cavity": True},
    ),
    (
        "mold_type",
        "family_mold",
        "Family mold",
        "共模／Family Mold",
        80,
        {"process_family": "injection", "family_mold": True},
    ),
    (
        "molding_process",
        "injection",
        "Injection molding",
        "射出成型",
        10,
        {},
    ),
    (
        "molding_process",
        "compression",
        "Compression molding",
        "壓縮成型",
        20,
        {},
    ),
    (
        "molding_process",
        "overmolding",
        "Insert / overmolding",
        "埋入／包覆成型",
        30,
        {},
    ),
    ("rule_category", "mold_design", "Mold design", "模具設計", 10, {}),
    ("rule_category", "product_design", "Product design", "產品設計", 20, {}),
    ("rule_category", "material", "Material", "材料", 30, {}),
    ("rule_category", "process", "Process", "製程", 40, {}),
    ("rule_category", "quality", "Quality", "品質", 50, {}),
)


def seed_reference_data_and_backfill_rules(apps, schema_editor):
    DataScope = apps.get_model("platform_core", "DataScope")
    MasterDataItem = apps.get_model("platform_core", "MasterDataItem")
    RuleProfile = apps.get_model("platform_core", "RuleProfile")
    Applicability = apps.get_model("platform_core", "RuleProfileApplicability")

    scope = DataScope.objects.get(code="public-demo")
    for kind, code, name_en, name_zh_tw, sort_order, attributes in REFERENCE_DATA_SEED:
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
                "source_refs": ["phase-1:rule-resolution"],
                "classification": "public_demo",
                "created_by": "system:migration",
                "updated_by": "system:migration",
            },
        )

    product_codes = set(
        MasterDataItem.objects.filter(scope=scope, kind="product_type").values_list(
            "code", flat=True
        )
    )
    material_codes = set(
        MasterDataItem.objects.filter(scope=scope, kind="material").values_list(
            "code", flat=True
        )
    )
    for profile in RuleProfile.objects.all():
        profile.scope = scope
        profile.classification = "public_demo"
        profile.is_default = (
            profile.profile_key == "demo-general-design@1.0"
            and profile.workflow_status == "published"
        )
        entries = []
        for value_code in profile.product_scope or []:
            if value_code in product_codes:
                entries.append(("product_type", value_code, "include"))
        for value_code in profile.material_scope or []:
            if value_code in material_codes:
                entries.append(("material", value_code, "include"))
        for dimension, value_code, match_mode in entries:
            Applicability.objects.get_or_create(
                profile=profile,
                dimension=dimension,
                value_code=value_code,
                match_mode=match_mode,
            )
        checksum_payload = {
            "entries": sorted(entries),
            "priority": profile.priority,
            "is_default": profile.is_default,
        }
        profile.applicability_checksum = hashlib.sha256(
            json.dumps(checksum_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        profile.save(
            update_fields=[
                "scope",
                "classification",
                "is_default",
                "applicability_checksum",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("platform_core", "0015_enterprise_history_controls")]

    operations = [
        migrations.AlterField(
            model_name="masterdataitem",
            name="kind",
            field=models.CharField(
                choices=[
                    ("dataset", "Dataset"),
                    ("product_type", "Product type"),
                    ("material", "Material"),
                    ("machine", "Machine"),
                    ("defect", "Defect"),
                    ("location", "Location"),
                    ("unit", "Unit"),
                    ("mold_type", "Mold type"),
                    ("molding_process", "Molding process"),
                    ("rule_category", "Rule category"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="masterdatamappingbacklog",
            name="target_kind",
            field=models.CharField(
                choices=[
                    ("dataset", "Dataset"),
                    ("product_type", "Product type"),
                    ("material", "Material"),
                    ("machine", "Machine"),
                    ("defect", "Defect"),
                    ("location", "Location"),
                    ("unit", "Unit"),
                    ("mold_type", "Mold type"),
                    ("molding_process", "Molding process"),
                    ("rule_category", "Rule category"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="applicability_checksum",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="classification",
            field=models.CharField(default="public_demo", max_length=32),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="effective_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="effective_to",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="priority",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="resolution_status",
            field=models.CharField(
                choices=[("eligible", "Eligible"), ("disabled", "Disabled")],
                default="eligible",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="ruleprofile",
            name="scope",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rule_profiles",
                to="platform_core.datascope",
            ),
        ),
        migrations.AddField(
            model_name="reviewrun",
            name="resolution_snapshot",
            field=models.JSONField(default=dict),
        ),
        migrations.CreateModel(
            name="RuleProfileApplicability",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "dimension",
                    models.CharField(
                        choices=[
                            ("mold_type", "Mold type"),
                            ("product_type", "Product type"),
                            ("material", "Material"),
                            ("molding_process", "Molding process"),
                            ("project", "Project"),
                            ("location", "Location"),
                        ],
                        max_length=32,
                    ),
                ),
                ("value_code", models.CharField(max_length=128)),
                (
                    "match_mode",
                    models.CharField(
                        choices=[("include", "Include"), ("exclude", "Exclude")],
                        default="include",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="applicability_entries",
                        to="platform_core.ruleprofile",
                    ),
                ),
            ],
            options={"ordering": ["dimension", "match_mode", "value_code"]},
        ),
        migrations.AddConstraint(
            model_name="ruleprofileapplicability",
            constraint=models.UniqueConstraint(
                fields=("profile", "dimension", "value_code", "match_mode"),
                name="unique_rule_profile_applicability",
            ),
        ),
        migrations.AddIndex(
            model_name="ruleprofileapplicability",
            index=models.Index(
                fields=["dimension", "value_code", "match_mode"],
                name="rule_applicability_lookup_idx",
            ),
        ),
        migrations.RunPython(
            seed_reference_data_and_backfill_rules,
            migrations.RunPython.noop,
        ),
    ]
