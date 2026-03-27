from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .tenancy import get_user_business


def get_business_access_state(user):
    if not user or not user.is_authenticated or user.is_superuser:
        return 'active', None

    try:
        business = get_user_business(user)
    except (AttributeError, ObjectDoesNotExist, OperationalError, ProgrammingError, PermissionDenied):
        return 'active', None

    if not business.is_active:
        return 'inactive', business

    if business.subscription_end_date and business.subscription_end_date < timezone.localdate():
        return 'expired', business

    return 'active', business
