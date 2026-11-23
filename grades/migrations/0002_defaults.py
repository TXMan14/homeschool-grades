from decimal import Decimal

from django.db import migrations

DEFAULT_SCALE = [
    ("A", "90", "4.0"),
    ("B", "80", "3.0"),
    ("C", "70", "2.0"),
    ("D", "60", "1.0"),
    ("F", "0", "0.0"),
]


def seed(apps, schema_editor):
    GradeScaleEntry = apps.get_model("grades", "GradeScaleEntry")
    SchoolSettings = apps.get_model("grades", "SchoolSettings")
    if not GradeScaleEntry.objects.exists():
        for letter, minimum, points in DEFAULT_SCALE:
            GradeScaleEntry.objects.create(
                letter=letter, min_percent=Decimal(minimum), grade_points=Decimal(points)
            )
    SchoolSettings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("grades", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
