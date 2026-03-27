from datetime import datetime, timedelta
import secrets

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import models
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .auth_security import ActivityLog, UserProfile
from .models import BusinessProfile, Payment
from .super_admin_forms import SuperAdminClientForm, SuperAdminPaymentForm


def _get_selected_report_date(request):
    today = timezone.localdate()
    raw_year = request.GET.get('year')
    raw_month = request.GET.get('month')
    raw_day = request.GET.get('day')

    try:
        year = int(raw_year) if raw_year else today.year
    except (TypeError, ValueError):
        year = today.year

    try:
        month = int(raw_month) if raw_month else today.month
    except (TypeError, ValueError):
        month = today.month

    try:
        day = int(raw_day) if raw_day else today.day
    except (TypeError, ValueError):
        day = today.day

    month = max(1, min(12, month))
    last_day = (datetime(year + (month == 12), 1 if month == 12 else month + 1, 1).date() - timedelta(days=1)).day
    day = max(1, min(last_day, day))
    return datetime(year, month, day).date()


class SuperAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'

    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, 'Only the system super admin can access this area.')
        if self.request.user.is_authenticated:
            return redirect('dashboard')
        return super().handle_no_permission()


class SuperAdminDashboardView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'core/super_admin/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = _get_selected_report_date(self.request)
        today = timezone.localdate()
        active_clients = BusinessProfile.objects.filter(is_active=True).exclude(subscription_end_date__lt=today)
        expired_clients = BusinessProfile.objects.filter(subscription_end_date__lt=today)
        filtered_payments = Payment.objects.filter(
            payment_date__year=selected_date.year,
            payment_date__month=selected_date.month,
        )
        monthly_revenue = Payment.objects.filter(
            payment_date__year=selected_date.year,
            payment_date__month=selected_date.month,
        ).aggregate(total=Sum('amount'))['total'] or 0
        daily_revenue = Payment.objects.filter(payment_date=selected_date).aggregate(total=Sum('amount'))['total'] or 0
        yearly_revenue = Payment.objects.filter(payment_date__year=selected_date.year).aggregate(total=Sum('amount'))['total'] or 0
        context.update({
            'total_clients': BusinessProfile.objects.count(),
            'active_clients': active_clients.count(),
            'expired_clients': expired_clients.count(),
            'total_users': UserProfile.objects.count(),
            'monthly_revenue': monthly_revenue,
            'daily_revenue': daily_revenue,
            'yearly_revenue': yearly_revenue,
            'selected_date': selected_date,
            'selected_year': selected_date.year,
            'selected_month': selected_date.month,
            'selected_day': selected_date.day,
            'year_options': list(range(today.year - 5, today.year + 2)),
            'month_options': range(1, 13),
            'day_options': range(1, 32),
            'near_expiry_clients': BusinessProfile.objects.filter(
                is_active=True,
                subscription_end_date__gte=today,
                subscription_end_date__lte=today + timedelta(days=3),
            ).order_by('subscription_end_date')[:8],
            'recent_payments': filtered_payments.select_related('business').order_by('-payment_date', '-created_at')[:8],
        })
        return context


class SuperAdminRevenueBreakdownView(SuperAdminRequiredMixin, TemplateView):
    template_name = 'core/super_admin/revenue_breakdown.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = _get_selected_report_date(self.request)
        daily_payments = Payment.objects.filter(payment_date=selected_date).select_related('business').order_by('-created_at')
        monthly_payments = Payment.objects.filter(
            payment_date__year=selected_date.year,
            payment_date__month=selected_date.month,
        ).select_related('business').order_by('-payment_date', '-created_at')
        yearly_payments = Payment.objects.filter(
            payment_date__year=selected_date.year
        ).select_related('business').order_by('-payment_date', '-created_at')

        context.update({
            'selected_date': selected_date,
            'selected_year': selected_date.year,
            'selected_month': selected_date.month,
            'selected_day': selected_date.day,
            'year_options': list(range(timezone.localdate().year - 5, timezone.localdate().year + 2)),
            'month_options': range(1, 13),
            'day_options': range(1, 32),
            'daily_revenue': daily_payments.aggregate(total=Sum('amount'))['total'] or 0,
            'monthly_revenue': monthly_payments.aggregate(total=Sum('amount'))['total'] or 0,
            'yearly_revenue': yearly_payments.aggregate(total=Sum('amount'))['total'] or 0,
            'daily_payments': daily_payments[:25],
            'monthly_payments': monthly_payments[:50],
            'yearly_payments': yearly_payments[:50],
        })
        return context


