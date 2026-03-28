from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class BusinessProfile(models.Model):
    APPROVAL_PENDING = 'pending'
    APPROVAL_APPROVED = 'approved'
    APPROVAL_REJECTED = 'rejected'
    APPROVAL_STATUS_CHOICES = [
        (APPROVAL_PENDING, 'Pending Approval'),
        (APPROVAL_APPROVED, 'Approved'),
        (APPROVAL_REJECTED, 'Rejected'),
    ]

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
    subscription_start_date = models.DateField("Subscription Start Date", blank=True, null=True)
    subscription_end_date = models.DateField("Subscription End Date", blank=True, null=True)
    is_active = models.BooleanField("Active", default=True)
    approval_status = models.CharField("Approval Status", max_length=20, choices=APPROVAL_STATUS_CHOICES, default=APPROVAL_APPROVED)
    date_created = models.DateTimeField("Date Created", default=timezone.now)

    class Meta:
        verbose_name = "Business Profile"
        verbose_name_plural = "Business Profiles"

    def __str__(self):
        return self.name

    @property
    def days_until_expiry(self):
        if not self.subscription_end_date:
            return None
        return (self.subscription_end_date - timezone.localdate()).days

    @property
    def subscription_status(self):
        if self.approval_status == self.APPROVAL_PENDING:
            return 'Pending Approval'
        if self.approval_status == self.APPROVAL_REJECTED:
            return 'Rejected'
        if not self.is_active:
            return 'Inactive'
        if not self.subscription_end_date:
            return 'Active'
        if self.subscription_end_date < timezone.localdate():
            return 'Expired'
        return 'Active'

    @property
    def is_expired(self):
        return self.subscription_status == 'Expired'

    @property
    def is_near_expiry(self):
        days = self.days_until_expiry
        return self.is_active and days is not None and 0 <= days <= 3

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

    company_name = models.CharField(
        "Company Name",
        max_length=255,
        blank=True,
        help_text="Optional company or organization name"
    )

    address = models.TextField(
        "Address",
        blank=True,
        help_text="Optional billing or postal address"
    )

    email = models.EmailField(
        "Email Address",
        blank=True,
        null=True,
        help_text="Client's email address"
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
    invoice_due_date = models.DateField("Invoice Due Date", blank=True, null=True)
    invoice_discount = models.DecimalField("Invoice Discount", max_digits=10, decimal_places=2, default=0)
    invoice_tax_rate = models.DecimalField("Invoice Tax Rate (%)", max_digits=5, decimal_places=2, default=0)
    document_notes = models.TextField("Document Notes", blank=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-date']

    def items_subtotal(self):
        if not self.pk:
            return self.unit_price * self.quantity
        items_total = self.items.aggregate(total=Sum('line_total'))['total']
        if items_total is not None:
            return items_total
        return self.unit_price * self.quantity

    def sync_primary_item_fields(self):
        first_item = self.items.order_by('id').first() if self.pk else None
        if first_item:
            self.service_name = first_item.description
            self.unit_price = first_item.unit_price
            self.quantity = first_item.quantity

    def recalculate_totals(self):
        subtotal = self.items_subtotal()
        discount = self.invoice_discount or Decimal('0')
        taxable_amount = subtotal - discount
        if taxable_amount < 0:
            taxable_amount = Decimal('0')
        tax_amount = taxable_amount * ((self.invoice_tax_rate or Decimal('0')) / Decimal('100'))
        self.total_amount = taxable_amount + tax_amount
        self.balance = self.total_amount - self.amount_paid
        if self.balance <= 0:
            self.status = self.PAID
        elif 0 < self.balance < self.total_amount:
            self.status = self.PARTIAL
        else:
            self.status = self.UNPAID

    def save(self, *args, **kwargs):
        # automatic calculations
        if self.client and self.client.business_id != self.business_id:
            raise ValidationError("Transactions can only be linked to clients from the same business.")
        if self.pk:
            self.sync_primary_item_fields()
        self.recalculate_totals()
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

    @property
    def receipt_number(self):
        if not self.pk:
            return "RCPT-DRAFT"
        return f"RCPT-{self.pk:05d}"

    @property
    def invoice_number(self):
        if not self.pk:
            return "INV-DRAFT"
        return f"INV-{self.pk:05d}"

    @property
    def document_subtotal(self):
        return self.items_subtotal()

    @property
    def document_discount_amount(self):
        return self.invoice_discount or 0

    @property
    def document_taxable_amount(self):
        taxable_amount = self.document_subtotal - self.document_discount_amount
        return taxable_amount if taxable_amount > 0 else 0

    @property
    def document_tax_amount(self):
        return (self.document_taxable_amount * (self.invoice_tax_rate or 0)) / 100

    @property
    def document_grand_total(self):
        return self.document_taxable_amount + self.document_tax_amount

    @property
    def invoice_balance_due(self):
        balance_due = self.document_grand_total - (self.amount_paid or 0)
        return balance_due if balance_due > 0 else 0


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
    supplier_name = models.CharField("Supplier Name", max_length=255, blank=True)
    supplier_contact = models.CharField("Supplier Contact", max_length=255, blank=True)
    description = models.TextField("Description", blank=True)
    amount = models.DecimalField("Amount", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-date']

    def clean(self):
        super().clean()
        if self.category == self.SUPPLIES and not self.supplier_name.strip():
            raise ValidationError({
                'supplier_name': 'Supplier name is required when recording supplies.'
            })

    def __str__(self):
        return f"{self.get_category_display()} - {self.amount}"


class SupplyExpense(models.Model):
    PAID = 'paid'
    PARTIAL = 'partial'
    UNPAID = 'unpaid'
    STATUS_CHOICES = [
        (PAID, 'Paid'),
        (PARTIAL, 'Partial'),
        (UNPAID, 'Unpaid'),
    ]

    business = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='supply_expenses')
    date = models.DateTimeField("Date", default=timezone.now)
    supplier_name = models.CharField("Supplier Name", max_length=255)
    supplier_contact = models.CharField("Supplier Contact", max_length=255, blank=True)
    item_name = models.CharField("Item Name", max_length=255, blank=True)
    description = models.TextField("Supplies Description", blank=True)
    quantity = models.DecimalField("Quantity", max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField("Unit Price", max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField("Total Amount", max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField("Amount Paid", max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField("Balance", max_digits=12, decimal_places=2, default=0)
    status = models.CharField("Status", max_length=10, choices=STATUS_CHOICES, default=UNPAID)

    class Meta:
        verbose_name = "Supply Expense"
        verbose_name_plural = "Supply Expenses"
        ordering = ['-date']

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})
        if self.amount_paid < 0:
            raise ValidationError({'amount_paid': 'Amount paid cannot be negative.'})

    def get_items_queryset(self):
        if not self.pk:
            return SupplyExpenseLineItem.objects.none()
        return self.items.all()

    def get_item_summary(self):
        items = list(self.get_items_queryset())
        if not items:
            return self.item_name or self.description or 'Supplies'
        first_name = items[0].item_name
        if len(items) == 1:
            return first_name
        return f"{first_name} + {len(items) - 1} more"

    def get_items_count(self):
        if not self.pk:
            return 0
        return self.items.count()

    def sync_primary_item_fields(self):
        items = list(self.get_items_queryset())
        if not items:
            return
        total_quantity = sum((item.quantity for item in items), Decimal('0'))
        total_amount = sum((item.line_total for item in items), Decimal('0'))
        primary = items[0]
        self.item_name = self.get_item_summary()
        self.description = primary.description or ''
        self.quantity = total_quantity or Decimal('0')
        self.unit_price = (total_amount / total_quantity) if total_quantity else Decimal('0')

    def recalculate_totals(self):
        items = list(self.get_items_queryset())
        if items:
            self.quantity = sum((item.quantity for item in items), Decimal('0'))
            self.amount = sum((item.line_total for item in items), Decimal('0'))
            self.unit_price = (self.amount / self.quantity) if self.quantity else Decimal('0')
            self.item_name = self.get_item_summary()
            primary = items[0]
            self.description = primary.description or self.description
        else:
            self.amount = self.quantity * self.unit_price
        self.balance = self.amount - self.amount_paid
        if self.balance <= 0:
            self.balance = Decimal('0')
            self.status = self.PAID
        elif self.amount_paid > 0:
            self.status = self.PARTIAL
        else:
            self.status = self.UNPAID

    def save(self, *args, **kwargs):
        self.recalculate_totals()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.supplier_name} - {self.item_name or self.description or self.amount}"


class SupplyExpenseLineItem(models.Model):
    supply_expense = models.ForeignKey(SupplyExpense, on_delete=models.CASCADE, related_name='items')
    item_name = models.CharField("Item Name", max_length=255)
    description = models.TextField("Description", blank=True)
    quantity = models.DecimalField("Quantity", max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField("Unit Price", max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField("Line Total", max_digits=12, decimal_places=2, blank=True)

    class Meta:
        verbose_name = "Supply Expense Line Item"
        verbose_name_plural = "Supply Expense Line Items"
        ordering = ['id']

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_name} ({self.quantity})"


class TransactionLineItem(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='items')
    description = models.CharField("Description", max_length=255)
    quantity = models.PositiveIntegerField("Quantity", default=1)
    unit_price = models.DecimalField("Unit Price", max_digits=10, decimal_places=2)
    line_total = models.DecimalField("Line Total", max_digits=12, decimal_places=2, blank=True)

    class Meta:
        verbose_name = "Transaction Line Item"
        verbose_name_plural = "Transaction Line Items"
        ordering = ['id']

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} ({self.quantity})"


class Payment(models.Model):
    business = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField("Amount", max_digits=12, decimal_places=2)
    payment_date = models.DateField("Payment Date", default=timezone.localdate)
    duration_days = models.PositiveIntegerField("Subscription Duration (Days)", default=30)
    reference = models.CharField("Reference", max_length=100, blank=True)
    notes = models.TextField("Notes", blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_payments',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.business.name} - {self.amount} on {self.payment_date}"


from .auth_security import ActivityLog, SystemSettings, UserProfile  # noqa: E402,F401
