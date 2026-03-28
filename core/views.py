import io
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, FormView
from django.contrib.auth.views import (
    LoginView as AuthLoginView,
    PasswordResetView as AuthPasswordResetView,
    PasswordResetDoneView as AuthPasswordResetDoneView,
    PasswordResetConfirmView as AuthPasswordResetConfirmView,
    PasswordResetCompleteView as AuthPasswordResetCompleteView,
    PasswordChangeView as AuthPasswordChangeView,
    PasswordChangeDoneView as AuthPasswordChangeDoneView,
)
from django.urls import reverse, reverse_lazy
from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Sum, Q, Count, Max
from django.http import Http404, HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from .models import BusinessProfile, Client, Transaction, Expense, SupplyExpense
from .auth_security import UserProfile
from .business_access import get_business_access_state
from .expense_utils import combined_expense_total, expense_breakdown_by_category, general_expenses_qs
from .forms import BusinessProfileForm, ClientForm, TransactionForm, ExpenseForm, RegistrationForm, StaffUserCreationForm, TeamMemberUpdateForm, SupplyExpenseForm, SupplyExpenseLineItemFormSet, InvoiceSettingsForm, TransactionLineItemFormSet
from .permissions import AdminRequiredMixin, RecordsRequiredMixin, ReportsRequiredMixin, can_backup_restore
from .tenancy import BusinessFormMixin, BusinessScopedQuerysetMixin, UserBusinessMixin, get_user_business


