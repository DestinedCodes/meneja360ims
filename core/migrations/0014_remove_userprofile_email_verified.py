from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_userprofile_email_verified"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="email_verified",
        ),
    ]
