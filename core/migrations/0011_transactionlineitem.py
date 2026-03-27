from django.db import migrations, models


def create_line_items_for_existing_transactions(apps, schema_editor):
    Transaction = apps.get_model('core', 'Transaction')
    TransactionLineItem = apps.get_model('core', 'TransactionLineItem')

    for transaction in Transaction.objects.all():
        has_items = TransactionLineItem.objects.filter(transaction=transaction).exists()
        if has_items:
            continue
        TransactionLineItem.objects.create(
            transaction=transaction,
            description=transaction.service_name,
            quantity=transaction.quantity,
            unit_price=transaction.unit_price,
            line_total=transaction.total_amount,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_invoice_receipt_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='TransactionLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(max_length=255, verbose_name='Description')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Quantity')),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Unit Price')),
                ('line_total', models.DecimalField(blank=True, decimal_places=2, max_digits=12, verbose_name='Line Total')),
                ('transaction', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='items', to='core.transaction')),
            ],
            options={
                'verbose_name': 'Transaction Line Item',
                'verbose_name_plural': 'Transaction Line Items',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(create_line_items_for_existing_transactions, migrations.RunPython.noop),
    ]
