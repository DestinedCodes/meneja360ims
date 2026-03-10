from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.contrib.auth.views import LoginView as AuthLoginView, LogoutView as AuthLogoutView
from django.urls import reverse_lazy
from django.db.models import Sum, Q, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from .models import BusinessProfile, Client, Transaction, Expense
from .forms import BusinessProfileForm, ClientForm, TransactionForm, ExpenseForm
import json


# Reporting Views
class ReportIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'core/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Get current business (assuming single business for now)
        business = BusinessProfile.objects.first()

        # Today's metrics
        today_revenue = Transaction.objects.filter(
            business=business,
            date__date=today
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        today_expenses = Expense.objects.filter(
            business=business,
            date__date=today
        ).aggregate(total=Sum('amount'))['total'] or 0

        context.update({
            'business': business,
            'today_revenue': today_revenue,
            'today_expenses': today_expenses,
            'net_profit': today_revenue - today_expenses,
        })
        return context


class DailyReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/daily_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report_date = self.request.GET.get('date', timezone.now().date())

        if isinstance(report_date, str):
            report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

        business = BusinessProfile.objects.first()

        # Daily metrics
        revenue = Transaction.objects.filter(
            business=business,
            date__date=report_date
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        expenses = Expense.objects.filter(
            business=business,
            date__date=report_date
        ).aggregate(total=Sum('amount'))['total'] or 0

        transactions = Transaction.objects.filter(
            business=business,
            date__date=report_date
        ).select_related('client').order_by('-date')

        outstanding_balance = Client.objects.filter(
            business=business
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

        context.update({
            'business': business,
            'report_date': report_date,
            'revenue': revenue,
            'expenses': expenses,
            'net_profit': revenue - expenses,
            'transactions': transactions,
            'outstanding_balance': outstanding_balance,
        })
        return context


class MonthlyReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/monthly_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month_str = self.request.GET.get('month', timezone.now().strftime('%Y-%m'))
        year, month = map(int, month_str.split('-'))

        business = BusinessProfile.objects.first()

        # Monthly date range
        month_date = datetime(year, month, 1).date()
        start_date = month_date
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Monthly metrics
        revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(start_date, end_date)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        expenses = Expense.objects.filter(
            business=business,
            date__date__range=(start_date, end_date)
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_transactions = Transaction.objects.filter(
            business=business,
            date__date__range=(start_date, end_date)
        ).count()

        # Daily breakdown for the month
        daily_data = []
        current_date = start_date
        while current_date <= end_date:
            day_revenue = Transaction.objects.filter(
                business=business,
                date__date=current_date
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            day_expenses = Expense.objects.filter(
                business=business,
                date__date=current_date
            ).aggregate(total=Sum('amount'))['total'] or 0

            day_transactions = Transaction.objects.filter(
                business=business,
                date__date=current_date
            ).count()

            daily_data.append({
                'date': current_date,
                'revenue': day_revenue,
                'expenses': day_expenses,
                'profit': day_revenue - day_expenses,
                'transactions': day_transactions,
            })
            current_date += timedelta(days=1)

        # Top clients for the month
        top_clients = Client.objects.filter(
            business=business,
            transactions__date__date__range=(start_date, end_date)
        ).annotate(
            total_spent=Sum('transactions__amount_paid'),
            transaction_count=Count('transactions')
        ).annotate(
            avg_transaction=Avg('transactions__amount_paid')
        ).order_by('-total_spent')[:10]

        # Revenue data for chart
        monthly_revenue = {
            'labels': [day['date'].strftime('%b %d') for day in daily_data],
            'data': [float(day['revenue']) for day in daily_data]
        }

        outstanding_balance = Client.objects.filter(
            business=business
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

        context.update({
            'business': business,
            'month': month_date,
            'revenue': revenue,
            'expenses': expenses,
            'net_profit': revenue - expenses,
            'total_transactions': total_transactions,
            'daily_data': daily_data,
            'top_clients': top_clients,
            'monthly_revenue': json.dumps(monthly_revenue),
            'outstanding_balance': outstanding_balance,
        })
        return context


class YearlyReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/yearly_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = int(self.request.GET.get('year', timezone.now().year))

        business = BusinessProfile.objects.first()

        # Yearly metrics
        revenue = Transaction.objects.filter(
            business=business,
            date__year=year
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        expenses = Expense.objects.filter(
            business=business,
            date__year=year
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_transactions = Transaction.objects.filter(
            business=business,
            date__year=year
        ).count()

        # Monthly breakdown
        monthly_data = []
        monthly_revenue_data = {'labels': [], 'data': []}

        for m in range(1, 13):
            month_start = datetime(year, m, 1).date()
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            month_revenue = Transaction.objects.filter(
                business=business,
                date__date__range=(month_start, month_end)
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            month_expenses = Expense.objects.filter(
                business=business,
                date__date__range=(month_start, month_end)
            ).aggregate(total=Sum('amount'))['total'] or 0

            month_transactions = Transaction.objects.filter(
                business=business,
                date__date__range=(month_start, month_end)
            ).count()

            # Top client for the month
            top_client = Client.objects.filter(
                business=business,
                transactions__date__date__range=(month_start, month_end)
            ).annotate(
                monthly_spent=Sum('transactions__amount_paid')
            ).order_by('-monthly_spent').first()

            monthly_data.append({
                'name': month_start.strftime('%B'),
                'revenue': month_revenue,
                'expenses': month_expenses,
                'profit': month_revenue - month_expenses,
                'transactions': month_transactions,
                'top_client': {
                    'name': top_client.full_name if top_client else None,
                    'amount': top_client.monthly_spent if top_client else 0
                } if top_client else None,
            })

            monthly_revenue_data['labels'].append(month_start.strftime('%b'))
            monthly_revenue_data['data'].append(float(month_revenue))

        # Year-over-year comparison
        prev_year = year - 1
        prev_year_revenue = Transaction.objects.filter(
            business=business,
            date__year=prev_year
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        growth_rate = ((revenue - prev_year_revenue) / prev_year_revenue * 100) if prev_year_revenue > 0 else 0

        # Best and worst months
        best_month = max(monthly_data, key=lambda x: x['revenue'])
        worst_month = min(monthly_data, key=lambda x: x['revenue'])
        avg_monthly = revenue / 12

        # Top clients of the year
        top_clients = Client.objects.filter(
            business=business,
            transactions__date__year=year
        ).annotate(
            total_spent=Sum('transactions__amount_paid'),
            transaction_count=Count('transactions')
        ).annotate(
            avg_transaction=Avg('transactions__amount_paid')
        ).order_by('-total_spent')[:10]

        outstanding_balance = Client.objects.filter(
            business=business
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

        context.update({
            'business': business,
            'year': year,
            'revenue': revenue,
            'expenses': expenses,
            'net_profit': revenue - expenses,
            'total_transactions': total_transactions,
            'monthly_data': monthly_data,
            'monthly_revenue': json.dumps(monthly_revenue_data),
            'growth_rate': growth_rate,
            'best_month': best_month,
            'worst_month': worst_month,
            'avg_monthly': avg_monthly,
            'top_clients': top_clients,
            'outstanding_balance': outstanding_balance,
        })
        return context


class CustomReportView(LoginRequiredMixin, TemplateView):
    template_name = 'core/custom_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        start_date_str = self.request.GET.get('start')
        end_date_str = self.request.GET.get('end')

        business = BusinessProfile.objects.first()

        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            # Custom range metrics
            revenue = Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date)
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            expenses = Expense.objects.filter(
                business=business,
                date__date__range=(start_date, end_date)
            ).aggregate(total=Sum('amount'))['total'] or 0

            total_transactions = Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date)
            ).count()

            # Transaction status breakdown
            paid_transactions = Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date),
                status='paid'
            ).count()

            partial_transactions = Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date),
                status='partial'
            ).count()

            unpaid_transactions = Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date),
                status='unpaid'
            ).count()

            # Daily breakdown
            daily_data = []
            days_count = (end_date - start_date).days + 1
            current_date = start_date

            daily_revenue_data = {'labels': [], 'data': []}

            while current_date <= end_date:
                day_revenue = Transaction.objects.filter(
                    business=business,
                    date__date=current_date
                ).aggregate(total=Sum('amount_paid'))['total'] or 0

                day_expenses = Expense.objects.filter(
                    business=business,
                    date__date=current_date
                ).aggregate(total=Sum('amount'))['total'] or 0

                day_transactions = Transaction.objects.filter(
                    business=business,
                    date__date=current_date
                ).count()

                daily_data.append({
                    'date': current_date,
                    'revenue': day_revenue,
                    'expenses': day_expenses,
                    'profit': day_revenue - day_expenses,
                    'transactions': day_transactions,
                })

                daily_revenue_data['labels'].append(current_date.strftime('%m/%d'))
                daily_revenue_data['data'].append(float(day_revenue))

                current_date += timedelta(days=1)

            # Top clients
            top_clients = Client.objects.filter(
                business=business,
                transactions__date__date__range=(start_date, end_date)
            ).annotate(
                total_spent=Sum('transactions__amount_paid'),
                transaction_count=Count('transactions')
            ).annotate(
                avg_transaction=Avg('transactions__amount_paid')
            ).order_by('-total_spent')[:10]

            # Expense categories breakdown
            total_expenses_for_calc = expenses if expenses > 0 else 1  # Avoid division by zero
            expense_categories = Expense.objects.filter(
                business=business,
                date__date__range=(start_date, end_date)
            ).values('category').annotate(
                amount=Sum('amount')
            ).order_by('-amount')

            expense_categories_list = []
            for category in expense_categories:
                percentage = (category['amount'] / total_expenses_for_calc) * 100
                expense_categories_list.append({
                    'name': category['category'],
                    'amount': category['amount'],
                    'percentage': percentage,
                })

            outstanding_balance = Client.objects.filter(
                business=business
            ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

            context.update({
                'business': business,
                'start_date': start_date,
                'end_date': end_date,
                'days_count': days_count,
                'revenue': revenue,
                'expenses': expenses,
                'net_profit': revenue - expenses,
                'total_transactions': total_transactions,
                'paid_transactions': paid_transactions,
                'partial_transactions': partial_transactions,
                'unpaid_transactions': unpaid_transactions,
                'daily_data': daily_data,
                'daily_revenue': json.dumps(daily_revenue_data),
                'top_clients': top_clients,
                'expense_categories': expense_categories_list,
                'outstanding_balance': outstanding_balance,
            })
        else:
            # Default to current month if no dates provided
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            context.update({
                'business': business,
                'start_date': start_date,
                'end_date': end_date,
            })

        return context


# Backup and Restore Views
class BackupView(LoginRequiredMixin, TemplateView):
    template_name = 'core/backup.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = BusinessProfile.objects.first()
        context['business'] = business
        return context


class RestoreView(LoginRequiredMixin, TemplateView):
    template_name = 'core/restore.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = BusinessProfile.objects.first()
        context['business'] = business
        return context


# Export Views
def export_daily_report_pdf(request):
    """Export daily report to PDF"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from django.http import HttpResponse
    import io

    # Get report data
    report_date = request.GET.get('date', timezone.now().date())
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

    business = BusinessProfile.objects.first()
    revenue = Transaction.objects.filter(
        business=business, date__date=report_date
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    expenses = Expense.objects.filter(
        business=business, date__date=report_date
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, f"Daily Report - {business.name}")
    p.drawString(100, height - 70, f"Date: {report_date}")

    # Metrics
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 100, f"Total Revenue: ${revenue:.2f}")
    p.drawString(100, height - 120, f"Total Expenses: ${expenses:.2f}")
    p.drawString(100, height - 140, f"Net Profit: ${(revenue - expenses):.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="daily_report_{report_date}.pdf"'
    return response


def export_monthly_report_pdf(request):
    """Export monthly report to PDF"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from django.http import HttpResponse
    import io

    month_str = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    year, month = map(int, month_str.split('-'))

    business = BusinessProfile.objects.first()
    month_date = datetime(year, month, 1).date()
    start_date = month_date
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    revenue = Transaction.objects.filter(
        business=business, date__date__range=(start_date, end_date)
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    expenses = Expense.objects.filter(
        business=business, date__date__range=(start_date, end_date)
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, f"Monthly Report - {business.name}")
    p.drawString(100, height - 70, f"Month: {month_date.strftime('%B %Y')}")

    # Metrics
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 100, f"Total Revenue: ${revenue:.2f}")
    p.drawString(100, height - 120, f"Total Expenses: ${expenses:.2f}")
    p.drawString(100, height - 140, f"Net Profit: ${(revenue - expenses):.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_report_{month_str}.pdf"'
    return response


def export_yearly_report_pdf(request):
    """Export yearly report to PDF"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from django.http import HttpResponse
    import io

    year = int(request.GET.get('year', timezone.now().year))

    business = BusinessProfile.objects.first()
    revenue = Transaction.objects.filter(
        business=business, date__year=year
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    expenses = Expense.objects.filter(
        business=business, date__year=year
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, f"Yearly Report - {business.name}")
    p.drawString(100, height - 70, f"Year: {year}")

    # Metrics
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 100, f"Total Revenue: ${revenue:.2f}")
    p.drawString(100, height - 120, f"Total Expenses: ${expenses:.2f}")
    p.drawString(100, height - 140, f"Net Profit: ${(revenue - expenses):.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="yearly_report_{year}.pdf"'
    return response


def export_custom_report_pdf(request):
    """Export custom report to PDF"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from django.http import HttpResponse
    import io

    start_date_str = request.GET.get('start')
    end_date_str = request.GET.get('end')

    if not start_date_str or not end_date_str:
        return HttpResponse("Date range required", status=400)

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    business = BusinessProfile.objects.first()
    revenue = Transaction.objects.filter(
        business=business, date__date__range=(start_date, end_date)
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    expenses = Expense.objects.filter(
        business=business, date__date__range=(start_date, end_date)
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, height - 50, f"Custom Report - {business.name}")
    p.drawString(100, height - 70, f"Period: {start_date} to {end_date}")

    # Metrics
    p.setFont("Helvetica", 12)
    p.drawString(100, height - 100, f"Total Revenue: ${revenue:.2f}")
    p.drawString(100, height - 120, f"Total Expenses: ${expenses:.2f}")
    p.drawString(100, height - 140, f"Net Profit: ${(revenue - expenses):.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="custom_report_{start_date_str}_to_{end_date_str}.pdf"'
    return response


# Function-based views for reporting
report_index = ReportIndexView.as_view()
daily_report = DailyReportView.as_view()
monthly_report = MonthlyReportView.as_view()
yearly_report = YearlyReportView.as_view()
custom_report = CustomReportView.as_view()
backup = BackupView.as_view()
restore = RestoreView.as_view()