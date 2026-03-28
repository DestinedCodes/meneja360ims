from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_remove_userprofile_email_verified"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessprofile",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Approval"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                default="approved",
                max_length=20,
                verbose_name="Approval Status",
            ),
        ),
    ]
