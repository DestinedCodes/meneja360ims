from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone


class BusinessProfile(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='business_profile',
        blank=True,
        null=True,
    )
    name = models.CharField("Business Name", max_length=255)
    owner_name = models.CharField("Owner Name", max_length=255)
    phone = models.CharField("Phone", max_length=50)
    email = models.EmailField("Email", blank=True, null=True)
    location = models.TextField("Location")
    logo = models.ImageField("Logo", upload_to="logos/", blank=True, null=True)
    date_created = models.DateTimeField("Date Created", default=timezone.now)

    class Meta:
        verbose_name = "Business Profile"
        verbose_name_plural = "Business Profiles"

    def __str__(self):
        return self.name

    @classmethod
    def defaults_for_user(cls, user):
        display_name = user.get_full_name().strip() or user.username
        return {
            'name': f"{display_name}'s Cyber Cafe",
            'owner_name': display_name,
            'phone': '',
            'email': user.email or '',
            'location': '',
        }

    @classmethod
    def get_or_create_for_user(cls, user):
        if not user or not user.is_authenticated:
            raise ValidationError("An authenticated user is required to access a business profile.")
        business, _ = cls.objects.get_or_create(
            owner=user,
            defaults=cls.defaults_for_user(user),
        )
        return business


class Client(models.Model):
    """
    Client model represents customers who purchase services from the business.
    Supports different client types and automatically tracks spending and balances.
    """

    # Client type choices
    WALK_IN = 'walkin'      # One-time visitors
    REGULAR = 'regular'     # Returning customers
    CORPORATE = 'corporate' # Business clients

    CLIENT_TYPE_CHOICES = [
        (WALK_IN, 'Walk-in'),
        (REGULAR, 'Regular'),
        (CORPORATE, 'Corporate'),
    ]

    # Foreign key to business - each client belongs to a business
    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.CASCADE,
        related_name='clients',
        help_text="The business this client belongs to"
    )

    # Basic client information
    full_name = models.CharField(
        "Full Name",
        max_length=255,
        help_text="Client's complete name"
    )

    phone_number = models.CharField(
        "Phone Number",
        max_length=50,
        blank=True,
        help_text="Client's contact phone number"
    )

    client_type = models.CharField(
        "Client Type",
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default=WALK_IN,
        help_text="Type of client relationship"
    )

    # Auto-calculated financial fields
    total_spending = models.DecimalField(
        "Total Spending",
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Total amount spent by client (auto-calculated)"
    )

    outstanding_balance = models.DecimalField(
        "Outstanding Balance",
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Amount client still owes (auto-calculated)"
    )

    # Timestamps and notes
    created_date = models.DateTimeField(
        "Created Date",
        default=timezone.now,
        help_text="When the client record was created"
    )

    notes = models.TextField(
        "Notes",
        blank=True,
        null=True,
        help_text="Additional notes about the client"
    )

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ['-created_date']
        # Ensure unique client names per business
        unique_together = ['business', 'full_name']

    def __str__(self):
        """String representation showing name and type"""
        return f"{self.full_name} ({self.get_client_type_display()})"

    def get_whatsapp_url(self):
        """
        Generate WhatsApp URL for the client's phone number.
        Returns None if phone number is not available.
        """
        if self.phone_number:
            # Remove any non-numeric characters and add country code if needed
            clean_number = ''.join(filter(str.isdigit, self.phone_number))
            # Add international prefix if not present (assuming +254 for Kenya)
            if not clean_number.startswith('254') and len(clean_number) == 9:
                clean_number = f"254{clean_number}"
            return f"https://wa.me/{clean_number}"
        return None

    def get_total_transactions(self):
        """Get total number of transactions for this client"""
        return self.transactions.count()

    def get_paid_transactions(self):
        """Get number of fully paid transactions"""
        return self.transactions.filter(status='paid').count()

    def get_pending_balance_percentage(self):
        """
        Calculate what percentage of total spending is still outstanding.
        Returns 0 if no spending.
        """
        if self.total_spending > 0:
            return (self.outstanding_balance / self.total_spending) * 100
        return 0

    def clean(self):
        """Custom validation for the model"""
        from django.core.exceptions import ValidationError

        # Validate phone number format (basic validation)
        if self.phone_number:
            clean_number = ''.join(filter(str.isdigit, self.phone_number))
            if len(clean_number) < 9:
                raise ValidationError({
                    'phone_number': 'Phone number must be at least 9 digits long.'
                })

        # Validate full name
        if self.full_name and len(self.full_name.strip()) < 2:
            raise ValidationError({
                'full_name': 'Full name must be at least 2 characters long.'
            })

    def save(self, *args, **kwargs):
        """Override save to perform validation"""
        self.full_clean()  # Run validation
        super().save(*args, **kwargs)


class Transaction(models.Model):
    PAID = 'paid'
    PARTIAL = 'partial'
    UNPAID = 'unpaid'
    STATUS_CHOICES = [
        (PAID, 'Paid'),
        (PARTIAL, 'Partial'),
        (UNPAID, 'Unpaid'),
    ]

    business = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateTimeField("Date", default=timezone.now)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, related_name='transactions', blank=True, null=True)
    service_name = models.CharField("Service Name", max_length=255)
    unit_price = models.DecimalField("Unit Price", max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField("Quantity", default=1)
    total_amount = models.DecimalField("Total Amount", max_digits=12, decimal_places=2, blank=True)
    amount_paid = models.DecimalField("Amount Paid", max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField("Balance", max_digits=12, decimal_places=2, blank=True)
    status = models.CharField("Status", max_length=10, choices=STATUS_CHOICES, default=UNPAID)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-date']

    def save(self, *args, **kwargs):
        # automatic calculations
        if self.client and self.client.business_id != self.business_id:
            raise ValidationError("Transactions can only be linked to clients from the same business.")
        self.total_amount = self.unit_price * self.quantity
        self.balance = self.total_amount - self.amount_paid
        if self.balance <= 0:
            self.status = self.PAID
        elif 0 < self.balance < self.total_amount:
            self.status = self.PARTIAL
        else:
            self.status = self.UNPAID
        super().save(*args, **kwargs)
        # After saving update related client aggregates
        if self.client:
            # recalc totals from all transactions belonging to this client
            total = self.client.transactions.aggregate(
                total=models.Sum('total_amount'))['total'] or 0
            balance = self.client.transactions.aggregate(
                balance=models.Sum('balance'))['balance'] or 0
            self.client.total_spending = total
            self.client.outstanding_balance = balance
            self.client.save(update_fields=['total_spending', 'outstanding_balance'])

    def __str__(self):
        return f"{self.service_name} - {self.date.date()}"


class Expense(models.Model):
    RENT = 'rent'
    ELECTRICITY = 'electricity'
    INTERNET = 'internet'
    SUPPLIES = 'supplies'
    MAINTENANCE = 'maintenance'
    SALARY = 'salary'
    MISC = 'misc'

    CATEGORY_CHOICES = [
        (RENT, 'Rent'),
        (ELECTRICITY, 'Electricity'),
        (INTERNET, 'Internet'),
        (SUPPLIES, 'Supplies'),
        (MAINTENANCE, 'Maintenance'),
        (SALARY, 'Salary'),
        (MISC, 'Misc'),
    ]

    business = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateTimeField("Date", default=timezone.now)
    category = models.CharField("Category", max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField("Description", blank=True)
    amount = models.DecimalField("Amount", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-date']

    def __str__(self):
        return f"{self.get_category_display()} - {self.amount}"


from .auth_security import ActivityLog, SystemSettings, UserProfile  # noqa: E402,F401
