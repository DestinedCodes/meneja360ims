from decimal import Decimal

from django.db import migrations, models


def populate_supply_expense_payables(apps, schema_editor):
    SupplyExpense = apps.get_model('core', 'SupplyExpense')
    for expense in SupplyExpense.objects.all():
        expense.item_name = ''
        expense.quantity = Decimal('1.00')
        expense.unit_price = expense.amount or Decimal('0')
        expense.amount_paid = expense.amount or Decimal('0')
        expense.balance = Decimal('0')
        expense.status = 'paid'
        expense.save(update_fields=['item_name', 'quantity', 'unit_price', 'amount_paid', 'balance', 'status'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_businessprofile_approval_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplyexpense',
            name='amount_paid',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Amount Paid'),
        ),
        migrations.AddField(
            model_name='supplyexpense',
            name='balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Balance'),
        ),
        migrations.AddField(
            model_name='supplyexpense',
            name='item_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='Item Name'),
        ),
        migrations.AddField(
            model_name='supplyexpense',
            name='quantity',
            field=models.DecimalField(decimal_places=2, default=1, max_digits=10, verbose_name='Quantity'),
        ),
        migrations.AddField(
            model_name='supplyexpense',
            name='status',
            field=models.CharField(choices=[('paid', 'Paid'), ('partial', 'Partial'), ('unpaid', 'Unpaid')], default='unpaid', max_length=10, verbose_name='Status'),
        ),
        migrations.AddField(
            model_name='supplyexpense',
            name='unit_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Unit Price'),
        ),
        migrations.RunPython(populate_supply_expense_payables, migrations.RunPython.noop),
    ]
