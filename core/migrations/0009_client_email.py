from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_supplyexpense_split'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='email',
            field=models.EmailField(blank=True, help_text="Client's email address", null=True, verbose_name='Email Address'),
        ),
    ]