class SuperAdminClientListView(SuperAdminRequiredMixin, ListView):
    model = BusinessProfile
    template_name = 'core/super_admin/client_list.html'
    context_object_name = 'clients'
    paginate_by = 25

    def get_queryset(self):
        queryset = BusinessProfile.objects.select_related('owner').annotate(user_count=Count('user_profiles'))
        search = self.request.GET.get('search', '').strip()
        status = self.request.GET.get('status', '').strip()
        today = timezone.localdate()

        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(owner_name__icontains=search) |
                models.Q(owner__username__icontains=search) |
                models.Q(email__icontains=search)
            )
        if status == 'expired':
            queryset = queryset.filter(subscription_end_date__lt=today)
        elif status == 'active':
            queryset = queryset.filter(is_active=True).exclude(subscription_end_date__lt=today)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        elif status == 'near_expiry':
            queryset = queryset.filter(
                is_active=True,
                subscription_end_date__gte=today,
                subscription_end_date__lte=today + timedelta(days=3),
            )
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        status_titles = {
            'active': 'Active Clients',
            'expired': 'Expired Clients',
            'inactive': 'Inactive Clients',
            'near_expiry': 'Near Expiry Clients',
        }
        context['list_title'] = status_titles.get(context['status_filter'], 'All Clients')
        return context


class SuperAdminClientDetailView(SuperAdminRequiredMixin, DetailView):
    model = BusinessProfile
    template_name = 'core/super_admin/client_detail.html'
    context_object_name = 'client_business'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        business = self.object
        context.update({
            'user_count': business.user_profiles.count(),
            'payment_history': business.payments.order_by('-payment_date', '-created_at')[:20],
            'recent_activity': ActivityLog.objects.filter(business=business).select_related('user')[:15],
            'recent_users': business.user_profiles.select_related('user').order_by('-updated_at')[:10],
        })
        return context


