from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.utils import OperationalError, ProgrammingError

from .models import BusinessProfile


def get_user_business(user):
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    try:
        profile = user.profile
    except (AttributeError, ObjectDoesNotExist, OperationalError, ProgrammingError):
        profile = None
    if profile and getattr(profile, 'business_id', None):
        return profile.business
    return BusinessProfile.get_or_create_for_user(user)


class UserBusinessMixin:
    def get_business(self):
        return get_user_business(self.request.user)


class BusinessScopedQuerysetMixin(UserBusinessMixin):
    business_field = 'business'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(**{self.business_field: self.get_business()})


class BusinessFormMixin(UserBusinessMixin):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.get_business()
        return kwargs