class DashboardView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filter parameters from request
        request = self.request
        today = timezone.now().date()
        selected_date_str = request.GET.get('date', today.isoformat())
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
        selected_year = int(request.GET.get('year', selected_date.year))
        selected_month = request.GET.get('month', str(selected_date.month))

        business = self.get_business()

        # Today's metrics (for cards)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)
        today_revenue = Transaction.objects.filter(
            business=business,
            date__range=(today_start, today_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        today_expenses = combined_expense_total(
            business,
            date__range=(today_start, today_end)
        )
        today_expense_breakdown = expense_breakdown_by_category(
            business,
            date__range=(today_start, today_end)
        )
        daily_start = datetime.combine(selected_date, datetime.min.time())
        daily_end = datetime.combine(selected_date, datetime.max.time())
        selected_date_str = selected_date.isoformat()

        daily_revenue = Transaction.objects.filter(
            business=business,
            date__range=(daily_start, daily_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        daily_expenses = combined_expense_total(
            business,
            date__range=(daily_start, daily_end)
        )

        daily_profit = daily_revenue - daily_expenses

        # Weekly metrics for selected date
        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        weekly_expenses = combined_expense_total(
            business,
            date__date__range=(week_start, week_end)
        )
        weekly_profit = weekly_revenue - weekly_expenses

        # Monthly metrics for selected month/year
        try:
            sel_month_int = int(selected_month)
        except (TypeError, ValueError):
            sel_month_int = selected_date.month
        month_start = datetime(selected_year, sel_month_int, 1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        monthly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(month_start.date(), month_end.date())
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        monthly_expenses = combined_expense_total(
            business,
            date__date__range=(month_start.date(), month_end.date())
        )
        monthly_profit = monthly_revenue - monthly_expenses

        # Net profit shown as selected daily profit
        net_profit = daily_profit

        # Total outstanding balance
        total_outstanding = Client.objects.filter(
            business=business
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0
        total_supplier_outstanding = SupplyExpense.objects.filter(
            business=business,
            balance__gt=0,
        ).aggregate(total=Sum('balance'))['total'] or 0

        # Recent transactions (last 10)
        recent_transactions = Transaction.objects.filter(
            business=business
        ).select_related('client').order_by('-date')[:10]

        # Recent expenses (last 10)
        recent_expenses = general_expenses_qs(business).order_by('-date')[:10]

        # Monthly data for the selected year (for graphs)
        monthly_data = []
        for month in range(1, 13):
            month_start = datetime(selected_year, month, 1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            revenue = Transaction.objects.filter(
                business=business,
                date__date__range=(month_start.date(), month_end.date())
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            expenses = combined_expense_total(
                business,
                date__date__range=(month_start.date(), month_end.date())
            )

            monthly_data.append({
                'month': month_start.strftime('%B'),
                'revenue': float(revenue),
                'expenses': float(expenses),
                'profit': float(revenue - expenses)
            })

        # Year options for dropdown
        years = list(range(selected_year - 2, selected_year + 3))

        context.update({
            'today_revenue': daily_revenue,
            'today_expenses': daily_expenses,
            'today_expense_breakdown_labels': [row['category'] for row in today_expense_breakdown],
            'today_expense_breakdown_data': [row['total'] for row in today_expense_breakdown],
            'daily_revenue': daily_revenue,
            'weekly_revenue': weekly_revenue,
            'monthly_revenue': monthly_revenue,
            'daily_profit': daily_profit,
            'weekly_profit': weekly_profit,
            'monthly_profit': monthly_profit,
            'net_profit': net_profit,
            'total_outstanding': total_outstanding,
            'total_supplier_outstanding': total_supplier_outstanding,
            'recent_transactions': recent_transactions,
            'recent_expenses': recent_expenses,
            'monthly_data': monthly_data,
            'current_year': selected_year,
            'selected_month': selected_month,
            'selected_date': selected_date_str,
            'years': years,
        })

        return context


class DailyRevenueDetailView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/daily_revenue_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        today = timezone.now().date()
        selected_date_str = request.GET.get('date', today.isoformat())
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today

        selected_year = int(request.GET.get('year', selected_date.year))
        selected_month = request.GET.get('month', str(selected_date.month))
        try:
            sel_month_int = int(selected_month)
        except (TypeError, ValueError):
            sel_month_int = selected_date.month

        business = self.get_business()

        daily_start = datetime.combine(selected_date, datetime.min.time())
        daily_end = datetime.combine(selected_date, datetime.max.time())
        daily_revenue = Transaction.objects.filter(
            business=business,
            date__range=(daily_start, daily_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        month_begin = datetime(selected_year, sel_month_int, 1)
        month_end = (month_begin + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        monthly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(month_begin.date(), month_end.date())
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        context.update({
            'selected_date': selected_date.isoformat(),
            'selected_month': str(sel_month_int),
            'selected_year': selected_year,
            'daily_revenue': daily_revenue,
            'weekly_revenue': weekly_revenue,
            'monthly_revenue': monthly_revenue,
            'years': list(range(selected_year - 2, selected_year + 3)),
            'months': list(range(1, 13)),
        })
        return context


class NetProfitDetailView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/net_profit_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        today = timezone.now().date()
        selected_date_str = request.GET.get('date', today.isoformat())
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
        selected_year = int(request.GET.get('year', selected_date.year))
        selected_month = request.GET.get('month', str(selected_date.month))

        try:
            sel_month_int = int(selected_month)
        except (TypeError, ValueError):
            sel_month_int = selected_date.month

        business = self.get_business()

        day_start = datetime.combine(selected_date, datetime.min.time())
        day_end = datetime.combine(selected_date, datetime.max.time())
        daily_revenue = Transaction.objects.filter(
            business=business,
            date__range=(day_start, day_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        daily_expense = combined_expense_total(
            business,
            date__range=(day_start, day_end)
        )
        daily_profit = daily_revenue - daily_expense

        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        weekly_expense = combined_expense_total(
            business,
            date__date__range=(week_start, week_end)
        )
        weekly_profit = weekly_revenue - weekly_expense

        month_begin = datetime(selected_year, sel_month_int, 1)
        month_end = (month_begin + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        monthly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(month_begin.date(), month_end.date())
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        monthly_expense = combined_expense_total(
            business,
            date__date__range=(month_begin.date(), month_end.date())
        )
        monthly_profit = monthly_revenue - monthly_expense

        context.update({
            'selected_date': selected_date.isoformat(),
            'selected_month': str(sel_month_int),
            'selected_year': selected_year,
            'daily_profit': daily_profit,
            'weekly_profit': weekly_profit,
            'monthly_profit': monthly_profit,
            'years': list(range(selected_year - 2, selected_year + 3)),
        })
        return context


dashboard = DashboardView.as_view()
net_profit_detail = NetProfitDetailView.as_view()


class SettingsView(LoginRequiredMixin, AdminRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/settings.html'

    def get(self, request, *args, **kwargs):
        business = self.get_business()
        form = BusinessProfileForm(instance=business)
        return render(request, self.template_name, {'form': form, 'business': business})

    def post(self, request, *args, **kwargs):
        business = self.get_business()
        form = BusinessProfileForm(request.POST, request.FILES, instance=business)
        if form.is_valid():
            updated_business = form.save(commit=False)
            updated_business.owner = request.user
            updated_business.save()
            return redirect('settings')
        return render(request, self.template_name, {'form': form, 'business': business})


class TeamManagementView(LoginRequiredMixin, AdminRequiredMixin, UserBusinessMixin, FormView):
    template_name = 'core/team_management.html'
    form_class = StaffUserCreationForm
    success_url = reverse_lazy('team_management')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_business()
        return kwargs

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f'Team member "{user.username}" was created successfully.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = self.get_business()
        team_members = UserProfile.objects.filter(
            business=business
        ).select_related('user').order_by('role', 'user__username')
        context.update({
            'business': business,
            'team_members': team_members,
            'owner': business.owner,
        })
        return context


class TeamMemberUpdateView(LoginRequiredMixin, AdminRequiredMixin, UserBusinessMixin, UpdateView):
    model = User
    form_class = TeamMemberUpdateForm
    template_name = 'core/team_member_form.html'
    success_url = reverse_lazy('team_management')

    def get_queryset(self):
        business = self.get_business()
        return User.objects.filter(profile__business=business).select_related('profile')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_business()
        return kwargs

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f'Team member "{user.username}" was updated successfully.')
        return redirect(self.success_url)


class OutstandingBalanceListView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, ListView):
    model = Transaction
    template_name = 'core/outstanding_balances.html'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .filter(business=self.get_business())
            .filter(balance__gt=0)
            .select_related('client')
        )
        client_name = self.request.GET.get('client_name', '').strip()
        start_date = self.request.GET.get('start_date', '').strip()
        end_date = self.request.GET.get('end_date', '').strip()
        min_balance = self.request.GET.get('min_balance')
        max_balance = self.request.GET.get('max_balance')

        if client_name:
            qs = qs.filter(
                Q(client__full_name__icontains=client_name) |
                Q(service_name__icontains=client_name)
            )
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                qs = qs.filter(date__date__gte=start_date)
            except ValueError:
                pass
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                qs = qs.filter(date__date__lte=end_date)
            except ValueError:
                pass
        if min_balance:
            try:
                qs = qs.filter(balance__gte=float(min_balance))
            except ValueError:
                pass
        if max_balance:
            try:
                qs = qs.filter(balance__lte=float(max_balance))
            except ValueError:
                pass

        return qs.order_by('-date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client_name'] = self.request.GET.get('client_name', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')
        context['min_balance'] = self.request.GET.get('min_balance', '')
        context['max_balance'] = self.request.GET.get('max_balance', '')
        return context


class SupplierListView(LoginRequiredMixin, RecordsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/supplier_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = self.get_business()
        search = self.request.GET.get('search', '').strip()
        supplier_rows = (
            SupplyExpense.objects.filter(business=business)
            .values('supplier_name', 'supplier_contact')
            .annotate(
                records_count=Count('id'),
                total_supplied=Sum('amount'),
                total_paid=Sum('amount_paid'),
                total_balance=Sum('balance'),
                last_supply_date=Max('date'),
            )
            .order_by('supplier_name')
        )
        if search:
            supplier_rows = supplier_rows.filter(
                Q(supplier_name__icontains=search) |
                Q(supplier_contact__icontains=search) |
                Q(item_name__icontains=search) |
                Q(items__item_name__icontains=search) |
                Q(items__description__icontains=search) |
                Q(description__icontains=search)
            ).distinct()
        context.update({
            'suppliers': supplier_rows,
            'search': search,
        })
        return context


class SupplierOutstandingBalanceListView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, ListView):
    model = SupplyExpense
    template_name = 'core/supplier_outstanding_balances.html'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .filter(business=self.get_business(), balance__gt=0)
            .order_by('-date')
        )
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(supplier_name__icontains=search) |
                Q(supplier_contact__icontains=search) |
                Q(item_name__icontains=search) |
                Q(items__item_name__icontains=search) |
                Q(items__description__icontains=search) |
                Q(description__icontains=search)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = self.get_business()
        search = self.request.GET.get('search', '').strip()
        supplier_summary = (
            SupplyExpense.objects.filter(business=business, balance__gt=0)
            .values('supplier_name', 'supplier_contact')
            .annotate(
                total_amount=Sum('amount'),
                total_paid=Sum('amount_paid'),
                total_balance=Sum('balance'),
                records_count=Count('id'),
            )
            .order_by('-total_balance', 'supplier_name')
        )
        if search:
            supplier_summary = supplier_summary.filter(
                Q(supplier_name__icontains=search) |
                Q(supplier_contact__icontains=search)
            )
        context.update({
            'search': search,
            'supplier_summary': supplier_summary,
            'total_supplier_outstanding': SupplyExpense.objects.filter(
                business=business,
                balance__gt=0,
            ).aggregate(total=Sum('balance'))['total'] or 0,
        })
        return context


# business
class BusinessListView(LoginRequiredMixin, AdminRequiredMixin, UserBusinessMixin, ListView):
    model = BusinessProfile
    template_name = 'core/business_list.html'

    def get_queryset(self):
        return BusinessProfile.objects.filter(owner=self.request.user)


class BusinessCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = BusinessProfile
    form_class = BusinessProfileForm
    template_name = 'core/business_form.html'
    success_url = reverse_lazy('business_list')

    def dispatch(self, request, *args, **kwargs):
        business = BusinessProfile.objects.filter(owner=request.user).first()
        if business:
            return redirect('business_edit', pk=business.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        business = form.save(commit=False)
        business.owner = self.request.user
        business.save()
        return redirect(self.success_url)


class BusinessUpdateView(LoginRequiredMixin, AdminRequiredMixin, UserBusinessMixin, UpdateView):
    model = BusinessProfile
    form_class = BusinessProfileForm
    template_name = 'core/business_form.html'
    success_url = reverse_lazy('business_list')

    def get_queryset(self):
        return BusinessProfile.objects.filter(owner=self.request.user)

    def form_valid(self, form):
        business = form.save(commit=False)
        business.owner = self.request.user
        business.save()
        return redirect(self.success_url)


class BusinessDeleteView(LoginRequiredMixin, AdminRequiredMixin, UserBusinessMixin, DeleteView):
    model = BusinessProfile
    template_name = 'core/business_confirm_delete.html'
    success_url = reverse_lazy('business_list')

    def get_queryset(self):
        return BusinessProfile.objects.filter(owner=self.request.user)


# client
class ClientListView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, ListView):
    model = Client
    template_name = 'core/client_list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        client_type = self.request.GET.get('type')
        search = self.request.GET.get('search', '').strip()
        if client_type:
            qs = qs.filter(client_type=client_type)
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(notes__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class ClientCreateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'core/client_form.html'
    success_url = reverse_lazy('client_list')


class ClientUpdateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, BusinessScopedQuerysetMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'core/client_form.html'
    success_url = reverse_lazy('client_list')


class ClientDeleteView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, DeleteView):
    model = Client
    template_name = 'core/client_confirm_delete.html'
    success_url = reverse_lazy('client_list')


def _parse_statement_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _build_client_statement(client, start_date=None, end_date=None):
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    transactions = Transaction.objects.filter(
        business=client.business,
        client=client,
    )

    if start_date:
        transactions = transactions.filter(date__date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__date__lte=end_date)

    transactions = transactions.order_by('date', 'id')

    rows = []
    running_balance = Decimal('0.00')
    total_amount = Decimal('0.00')
    total_paid = Decimal('0.00')
    total_balance = Decimal('0.00')

    for transaction in transactions:
        total_amount += transaction.total_amount
        total_paid += transaction.amount_paid
        total_balance += transaction.balance
        running_balance += transaction.balance
        rows.append({
            'date': transaction.date,
            'service_name': transaction.service_name,
            'total_amount': transaction.total_amount,
            'amount_paid': transaction.amount_paid,
            'balance': transaction.balance,
            'running_balance': running_balance,
            'status': transaction.get_status_display(),
        })

    return {
        'rows': rows,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_balance': total_balance,
    }


def _build_supplier_statement(business, supplier_name, supplier_contact='', start_date=None, end_date=None):
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    expenses = SupplyExpense.objects.filter(
        business=business,
        supplier_name=supplier_name,
    )
    if supplier_contact:
        expenses = expenses.filter(supplier_contact=supplier_contact)
    if start_date:
        expenses = expenses.filter(date__date__gte=start_date)
    if end_date:
        expenses = expenses.filter(date__date__lte=end_date)

    expenses = expenses.order_by('date', 'id')

    rows = []
    running_balance = Decimal('0.00')
    total_amount = Decimal('0.00')
    total_paid = Decimal('0.00')
    total_balance = Decimal('0.00')
    total_quantity = Decimal('0.00')

    for expense in expenses:
        total_amount += expense.amount
        total_paid += expense.amount_paid
        total_balance += expense.balance
        total_quantity += expense.quantity
        running_balance += expense.balance
        rows.append({
            'date': expense.date,
            'item_name': expense.get_item_summary(),
            'description': expense.description,
            'quantity': expense.quantity,
            'unit_price': expense.unit_price,
            'amount': expense.amount,
            'amount_paid': expense.amount_paid,
            'balance': expense.balance,
            'running_balance': running_balance,
            'status': expense.get_status_display(),
        })

    return {
        'rows': rows,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'total_quantity': total_quantity,
    }


class ClientStatementView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/client_statement.html'

    def get_client(self):
        client = Client.objects.filter(
            pk=self.kwargs['pk'],
            business=self.get_business(),
        ).first()
        if client is None:
            raise Http404("Client not found.")
        return client

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_client()
        start_date = _parse_statement_date(self.request.GET.get('start_date', '').strip())
        end_date = _parse_statement_date(self.request.GET.get('end_date', '').strip())
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date
        statement_data = _build_client_statement(client, start_date=start_date, end_date=end_date)

        context.update({
            'business': self.get_business(),
            'client': client,
            'statement_title': 'Statement of Account',
            'statement_rows': statement_data['rows'],
            'total_amount': statement_data['total_amount'],
            'total_paid': statement_data['total_paid'],
            'total_balance': statement_data['total_balance'],
            'start_date': start_date.isoformat() if start_date else '',
            'end_date': end_date.isoformat() if end_date else '',
            'date_range_applied': bool(start_date or end_date),
            'generated_at': timezone.localtime(),
            'whatsapp_url': client.get_whatsapp_url(),
        })
        return context


def export_client_statement_pdf(request, pk):
    if not request.user.is_authenticated:
        raise Http404("Client not found.")

    business = get_user_business(request.user)
    client = Client.objects.filter(pk=pk, business=business).first()
    if client is None:
        raise Http404("Client not found.")

    start_date = _parse_statement_date(request.GET.get('start_date', '').strip())
    end_date = _parse_statement_date(request.GET.get('end_date', '').strip())
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date
    statement_data = _build_client_statement(client, start_date=start_date, end_date=end_date)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as ReportImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ClientStatementTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#12263A'),
    )
    normal_style = ParagraphStyle(
        'ClientStatementBody',
        parent=styles['BodyText'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155'),
    )
    muted_style = ParagraphStyle(
        'ClientStatementMuted',
        parent=normal_style,
        textColor=colors.HexColor('#64748B'),
    )

    story = []
    logo_cell = ''
    if business.logo:
        try:
            logo_cell = ReportImage(business.logo.path, width=0.9 * inch, height=0.9 * inch)
        except Exception:
            logo_cell = ''

    period_label = 'All transactions'
    if start_date or end_date:
        start_label = start_date.strftime('%d %b %Y') if start_date else 'Beginning'
        end_label = end_date.strftime('%d %b %Y') if end_date else 'Today'
        period_label = f'{start_label} to {end_label}'

    header_info = [
        Paragraph(f'<b>{business.name}</b>', title_style),
        Paragraph('Statement of Account', normal_style),
        Paragraph(period_label, normal_style),
        Paragraph('<br/>'.join(filter(None, [business.phone, business.email, business.location])) or 'No business contacts set', muted_style),
    ]
    header_table = Table([[logo_cell, header_info]], colWidths=[1.1 * inch, 5.8 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    client_details = [
        ['Client Name', client.full_name],
        ['Phone', client.phone_number or '-'],
        ['Email', client.email or '-'],
        ['Client Type', client.get_client_type_display()],
        ['Generated', timezone.localtime().strftime('%d %b %Y %H:%M')],
    ]
    client_table = Table(client_details, colWidths=[1.5 * inch, 4.8 * inch])
    client_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(client_table)
    story.append(Spacer(1, 12))

    table_data = [['Date', 'Service', 'Total Amount', 'Amount Paid', 'Balance', 'Running Balance', 'Status']]
    for row in statement_data['rows']:
        table_data.append([
            timezone.localtime(row['date']).strftime('%d %b %Y %H:%M'),
            row['service_name'],
            f"KSh {row['total_amount']:,.2f}",
            f"KSh {row['amount_paid']:,.2f}",
            f"KSh {row['balance']:,.2f}",
            f"KSh {row['running_balance']:,.2f}",
            row['status'],
        ])
    if len(table_data) == 1:
        table_data.append(['-', 'No transactions found for this period.', '-', '-', '-', '-', '-'])

    statement_table = Table(table_data, colWidths=[0.95 * inch, 1.8 * inch, 0.95 * inch, 0.95 * inch, 0.85 * inch, 1.0 * inch, 0.8 * inch], repeatRows=1)
    statement_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(statement_table)
    story.append(Spacer(1, 12))

    totals_table = Table([
        ['Total Amount', f"KSh {statement_data['total_amount']:,.2f}"],
        ['Total Paid', f"KSh {statement_data['total_paid']:,.2f}"],
        ['Outstanding Balance', f"KSh {statement_data['total_balance']:,.2f}"],
    ], colWidths=[2.2 * inch, 2.0 * inch])
    totals_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1, 2), (1, 2), colors.HexColor('#B91C1C')),
        ('PADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph('System: Meneja360°', muted_style))
    story.append(Paragraph('Signature: ______________________________', muted_style))

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    safe_name = client.full_name.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="statement_of_account_{safe_name}.pdf"'
    return response


class SupplierStatementView(LoginRequiredMixin, ReportsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/supplier_statement.html'

    def dispatch(self, request, *args, **kwargs):
        self.supplier_name = request.GET.get('supplier', '').strip()
        self.supplier_contact = request.GET.get('contact', '').strip()
        if not self.supplier_name:
            messages.error(request, 'Select a supplier to open the statement page.')
            return redirect('supplier_list')
        supplier_exists = SupplyExpense.objects.filter(
            business=self.get_business(),
            supplier_name=self.supplier_name,
        )
        if self.supplier_contact:
            supplier_exists = supplier_exists.filter(supplier_contact=self.supplier_contact)
        if not supplier_exists.exists():
            raise Http404("Supplier not found.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = self.get_business()
        start_date = _parse_statement_date(self.request.GET.get('start_date', '').strip())
        end_date = _parse_statement_date(self.request.GET.get('end_date', '').strip())
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date
        statement_data = _build_supplier_statement(
            business,
            self.supplier_name,
            self.supplier_contact,
            start_date=start_date,
            end_date=end_date,
        )

        context.update({
            'business': business,
            'supplier_name': self.supplier_name,
            'supplier_contact': self.supplier_contact,
            'statement_title': 'Supplier Statement',
            'statement_rows': statement_data['rows'],
            'total_amount': statement_data['total_amount'],
            'total_paid': statement_data['total_paid'],
            'total_balance': statement_data['total_balance'],
            'total_quantity': statement_data['total_quantity'],
            'start_date': start_date.isoformat() if start_date else '',
            'end_date': end_date.isoformat() if end_date else '',
            'date_range_applied': bool(start_date or end_date),
            'generated_at': timezone.localtime(),
        })
        return context


def export_supplier_statement_pdf(request):
    if not request.user.is_authenticated:
        raise Http404("Supplier not found.")

    business = get_user_business(request.user)
    supplier_name = request.GET.get('supplier', '').strip()
    supplier_contact = request.GET.get('contact', '').strip()
    if not supplier_name:
        raise Http404("Supplier not found.")

    supplier_exists = SupplyExpense.objects.filter(
        business=business,
        supplier_name=supplier_name,
    )
    if supplier_contact:
        supplier_exists = supplier_exists.filter(supplier_contact=supplier_contact)
    if not supplier_exists.exists():
        raise Http404("Supplier not found.")

    start_date = _parse_statement_date(request.GET.get('start_date', '').strip())
    end_date = _parse_statement_date(request.GET.get('end_date', '').strip())
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date
    statement_data = _build_supplier_statement(
        business,
        supplier_name,
        supplier_contact,
        start_date=start_date,
        end_date=end_date,
    )

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as ReportImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'SupplierStatementTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#12263A'),
    )
    normal_style = ParagraphStyle(
        'SupplierStatementBody',
        parent=styles['BodyText'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155'),
    )
    muted_style = ParagraphStyle(
        'SupplierStatementMuted',
        parent=normal_style,
        textColor=colors.HexColor('#64748B'),
    )

    story = []
    logo_cell = ''
    if business.logo:
        try:
            logo_cell = ReportImage(business.logo.path, width=0.9 * inch, height=0.9 * inch)
        except Exception:
            logo_cell = ''

    period_label = 'All supply records'
    if start_date or end_date:
        start_label = start_date.strftime('%d %b %Y') if start_date else 'Beginning'
        end_label = end_date.strftime('%d %b %Y') if end_date else 'Today'
        period_label = f'{start_label} to {end_label}'

    header_info = [
        Paragraph(f'<b>{business.name}</b>', title_style),
        Paragraph('Supplier Statement', normal_style),
        Paragraph(period_label, normal_style),
        Paragraph('<br/>'.join(filter(None, [business.phone, business.email, business.location])) or 'No business contacts set', muted_style),
    ]
    header_table = Table([[logo_cell, header_info]], colWidths=[1.1 * inch, 5.8 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    supplier_details = [
        ['Supplier', supplier_name],
        ['Contact', supplier_contact or '-'],
        ['Generated', timezone.localtime().strftime('%d %b %Y %H:%M')],
        ['Total Quantity', f"{statement_data['total_quantity']:,.2f}"],
    ]
    supplier_table = Table(supplier_details, colWidths=[1.5 * inch, 4.8 * inch])
    supplier_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(supplier_table)
    story.append(Spacer(1, 12))

    table_data = [['Date', 'Item', 'Qty', 'Unit Price', 'Total', 'Paid', 'Balance', 'Running Balance', 'Status']]
    for row in statement_data['rows']:
        table_data.append([
            timezone.localtime(row['date']).strftime('%d %b %Y %H:%M'),
            row['item_name'],
            f"{row['quantity']:,.2f}",
            f"KSh {row['unit_price']:,.2f}",
            f"KSh {row['amount']:,.2f}",
            f"KSh {row['amount_paid']:,.2f}",
            f"KSh {row['balance']:,.2f}",
            f"KSh {row['running_balance']:,.2f}",
            row['status'],
        ])
    if len(table_data) == 1:
        table_data.append(['-', 'No supply records found for this period.', '-', '-', '-', '-', '-', '-', '-'])

    statement_table = Table(
        table_data,
        colWidths=[0.9 * inch, 1.35 * inch, 0.5 * inch, 0.75 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 1.0 * inch, 0.65 * inch],
        repeatRows=1,
    )
    statement_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(statement_table)
    story.append(Spacer(1, 12))

    totals_table = Table([
        ['Total Supplied', f"KSh {statement_data['total_amount']:,.2f}"],
        ['Total Paid', f"KSh {statement_data['total_paid']:,.2f}"],
        ['Outstanding Balance', f"KSh {statement_data['total_balance']:,.2f}"],
    ], colWidths=[2.2 * inch, 2.0 * inch])
    totals_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1, 2), (1, 2), colors.HexColor('#B91C1C')),
        ('PADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph('System: Meneja360°', muted_style))
    story.append(Paragraph('Signature: ______________________________', muted_style))

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    safe_name = supplier_name.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="supplier_statement_{safe_name}.pdf"'
    return response


def _get_transaction_for_user(user, pk):
    business = get_user_business(user)
    transaction = (
        Transaction.objects.filter(
            pk=pk,
            business=business,
        )
        .select_related('client')
        .prefetch_related('items')
        .first()
    )
    if transaction is None:
        raise Http404("Transaction not found.")
    return business, transaction


class TransactionReceiptView(LoginRequiredMixin, RecordsRequiredMixin, UserBusinessMixin, TemplateView):
    template_name = 'core/transaction_receipt.html'

    def get_transaction(self):
        _, transaction = _get_transaction_for_user(self.request.user, self.kwargs['pk'])
        return transaction

    def dispatch(self, request, *args, **kwargs):
        transaction = self.get_transaction()
        if transaction.status != Transaction.PAID:
            messages.error(request, 'A receipt is available only for fully paid cash sales.')
            return redirect('transaction_list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transaction = self.get_transaction()
        context.update({
            'business': self.get_business(),
            'transaction': transaction,
            'receipt_number': transaction.receipt_number,
            'receipt_generated_at': timezone.localtime(),
            'tax_amount': transaction.document_tax_amount,
            'grand_total': transaction.document_grand_total,
        })
        return context


class TransactionInvoiceView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, UpdateView):
    model = Transaction
    form_class = InvoiceSettingsForm
    template_name = 'core/transaction_invoice.html'

    def get_queryset(self):
        return super().get_queryset().select_related('client').prefetch_related('items')

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status == Transaction.PAID:
            messages.info(request, 'This transaction is fully paid. Print a receipt instead of generating an invoice.')
            return redirect('transaction_detail', pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        if self.object.invoice_due_date is None:
            initial['invoice_due_date'] = self.object.date.date() + timedelta(days=7)
        return initial

    def form_valid(self, form):
        messages.success(self.request, f'Invoice settings saved for {self.object.invoice_number}.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('transaction_invoice', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transaction = self.object
        context.update({
            'business': self.get_business(),
            'transaction': transaction,
            'invoice_number': transaction.invoice_number,
            'invoice_date': transaction.date.date(),
            'invoice_due_date': transaction.invoice_due_date or (transaction.date.date() + timedelta(days=7)),
            'subtotal': transaction.document_subtotal,
            'discount_amount': transaction.document_discount_amount,
            'tax_amount': transaction.document_tax_amount,
            'grand_total': transaction.document_grand_total,
            'balance_due': transaction.invoice_balance_due,
        })
        return context


class TransactionDetailView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, TemplateView):
    template_name = 'core/transaction_detail.html'

    def get_transaction(self):
        _, transaction = _get_transaction_for_user(self.request.user, self.kwargs['pk'])
        return transaction

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transaction = self.get_transaction()

        if transaction.status == Transaction.PAID:
            recommendation_title = 'Ready to Print Receipt'
            recommendation_message = 'This transaction is fully paid, so the fastest next step is printing a cash sale receipt.'
            primary_action = {
                'label': 'Print Receipt',
                'url': reverse('transaction_receipt', kwargs={'pk': transaction.pk}),
            }
        elif transaction.status == Transaction.PARTIAL:
            recommendation_title = 'Generate Invoice'
            recommendation_message = 'This transaction is partially paid, so an invoice is the better document to show the remaining balance due.'
            primary_action = {
                'label': 'Open Invoice',
                'url': reverse('transaction_invoice', kwargs={'pk': transaction.pk}),
            }
        else:
            recommendation_title = 'Invoice Recommended'
            recommendation_message = 'This transaction is unpaid, so an invoice is recommended instead of a receipt.'
            primary_action = {
                'label': 'Open Invoice',
                'url': reverse('transaction_invoice', kwargs={'pk': transaction.pk}),
            }

        context.update({
            'business': self.get_business(),
            'transaction': transaction,
            'recommendation_title': recommendation_title,
            'recommendation_message': recommendation_message,
            'primary_action': primary_action,
            'show_invoice_actions': transaction.status != Transaction.PAID,
        })
        return context


def export_transaction_receipt_pdf(request, pk):
    business, transaction = _get_transaction_for_user(request.user, pk)
    if transaction.status != Transaction.PAID:
        messages.error(request, 'Only fully paid transactions can generate receipt PDFs.')
        return redirect('transaction_detail', pk=transaction.pk)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=28, rightMargin=28, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReceiptTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, alignment=1)
    body_style = ParagraphStyle('ReceiptBody', parent=styles['BodyText'], fontSize=9, leading=12)
    story = []

    story.append(Paragraph('CASH RECEIPT', title_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(business.name, body_style))
    contact_lines = '<br/>'.join(filter(None, [business.phone, business.email, business.location]))
    if contact_lines:
        story.append(Paragraph(contact_lines, body_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Receipt No:</b> {transaction.receipt_number}", body_style))
    story.append(Paragraph(f"<b>Date:</b> {timezone.localtime(transaction.date).strftime('%d %b %Y %H:%M')}", body_style))
    story.append(Paragraph(f"<b>Client:</b> {transaction.client.full_name if transaction.client else 'Walk-in Customer'}", body_style))
    story.append(Spacer(1, 10))

    item_rows = [['No.', 'Service Name', 'Units', 'Price', 'Total']]
    for index, item in enumerate(transaction.items.all(), start=1):
        item_rows.append([
            str(index),
            item.description,
            str(item.quantity),
            f"KSh {item.unit_price:,.2f}",
            f"KSh {item.line_total:,.2f}",
        ])
    item_table = Table(item_rows, colWidths=[0.45 * inch, 2.7 * inch, 0.7 * inch, 1.0 * inch, 1.0 * inch], repeatRows=1)
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 10))

    summary_table = Table([
        ['Subtotal', f"KSh {transaction.document_subtotal:,.2f}"],
        ['Tax', f"KSh {transaction.document_tax_amount:,.2f}"],
        ['Grand Total', f"KSh {transaction.document_grand_total:,.2f}"],
    ], colWidths=[1.7 * inch, 1.5 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph('Thank you for your business.', body_style))
    if transaction.document_notes:
        story.append(Paragraph(f"<b>Comments:</b> {transaction.document_notes}", body_style))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{transaction.receipt_number.lower()}.pdf"'
    return response


def export_transaction_invoice_pdf(request, pk):
    business, transaction = _get_transaction_for_user(request.user, pk)
    if transaction.status == Transaction.PAID:
        messages.info(request, 'This transaction is fully paid. Use the receipt PDF instead.')
        return redirect('transaction_detail', pk=transaction.pk)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('InvoiceTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor('#12263A'))
    body_style = ParagraphStyle('InvoiceBody', parent=styles['BodyText'], fontSize=9, leading=12)
    story = []

    story.append(Paragraph('INVOICE', title_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(business.name, body_style))
    contact_lines = '<br/>'.join(filter(None, [business.phone, business.email, business.location]))
    if contact_lines:
        story.append(Paragraph(contact_lines, body_style))
    story.append(Spacer(1, 8))

    meta_table = Table([
        [Paragraph('<b>Invoice</b>', body_style), f"Invoice No: {transaction.invoice_number}"],
        [f"Date: {transaction.date.strftime('%d %b %Y')}", f"Due Date: {(transaction.invoice_due_date or (transaction.date.date() + timedelta(days=7))).strftime('%d %b %Y')}"],
        [f"Client: {transaction.client.full_name if transaction.client else 'Walk-in Customer'}", f"Status: {transaction.get_status_display()}"],
    ], colWidths=[3.1 * inch, 3.1 * inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    bill_to_rows = [
        ['Name', transaction.client.full_name if transaction.client else 'Walk-in Customer'],
        ['Company', transaction.client.company_name if transaction.client and transaction.client.company_name else '-'],
        ['Address', transaction.client.address if transaction.client and transaction.client.address else '-'],
        ['Phone', transaction.client.phone_number if transaction.client and transaction.client.phone_number else '-'],
        ['Email', transaction.client.email if transaction.client and transaction.client.email else '-'],
    ]
    bill_to_table = Table(bill_to_rows, colWidths=[1.1 * inch, 5.2 * inch])
    bill_to_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(bill_to_table)
    story.append(Spacer(1, 10))

    item_rows = [['Service Name', 'Quantity', 'Unit Price', 'Total']]
    for item in transaction.items.all():
        item_rows.append([
            item.description,
            str(item.quantity),
            f"KSh {item.unit_price:,.2f}",
            f"KSh {item.line_total:,.2f}",
        ])
    item_table = Table(item_rows, colWidths=[3.0 * inch, 1.0 * inch, 1.15 * inch, 1.15 * inch], repeatRows=1)
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 10))

    summary_table = Table([
        ['Subtotal', f"KSh {transaction.document_subtotal:,.2f}"],
        ['Discount', f"KSh {transaction.document_discount_amount:,.2f}"],
        ['Tax Rate', f"{transaction.invoice_tax_rate}%"],
        ['Total Tax', f"KSh {transaction.document_tax_amount:,.2f}"],
        ['Final Amount', f"KSh {transaction.document_grand_total:,.2f}"],
        ['Balance Due', f"KSh {transaction.invoice_balance_due:,.2f}"],
    ], colWidths=[1.7 * inch, 1.6 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 4), (-1, 5), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1, 5), (1, 5), colors.HexColor('#B91C1C')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Remarks / Payment Instructions:</b> {transaction.document_notes or 'Payment due by the invoice due date.'}", body_style))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{transaction.invoice_number.lower()}.pdf"'
    return response


# transaction
class TransactionListView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, ListView):
    model = Transaction
    template_name = 'core/transaction_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        # filtering by GET params
        search = self.request.GET.get('search', '').strip()
        status = self.request.GET.get('status')
        client = self.request.GET.get('client')
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if search:
            qs = qs.filter(
                Q(service_name__icontains=search) |
                Q(client__full_name__icontains=search)
            )
        if status:
            qs = qs.filter(status=status)
        if client:
            qs = qs.filter(client__id=client)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class TransactionCreateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'core/transaction_form.html'
    success_url = reverse_lazy('transaction_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = getattr(self, 'object', None)
        if self.request.POST:
            context['item_formset'] = TransactionLineItemFormSet(self.request.POST, instance=instance, prefix='items')
        else:
            context['item_formset'] = TransactionLineItemFormSet(instance=instance, prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        item_formset = context['item_formset']
        if not item_formset.is_valid():
            return self.form_invalid(form)

        with db_transaction.atomic():
            self.object = form.save(commit=False)
            if not self.object.service_name:
                self.object.service_name = 'Pending items'
            self.object.unit_price = 0
            self.object.quantity = 1
            self.object.save()
            item_formset.instance = self.object
            item_formset.save()
            self.object.sync_primary_item_fields()
            self.object.recalculate_totals()
            self.object.save(update_fields=[
                'service_name',
                'unit_price',
                'quantity',
                'total_amount',
                'balance',
                'status',
            ])
            if self.object.client:
                TransactionForm._recalculate_client_totals(self.object.client)
        return redirect(self.success_url)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class TransactionUpdateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, BusinessScopedQuerysetMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'core/transaction_form.html'
    success_url = reverse_lazy('transaction_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['item_formset'] = TransactionLineItemFormSet(self.request.POST, instance=self.object, prefix='items')
        else:
            context['item_formset'] = TransactionLineItemFormSet(instance=self.object, prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        item_formset = context['item_formset']
        if not item_formset.is_valid():
            return self.form_invalid(form)

        previous_client = self.object.client
        with db_transaction.atomic():
            self.object = form.save(commit=False)
            if not self.object.service_name:
                self.object.service_name = 'Pending items'
            self.object.unit_price = 0
            self.object.quantity = 1
            self.object.save()
            item_formset.instance = self.object
            item_formset.save()
            self.object.sync_primary_item_fields()
            self.object.recalculate_totals()
            self.object.save(update_fields=[
                'client',
                'service_name',
                'unit_price',
                'quantity',
                'amount_paid',
                'invoice_tax_rate',
                'total_amount',
                'balance',
                'status',
            ])
            if previous_client and (not self.object.client or previous_client.pk != self.object.client.pk):
                TransactionForm._recalculate_client_totals(previous_client)
            if self.object.client:
                TransactionForm._recalculate_client_totals(self.object.client)
        return redirect(self.success_url)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class TransactionDeleteView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, DeleteView):
    model = Transaction
    template_name = 'core/transaction_confirm_delete.html'
    success_url = reverse_lazy('transaction_list')


# expense
class ExpenseListView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, ListView):
    model = Expense
    template_name = 'core/expense_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get('search', '').strip()
        category = self.request.GET.get('category')
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if search:
            qs = qs.filter(
                Q(description__icontains=search) |
                Q(category__icontains=search)
            )
        qs = qs.exclude(category=Expense.SUPPLIES)
        if category:
            qs = qs.filter(category=category)
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class ExpenseCreateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'core/expense_form.html'
    success_url = reverse_lazy('expense_list')


class ExpenseUpdateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, BusinessScopedQuerysetMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'core/expense_form.html'
    success_url = reverse_lazy('expense_list')


class ExpenseDeleteView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, DeleteView):
    model = Expense
    template_name = 'core/expense_confirm_delete.html'
    success_url = reverse_lazy('expense_list')


class SupplyExpenseListView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, ListView):
    model = SupplyExpense
    template_name = 'core/supply_expense_list.html'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('items')
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(supplier_name__icontains=search) |
                Q(supplier_contact__icontains=search) |
                Q(item_name__icontains=search) |
                Q(items__item_name__icontains=search) |
                Q(items__description__icontains=search) |
                Q(description__icontains=search)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        return context


class SupplyExpenseCreateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, CreateView):
    model = SupplyExpense
    form_class = SupplyExpenseForm
    template_name = 'core/supply_expense_form.html'
    success_url = reverse_lazy('supply_expense_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = getattr(self, 'object', None)
        if self.request.POST:
            context['item_formset'] = SupplyExpenseLineItemFormSet(self.request.POST, instance=instance, prefix='items')
        else:
            context['item_formset'] = SupplyExpenseLineItemFormSet(instance=instance, prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        item_formset = context['item_formset']
        if not item_formset.is_valid():
            return self.form_invalid(form)

        subtotal = Decimal('0.00')
        for item_form in item_formset.forms:
            if not hasattr(item_form, 'cleaned_data') or not item_form.cleaned_data or item_form.cleaned_data.get('DELETE'):
                continue
            quantity = item_form.cleaned_data.get('quantity') or Decimal('0.00')
            unit_price = item_form.cleaned_data.get('unit_price') or Decimal('0.00')
            subtotal += quantity * unit_price
        amount_paid = form.cleaned_data.get('amount_paid') or Decimal('0.00')
        if amount_paid > subtotal:
            form.add_error('amount_paid', 'Amount paid cannot be greater than the total supplied amount.')
            return self.form_invalid(form)

        with db_transaction.atomic():
            self.object = form.save(commit=False)
            self.object.item_name = 'Pending items'
            self.object.quantity = Decimal('1.00')
            self.object.unit_price = Decimal('0.00')
            self.object.save()
            item_formset.instance = self.object
            item_formset.save()
            self.object.sync_primary_item_fields()
            self.object.recalculate_totals()
            self.object.save(update_fields=[
                'date',
                'supplier_name',
                'supplier_contact',
                'item_name',
                'description',
                'quantity',
                'unit_price',
                'amount',
                'amount_paid',
                'balance',
                'status',
            ])
        return redirect(self.success_url)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class SupplyExpenseUpdateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, BusinessScopedQuerysetMixin, UpdateView):
    model = SupplyExpense
    form_class = SupplyExpenseForm
    template_name = 'core/supply_expense_form.html'
    success_url = reverse_lazy('supply_expense_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['item_formset'] = SupplyExpenseLineItemFormSet(self.request.POST, instance=self.object, prefix='items')
        else:
            context['item_formset'] = SupplyExpenseLineItemFormSet(instance=self.object, prefix='items')
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        item_formset = context['item_formset']
        if not item_formset.is_valid():
            return self.form_invalid(form)

        subtotal = Decimal('0.00')
        for item_form in item_formset.forms:
            if not hasattr(item_form, 'cleaned_data') or not item_form.cleaned_data or item_form.cleaned_data.get('DELETE'):
                continue
            quantity = item_form.cleaned_data.get('quantity') or Decimal('0.00')
            unit_price = item_form.cleaned_data.get('unit_price') or Decimal('0.00')
            subtotal += quantity * unit_price
        amount_paid = form.cleaned_data.get('amount_paid') or Decimal('0.00')
        if amount_paid > subtotal:
            form.add_error('amount_paid', 'Amount paid cannot be greater than the total supplied amount.')
            return self.form_invalid(form)

        with db_transaction.atomic():
            self.object = form.save(commit=False)
            self.object.item_name = self.object.item_name or 'Pending items'
            self.object.save()
            item_formset.instance = self.object
            item_formset.save()
            self.object.sync_primary_item_fields()
            self.object.recalculate_totals()
            self.object.save(update_fields=[
                'date',
                'supplier_name',
                'supplier_contact',
                'item_name',
                'description',
                'quantity',
                'unit_price',
                'amount',
                'amount_paid',
                'balance',
                'status',
            ])
        return redirect(self.success_url)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class SupplyExpenseDeleteView(LoginRequiredMixin, RecordsRequiredMixin, BusinessScopedQuerysetMixin, DeleteView):
    model = SupplyExpense
    template_name = 'core/expense_confirm_delete.html'
    success_url = reverse_lazy('supply_expense_list')


# authentication
class LoginView(AuthLoginView):
    template_name = 'core/login.html'

    def get_success_url(self):
        next_url = self.get_redirect_url()
        if next_url:
            return next_url
        if self.request.user.is_superuser:
            return reverse('super_admin_dashboard')
        return reverse('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        state, _business = get_business_access_state(self.request.user)
        if state == 'expired':
            messages.error(self.request, 'Your subscription has expired. Please contact the system administrator.')
            return redirect('inactive_subscription')
        if state == 'inactive':
            messages.error(self.request, 'This client account has been deactivated. Please contact the system administrator.')
            return redirect('inactive_subscription')
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.require_password_change:
            messages.warning(self.request, 'Please change your temporary password before continuing.')
            return redirect('password_change')
        return response

    def form_invalid(self, form):
        username = self.request.POST.get('username', '').strip()
        if username:
            try:
                user = User.objects.get(username=username)
                business = getattr(user, 'business_profile', None)
                if not user.is_active and business and business.approval_status == BusinessProfile.APPROVAL_PENDING:
                    messages.error(self.request, 'Your account is pending super admin approval. You will be able to log in after approval.')
                elif not user.is_active and business and business.approval_status == BusinessProfile.APPROVAL_REJECTED:
                    messages.error(self.request, 'This account request was rejected. Contact the system administrator for help.')
            except User.DoesNotExist:
                pass
        return super().form_invalid(form)


class RegisterView(FormView):
    template_name = 'core/register.html'
    form_class = RegistrationForm
    success_url = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Your account request has been submitted successfully and is now pending super admin approval.')
        return super().form_valid(form)


class PasswordReset(AuthPasswordResetView):
    template_name = 'core/password_reset_form.html'
    email_template_name = 'core/password_reset_email.html'
    subject_template_name = 'core/password_reset_subject.txt'
    from_email = settings.DEFAULT_FROM_EMAIL
    success_url = reverse_lazy('password_reset_done')


class PasswordResetDone(AuthPasswordResetDoneView):
    template_name = 'core/password_reset_done.html'


class PasswordResetConfirm(AuthPasswordResetConfirmView):
    template_name = 'core/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


class PasswordResetComplete(AuthPasswordResetCompleteView):
    template_name = 'core/password_reset_complete.html'


class PasswordChange(AuthPasswordChangeView):
    template_name = 'core/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        response = super().form_valid(form)
        profile = getattr(self.request.user, 'profile', None)
        if profile:
            profile.require_password_change = False
            profile.password_changed_date = timezone.now()
            profile.save(update_fields=['require_password_change', 'password_changed_date'])
        messages.success(self.request, 'Your password has been changed successfully.')
        return response


class PasswordChangeDone(AuthPasswordChangeDoneView):
    template_name = 'core/password_change_done.html'


def LogoutView(request):
    logout(request)
    return redirect('login')


class InactiveSubscriptionView(LoginRequiredMixin, TemplateView):
    template_name = 'core/inactive_subscription.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state, business = get_business_access_state(self.request.user)
        context.update({
            'business': business,
            'access_state': state,
        })
        return context


# placeholder report view
def report_index(request):
    # gather some basic aggregates
    if not request.user.is_authenticated:
        return redirect('login')
    if not can_backup_restore(request.user):
        messages.error(request, 'Only the business owner can create backups.')
        return redirect('dashboard')
    business = get_user_business(request.user)
    from django.db.models import Sum
    data = {}
    data['total_revenue'] = Transaction.objects.filter(business=business).aggregate(total=Sum('total_amount'))['total'] or 0
    data['total_expense'] = combined_expense_total(business)
    return render(request, 'core/reports.html', {'data': data, 'business': business})


# backup / restore views
import os
from django.conf import settings
from django.http import HttpResponse

def backup(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if not can_backup_restore(request.user):
        messages.error(request, 'Only the business owner can create backups.')
        return redirect('dashboard')
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
    if not can_backup_restore(request.user):
        messages.error(request, 'Only the business owner can restore backups.')
        return redirect('dashboard')
    if request.method == 'POST' and request.FILES.get('dbfile'):
        db_path = settings.DATABASES['default']['NAME']
        uploaded = request.FILES['dbfile']
        with open(db_path, 'wb') as f:
            for chunk in uploaded.chunks():
                f.write(chunk)
        return redirect('dashboard')
    return render(request, 'core/restore.html')