class SuperAdminClientCreateView(SuperAdminRequiredMixin, CreateView):
    form_class = SuperAdminClientForm
    template_name = 'core/super_admin/client_form.html'

    def get_success_url(self):
        return reverse('super_admin_client_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, f'Client "{self.object.name}" created successfully.')
        return redirect(self.get_success_url())


class SuperAdminClientUpdateView(SuperAdminRequiredMixin, UpdateView):
    model = BusinessProfile
    form_class = SuperAdminClientForm
    template_name = 'core/super_admin/client_form.html'
    context_object_name = 'client_business'

    def get_success_url(self):
        return reverse('super_admin_client_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, f'Client "{self.object.name}" updated successfully.')
        return redirect(self.get_success_url())


class SuperAdminPaymentListView(SuperAdminRequiredMixin, ListView):
    model = Payment
    template_name = 'core/super_admin/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 30

    def get_queryset(self):
        queryset = Payment.objects.select_related('business', 'recorded_by')
        business_id = self.request.GET.get('business')
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['businesses'] = BusinessProfile.objects.order_by('name')
        context['selected_business'] = self.request.GET.get('business', '')
        return context


class SuperAdminPaymentCreateView(SuperAdminRequiredMixin, CreateView):
    model = Payment
    form_class = SuperAdminPaymentForm
    template_name = 'core/super_admin/payment_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.business = get_object_or_404(BusinessProfile, pk=self.kwargs['business_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client_business'] = self.business
        return context

    def get_success_url(self):
        return reverse('super_admin_client_detail', kwargs={'pk': self.business.pk})

    def form_valid(self, form):
        payment = form.save(commit=False)
        payment.business = self.business
        payment.recorded_by = self.request.user
        payment.save()

        start_date = self.business.subscription_end_date or payment.payment_date
        if start_date < payment.payment_date:
            start_date = payment.payment_date
        self.business.subscription_start_date = payment.payment_date
        self.business.subscription_end_date = start_date + timedelta(days=payment.duration_days)
        self.business.is_active = True
        self.business.save(update_fields=['subscription_start_date', 'subscription_end_date', 'is_active'])

        messages.success(self.request, f'Payment recorded and subscription extended for "{self.business.name}".')
        return redirect(self.get_success_url())


class SuperAdminUserListView(SuperAdminRequiredMixin, ListView):
    model = UserProfile
    template_name = 'core/super_admin/user_list.html'
    context_object_name = 'user_profiles'
    paginate_by = 30

    def get_queryset(self):
        queryset = UserProfile.objects.select_related('user', 'business').order_by('business__name', 'user__username')
        business_id = self.request.GET.get('business')
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['businesses'] = BusinessProfile.objects.order_by('name')
        context['selected_business'] = self.request.GET.get('business', '')
        return context


@require_POST
def super_admin_delete_user(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Only the system super admin can perform this action.')
        return redirect('dashboard')

    target_user = get_object_or_404(User, pk=pk)

    if target_user == request.user:
        messages.error(request, 'You cannot delete the currently logged-in super admin account.')
        return redirect('super_admin_user_list')

    if target_user.is_superuser:
        messages.error(request, 'Super admin accounts cannot be deleted from this screen.')
        return redirect('super_admin_user_list')

    owned_business = getattr(target_user, 'business_profile', None)
    if owned_business is not None:
        messages.error(
            request,
            f'Cannot delete {target_user.username} because the account owns "{owned_business.name}". '
            'Transfer or remove the client business first.'
        )
        return redirect('super_admin_user_list')

    business = getattr(getattr(target_user, 'profile', None), 'business', None)
    username = target_user.username
    target_user.delete()

    ActivityLog.objects.create(
        user=request.user,
        action='delete',
        description=f'Super admin deleted user account {username}.',
        business=business,
        related_object_type='User',
        related_object_id=pk,
    )

    messages.success(request, f'User "{username}" was deleted successfully.')
    return redirect('super_admin_user_list')


class SuperAdminActivityLogListView(SuperAdminRequiredMixin, ListView):
    model = ActivityLog
    template_name = 'core/super_admin/activity_list.html'
    context_object_name = 'logs'
    paginate_by = 40

    def get_queryset(self):
        queryset = ActivityLog.objects.select_related('user', 'business')
        business_id = self.request.GET.get('business')
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['businesses'] = BusinessProfile.objects.order_by('name')
        context['selected_business'] = self.request.GET.get('business', '')
        return context


def super_admin_toggle_client_status(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Only the system super admin can perform this action.')
        return redirect('dashboard')
    business = get_object_or_404(BusinessProfile, pk=pk)
    business.is_active = not business.is_active
    business.save(update_fields=['is_active'])
    state = 'activated' if business.is_active else 'deactivated'
    messages.success(request, f'Client "{business.name}" {state}.')
    return redirect('super_admin_client_detail', pk=business.pk)


def super_admin_extend_subscription(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Only the system super admin can perform this action.')
        return redirect('dashboard')
    business = get_object_or_404(BusinessProfile, pk=pk)
    days = int(request.POST.get('days', '30') or 30)
    today = timezone.localdate()
    start_date = business.subscription_end_date if business.subscription_end_date and business.subscription_end_date > today else today
    business.subscription_start_date = today
    business.subscription_end_date = start_date + timedelta(days=days)
    business.is_active = True
    business.save(update_fields=['subscription_start_date', 'subscription_end_date', 'is_active'])
    messages.success(request, f'Subscription extended by {days} days for "{business.name}".')
    return redirect('super_admin_client_detail', pk=business.pk)


def super_admin_impersonate_client(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Only the system super admin can perform this action.')
        return redirect('dashboard')
    business = get_object_or_404(BusinessProfile, pk=pk)
    if not business.owner:
        messages.error(request, 'This client does not have an owner account to impersonate.')
        return redirect('super_admin_client_detail', pk=business.pk)
    request.session['super_admin_original_user_id'] = request.user.pk
    auth_login(request, business.owner, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request, f'You are now logged in as {business.owner.username}.')
    return redirect('dashboard')


def super_admin_stop_impersonation(request):
    original_user_id = request.session.get('super_admin_original_user_id')
    if not original_user_id:
        messages.info(request, 'No active impersonation session was found.')
        return redirect('dashboard')
    original_user = get_object_or_404(User, pk=original_user_id, is_superuser=True)
    auth_login(request, original_user, backend='django.contrib.auth.backends.ModelBackend')
    del request.session['super_admin_original_user_id']
    messages.success(request, 'Returned to the super admin account.')
    return redirect('super_admin_dashboard')


def super_admin_reset_owner_password(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Only the system super admin can perform this action.')
        return redirect('dashboard')
    business = get_object_or_404(BusinessProfile, pk=pk)
    if not business.owner:
        messages.error(request, 'This client does not have an owner account.')
        return redirect('super_admin_client_detail', pk=business.pk)
    temp_password = secrets.token_urlsafe(8)
    business.owner.set_password(temp_password)
    business.owner.save(update_fields=['password'])
    profile = getattr(business.owner, 'profile', None)
    if profile:
        profile.require_password_change = True
        profile.password_changed_date = timezone.now()
        profile.save(update_fields=['require_password_change', 'password_changed_date'])

    email_sent = False
    recipient_email = business.owner.email or business.email
    if recipient_email:
        try:
            send_mail(
                subject='Your Meneja360° password has been reset',
                message=(
                    f'Hello {business.owner.username},\n\n'
                    f'Your password for {business.name} has been reset by the system administrator.\n'
                    f'Temporary password: {temp_password}\n\n'
                    'Please sign in and change this temporary password immediately.\n'
                ),
                from_email=None,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            email_sent = True
        except Exception:
            email_sent = False

    if email_sent:
        messages.success(
            request,
            f'Temporary password for {business.owner.username}: {temp_password}. '
            f'The reset details were also emailed to {recipient_email}.'
        )
    else:
        messages.success(
            request,
            f'Temporary password for {business.owner.username}: {temp_password}. '
            'No email was sent, so share it with the client manually.'
        )
    return redirect('super_admin_client_detail', pk=business.pk)
