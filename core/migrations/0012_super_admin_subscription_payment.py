from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_transactionlineitem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='businessprofile',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='Active'),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='subscription_end_date',
            field=models.DateField(blank=True, null=True, verbose_name='Subscription End Date'),
        ),
        migrations.AddField(
            model_name='businessprofile',
            name='subscription_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='Subscription Start Date'),
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Amount')),
                ('payment_date', models.DateField(default=django.utils.timezone.localdate, verbose_name='Payment Date')),
                ('duration_days', models.PositiveIntegerField(default=30, verbose_name='Subscription Duration (Days)')),
                ('reference', models.CharField(blank=True, max_length=100, verbose_name='Reference')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='core.businessprofile')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recorded_payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Payment',
                'verbose_name_plural': 'Payments',
                'ordering': ['-payment_date', '-created_at'],
            },
        ),
    ]
