from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_client_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='address',
            field=models.TextField(blank=True, help_text='Optional billing or postal address', verbose_name='Address'),
        ),
        migrations.AddField(
            model_name='client',
            name='company_name',
            field=models.CharField(blank=True, help_text='Optional company or organization name', max_length=255, verbose_name='Company Name'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='document_notes',
            field=models.TextField(blank=True, verbose_name='Document Notes'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='invoice_discount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Invoice Discount'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='invoice_due_date',
            field=models.DateField(blank=True, null=True, verbose_name='Invoice Due Date'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='invoice_tax_rate',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Invoice Tax Rate (%)'),
        ),
    ]
