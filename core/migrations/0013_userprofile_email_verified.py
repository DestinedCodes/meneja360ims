from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_super_admin_subscription_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
    ]
