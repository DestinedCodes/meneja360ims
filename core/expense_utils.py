from decimal import Decimal

from django.db.models import Sum

from .models import Expense, SupplyExpense


def general_expenses_qs(business):
    return Expense.objects.filter(business=business).exclude(category=Expense.SUPPLIES)


def supply_expenses_qs(business):
    return SupplyExpense.objects.filter(business=business)


def combined_expense_total(business, **filters):
    general_total = general_expenses_qs(business).filter(**filters).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    supply_total = supply_expenses_qs(business).filter(**filters).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    return general_total + supply_total


def expense_breakdown_by_category(business, **filters):
    breakdown = []
    general_rows = (
        general_expenses_qs(business)
        .filter(**filters)
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    category_labels = dict(Expense.CATEGORY_CHOICES)
    for row in general_rows:
        breakdown.append({
            'category': category_labels.get(row['category'], row['category'].title()),
            'total': float(row['total'] or 0),
        })

    supply_total = supply_expenses_qs(business).filter(**filters).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    if supply_total:
        breakdown.append({
            'category': 'Supplies',
            'total': float(supply_total),
        })

    breakdown.sort(key=lambda item: item['total'], reverse=True)
    return breakdown
