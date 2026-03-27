from django.contrib import messages
from django.shortcuts import redirect

from .business_access import get_business_access_state


class BusinessAccessMiddleware:
    allowed_view_names = {
        'login',
        'logout',
        'password_reset',
        'password_reset_done',
        'password_reset_confirm',
        'password_reset_complete',
        'password_change',
        'password_change_done',
        'inactive_subscription',
        'super_admin_stop_impersonation',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.is_superuser:
            return None

        match = getattr(request, 'resolver_match', None)
        if match and match.view_name in self.allowed_view_names:
            return None

        state, _business = get_business_access_state(user)
        if state == 'active':
            return None

        if state == 'expired':
            messages.error(request, 'Your subscription has expired. Please contact the system administrator.')
        else:
            messages.error(request, 'This client account has been deactivated. Please contact the system administrator.')
        return redirect('inactive_subscription')
