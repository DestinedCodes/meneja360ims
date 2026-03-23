from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import redirect

from .tenancy import get_user_business


def _get_profile(user):
    try:
        return user.profile
    except (AttributeError, ObjectDoesNotExist, OperationalError, ProgrammingError):
        return None


def get_user_role(user):
    if not user or not user.is_authenticated:
        return None

    business = get_user_business(user)
    if business.owner_id == user.id:
        return 'admin'

    profile = _get_profile(user)
    if profile and getattr(profile, 'business_id', None) == business.id:
        return profile.role

    return 'staff'


def can_backup_restore(user):
    return get_user_role(user) == 'admin'


def can_manage_business(user):
    return get_user_role(user) == 'admin'


def can_manage_records(user):
    return get_user_role(user) in {'admin', 'staff'}


def can_view_reports(user):
    return get_user_role(user) in {'admin', 'staff', 'viewer'}


class PermissionRedirectMixin:
    permission_denied_message = 'You do not have permission to access that page.'

    def has_permission(self):
        return True

    def dispatch(self, request, *args, **kwargs):
        if not self.has_permission():
            messages.error(request, self.permission_denied_message)
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(PermissionRedirectMixin):
    permission_denied_message = 'Only the business owner can access that page.'

    def has_permission(self):
        return can_manage_business(self.request.user)


class RecordsRequiredMixin(PermissionRedirectMixin):
    permission_denied_message = 'Only staff or the business owner can manage records.'

    def has_permission(self):
        return can_manage_records(self.request.user)


class ReportsRequiredMixin(PermissionRedirectMixin):
    permission_denied_message = 'You do not have permission to view reports.'

    def has_permission(self):
        return can_view_reports(self.request.user)
