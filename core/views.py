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
from django.urls import reverse_lazy
from django.conf import settings
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta
from .models import BusinessProfile, Client, Transaction, Expense
from .auth_security import UserProfile
from .forms import BusinessProfileForm, ClientForm, TransactionForm, ExpenseForm, RegistrationForm, StaffUserCreationForm, TeamMemberUpdateForm
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
        today_expenses = Expense.objects.filter(
            business=business,
            date__range=(today_start, today_end)
        ).aggregate(total=Sum('amount'))['total'] or 0

        expense_by_category = Expense.objects.filter(
            business=business,
            date__range=(today_start, today_end)
        ).values('category').annotate(total=Sum('amount')).order_by('-total')
        category_labels_map = dict(Expense.CATEGORY_CHOICES)
        today_expense_breakdown = [
            {
                'category': category_labels_map.get(item['category'], item['category'].title()),
                'total': float(item['total'] or 0)
            }
            for item in expense_by_category
        ]
        daily_start = datetime.combine(selected_date, datetime.min.time())
        daily_end = datetime.combine(selected_date, datetime.max.time())
        selected_date_str = selected_date.isoformat()

        daily_revenue = Transaction.objects.filter(
            business=business,
            date__range=(daily_start, daily_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        daily_expenses = Expense.objects.filter(
            business=business,
            date__range=(daily_start, daily_end)
        ).aggregate(total=Sum('amount'))['total'] or 0

        daily_profit = daily_revenue - daily_expenses

        # Weekly metrics for selected date
        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        weekly_expenses = Expense.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount'))['total'] or 0
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
        monthly_expenses = Expense.objects.filter(
            business=business,
            date__date__range=(month_start.date(), month_end.date())
        ).aggregate(total=Sum('amount'))['total'] or 0
        monthly_profit = monthly_revenue - monthly_expenses

        # Net profit shown as selected daily profit
        net_profit = daily_profit

        # Total outstanding balance
        total_outstanding = Client.objects.filter(
            business=business
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

        # Recent transactions (last 10)
        recent_transactions = Transaction.objects.filter(
            business=business
        ).select_related('client').order_by('-date')[:10]

        # Recent expenses (last 10)
        recent_expenses = Expense.objects.filter(
            business=business
        ).order_by('-date')[:10]

        # Monthly data for the selected year (for graphs)
        monthly_data = []
        for month in range(1, 13):
            month_start = datetime(selected_year, month, 1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

            revenue = Transaction.objects.filter(
                business=business,
                date__date__range=(month_start.date(), month_end.date())
            ).aggregate(total=Sum('amount_paid'))['total'] or 0

            expenses = Expense.objects.filter(
                business=business,
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
        daily_expense = Expense.objects.filter(
            business=business,
            date__range=(day_start, day_end)
        ).aggregate(total=Sum('amount'))['total'] or 0
        daily_profit = daily_revenue - daily_expense

        week_start = selected_date - timedelta(days=selected_date.weekday())
        week_end = week_start + timedelta(days=6)
        weekly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        weekly_expense = Expense.objects.filter(
            business=business,
            date__date__range=(week_start, week_end)
        ).aggregate(total=Sum('amount'))['total'] or 0
        weekly_profit = weekly_revenue - weekly_expense

        month_begin = datetime(selected_year, sel_month_int, 1)
        month_end = (month_begin + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        monthly_revenue = Transaction.objects.filter(
            business=business,
            date__date__range=(month_begin.date(), month_end.date())
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        monthly_expense = Expense.objects.filter(
            business=business,
            date__date__range=(month_begin.date(), month_end.date())
        ).aggregate(total=Sum('amount'))['total'] or 0
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


class TransactionUpdateView(LoginRequiredMixin, RecordsRequiredMixin, BusinessFormMixin, BusinessScopedQuerysetMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'core/transaction_form.html'
    success_url = reverse_lazy('transaction_list')


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


# authentication
class LoginView(AuthLoginView):
    template_name = 'core/login.html'


class RegisterView(FormView):
    template_name = 'core/register.html'
    form_class = RegistrationForm
    success_url = reverse_lazy('dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        auth_login(self.request, user)
        messages.success(self.request, 'Your account has been created successfully.')
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


class PasswordChangeDone(AuthPasswordChangeDoneView):
    template_name = 'core/password_change_done.html'


def LogoutView(request):
    logout(request)
    return redirect('login')


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
    data['total_expense'] = Expense.objects.filter(business=business).aggregate(total=Sum('amount'))['total'] or 0
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
