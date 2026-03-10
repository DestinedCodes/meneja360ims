from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.contrib.auth.views import LoginView as AuthLoginView, LogoutView as AuthLogoutView
from django.urls import reverse_lazy
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import BusinessProfile, Client, Transaction, Expense
from .forms import BusinessProfileForm, ClientForm, TransactionForm, ExpenseForm


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filter parameters from request
        request = self.request
        selected_year = int(request.GET.get('year', timezone.now().year))
        selected_month = request.GET.get('month')

        # Get today's date
        today = timezone.now().date()

        # Get all businesses for the user (assuming single business for now)
        # In a multi-business setup, you'd filter by user/business ownership
        businesses = BusinessProfile.objects.all()

        # Today's metrics (always show today's data)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

        today_revenue = Transaction.objects.filter(
            business__in=businesses,
            date__range=(today_start, today_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        today_expenses = Expense.objects.filter(
            business__in=businesses,
            date__range=(today_start, today_end)
        ).aggregate(total=Sum('amount'))['total'] or 0

        net_profit = today_revenue - today_expenses

        # Total outstanding balance
        total_outstanding = Client.objects.filter(
            business__in=businesses
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

        # Recent transactions (last 10)
        recent_transactions = Transaction.objects.filter(
            business__in=businesses
        ).select_related('client').order_by('-date')[:10]

        # Recent expenses (last 10)
        recent_expenses = Expense.objects.filter(
            business__in=businesses
        ).order_by('-date')[:10]

        # Monthly data for the selected year (for graphs)
        monthly_data = []
        for month in range(1, 13):
            month_start = datetime(selected_year, month, 1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            revenue = Transaction.objects.filter(
                business__in=businesses,
                date__date__range=(month_start.date(), month_end.date())
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            expenses = Expense.objects.filter(
                business__in=businesses,
                date__date__range=(month_start.date(), month_end.date())
            ).aggregate(total=Sum('amount'))['total'] or 0

            monthly_data.append({
                'month': month_start.strftime('%B'),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': float(revenue - expenses)
            })

        # Year options for dropdown
        years = list(range(selected_year - 2, selected_year + 3))

        context.update({
            'today_revenue': today_revenue,
            'today_expenses': today_expenses,
            'net_profit': net_profit,
            'total_outstanding': total_outstanding,
            'recent_transactions': recent_transactions,
            'recent_expenses': recent_expenses,
            'monthly_data': monthly_data,
            'current_year': selected_year,
            'selected_month': selected_month,
            'years': years,
        })

        return context


dashboard = DashboardView.as_view()


# business
class BusinessListView(LoginRequiredMixin, ListView):
    model = BusinessProfile
    template_name = 'core/business_list.html'


class BusinessCreateView(LoginRequiredMixin, CreateView):
    model = BusinessProfile
    form_class = BusinessProfileForm
    template_name = 'core/business_form.html'
    success_url = reverse_lazy('business_list')


class BusinessUpdateView(LoginRequiredMixin, UpdateView):
    model = BusinessProfile
    form_class = BusinessProfileForm
    template_name = 'core/business_form.html'
    success_url = reverse_lazy('business_list')


# client
class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'core/client_list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        client_type = self.request.GET.get('type')
        if client_type:
            qs = qs.filter(client_type=client_type)
        return qs


class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'core/client_form.html'
    success_url = reverse_lazy('client_list')


class ClientUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'core/client_form.html'
    success_url = reverse_lazy('client_list')


# transaction
class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'core/transaction_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        # filtering by GET params
        status = self.request.GET.get('status')
        client = self.request.GET.get('client')
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if status:
            qs = qs.filter(status=status)
        if client:
            qs = qs.filter(client__id=client)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs


class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'core/transaction_form.html'
    success_url = reverse_lazy('transaction_list')


class TransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'core/transaction_form.html'
    success_url = reverse_lazy('transaction_list')


# expense
class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    template_name = 'core/expense_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.GET.get('category')
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if category:
            qs = qs.filter(category=category)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs


class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'core/expense_form.html'
    success_url = reverse_lazy('expense_list')


class ExpenseUpdateView(LoginRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'core/expense_form.html'
    success_url = reverse_lazy('expense_list')


# authentication
class LoginView(AuthLoginView):
    template_name = 'core/login.html'


class LogoutView(AuthLogoutView):
    pass


# placeholder report view
def report_index(request):
    # gather some basic aggregates
    if not request.user.is_authenticated:
        return redirect('login')
    from django.db.models import Sum
    data = {}
    data['total_revenue'] = Transaction.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    data['total_expense'] = Expense.objects.aggregate(total=Sum('amount'))['total'] or 0
    return render(request, 'core/reports.html', {'data': data})


# backup / restore views
import os
from django.conf import settings
from django.http import HttpResponse

def backup(request):
    if not request.user.is_authenticated:
        return redirect('login')
    db_path = settings.DATABASES['default']['NAME']
    if os.path.exists(db_path):
        with open(db_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/x-sqlite3')
            response['Content-Disposition'] = 'attachment; filename="db_backup.sqlite3"'
            return response
    return HttpResponse('Database file not found', status=404)


def restore(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST' and request.FILES.get('dbfile'):
        db_path = settings.DATABASES['default']['NAME']
        uploaded = request.FILES['dbfile']
        with open(db_path, 'wb') as f:
            for chunk in uploaded.chunks():
                f.write(chunk)
        return redirect('dashboard')
    return render(request, 'core/restore.html')
