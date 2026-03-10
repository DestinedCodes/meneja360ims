from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """
    Extended user profile for role-based access control
    """

    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('staff', 'Staff'),
        ('viewer', 'Viewer'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='staff',
        help_text="User's role in the system"
    )
    business = models.ForeignKey(
        'BusinessProfile',
        on_delete=models.CASCADE,
        related_name='user_profiles',
        help_text="Business this user belongs to"
    )
    is_active = models.BooleanField(default=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Security settings
    password_changed_date = models.DateTimeField(default=timezone.now)
    require_password_change = models.BooleanField(default=False)

    # Activity tracking
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        unique_together = ['user', 'business']

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()}) - {self.business.name}"

    def is_admin(self):
        """Check if user is administrator"""
        return self.role == 'admin'

    def is_staff_member(self):
        """Check if user is staff"""
        return self.role in ['admin', 'staff']

    def can_view_reports(self):
        """Check if user can view reports"""
        return self.role in ['admin', 'staff', 'viewer']

    def can_manage_clients(self):
        """Check if user can manage clients"""
        return self.role in ['admin', 'staff']

    def can_manage_transactions(self):
        """Check if user can manage transactions"""
        return self.role in ['admin', 'staff']

    def can_backup_restore(self):
        """Check if user can perform backup/restore operations"""
        return self.role == 'admin'

    def record_login_attempt(self, ip_address=None):
        """Record a login attempt"""
        self.login_attempts += 1
        self.last_login_ip = ip_address

        # Lock account after 5 failed attempts
        if self.login_attempts >= 5:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=30)

        self.save()

    def reset_login_attempts(self):
        """Reset login attempts on successful login"""
        self.login_attempts = 0
        self.locked_until = None
        self.save()

    def is_account_locked(self):
        """Check if account is currently locked"""
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False

    def get_lockout_time_remaining(self):
        """Get remaining lockout time in minutes"""
        if self.locked_until and timezone.now() < self.locked_until:
            remaining = self.locked_until - timezone.now()
            return int(remaining.total_seconds() / 60)
        return 0


class ActivityLog(models.Model):
    """
    Log of user activities for security and auditing
    """

    ACTION_CHOICES = [
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('create', 'Create Record'),
        ('update', 'Update Record'),
        ('delete', 'Delete Record'),
        ('view', 'View Record'),
        ('export', 'Export Data'),
        ('backup', 'Database Backup'),
        ('restore', 'Database Restore'),
        ('failed_login', 'Failed Login Attempt'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField(help_text="Description of the activity")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, help_text="Browser user agent")

    # Related objects (optional)
    business = models.ForeignKey(
        'BusinessProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    related_object_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type of related object (e.g., 'Client', 'Transaction')"
    )
    related_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of related object"
    )

    # Timestamps
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['business', 'timestamp']),
        ]

    def __str__(self):
        user_name = self.user.username if self.user else 'Anonymous'
        return f"{user_name} - {self.get_action_display()} - {self.timestamp}"


class SystemSettings(models.Model):
    """
    System-wide settings
    """

    business = models.OneToOneField(
        'BusinessProfile',
        on_delete=models.CASCADE,
        related_name='system_settings'
    )

    # Security settings
    session_timeout_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Session timeout in minutes"
    )
    max_login_attempts = models.PositiveIntegerField(
        default=5,
        help_text="Maximum login attempts before lockout"
    )
    lockout_duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Account lockout duration in minutes"
    )

    # Backup settings
    auto_backup_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic daily backups"
    )
    backup_retention_days = models.PositiveIntegerField(
        default=30,
        help_text="Number of days to keep backups"
    )

    # Business settings
    currency_symbol = models.CharField(
        max_length=10,
        default='$',
        help_text="Currency symbol for display"
    )
    date_format = models.CharField(
        max_length=20,
        default='Y-m-d',
        help_text="Date format for display"
    )
    timezone = models.CharField(
        max_length=50,
        default='UTC',
        help_text="System timezone"
    )

    # Email settings (for future use)
    email_notifications_enabled = models.BooleanField(
        default=False,
        help_text="Enable email notifications"
    )
    smtp_server = models.CharField(
        max_length=100,
        blank=True,
        help_text="SMTP server address"
    )
    smtp_port = models.PositiveIntegerField(
        default=587,
        help_text="SMTP server port"
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return f"Settings for {self.business.name}"


# Signal handlers for automatic profile creation and activity logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile when user is created"""
    if created:
        # Try to get the first business, or create default settings
        business = BusinessProfile.objects.first()
        if business:
            UserProfile.objects.create(user=instance, business=business)


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log successful user login"""
    try:
        profile = user.profile
        profile.reset_login_attempts()

        ActivityLog.objects.create(
            user=user,
            action='login',
            description=f'User {user.username} logged in',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            business=profile.business if hasattr(profile, 'business') else None
        )
    except:
        pass  # Silently handle errors in logging


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log user logout"""
    try:
        profile = user.profile
        ActivityLog.objects.create(
            user=user,
            action='logout',
            description=f'User {user.username} logged out',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            business=profile.business if hasattr(profile, 'business') else None
        )
    except:
        pass


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    """Log failed login attempts"""
    username = credentials.get('username', 'unknown')
    try:
        user = User.objects.get(username=username)
        profile = user.profile
        profile.record_login_attempt(get_client_ip(request))

        ActivityLog.objects.create(
            user=user,
            action='failed_login',
            description=f'Failed login attempt for user {username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            business=profile.business if hasattr(profile, 'business') else None
        )
    except User.DoesNotExist:
        # Log anonymous failed login
        ActivityLog.objects.create(
            action='failed_login',
            description=f'Failed login attempt for unknown user {username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
    except:
        pass


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip