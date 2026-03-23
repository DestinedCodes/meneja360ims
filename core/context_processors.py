from .permissions import can_backup_restore, can_manage_business, can_manage_records, can_view_reports, get_user_role


def app_permissions(request):
    user = getattr(request, 'user', None)
    return {
        'app_role': get_user_role(user) if user and user.is_authenticated else None,
        'can_backup_restore': can_backup_restore(user) if user and user.is_authenticated else False,
        'can_manage_business': can_manage_business(user) if user and user.is_authenticated else False,
        'can_manage_records': can_manage_records(user) if user and user.is_authenticated else False,
        'can_view_reports': can_view_reports(user) if user and user.is_authenticated else False,
    }
