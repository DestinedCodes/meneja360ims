from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Q
from .currency import format_ksh
from .models import BusinessProfile, Client, Transaction, Expense, SupplyExpense


class OutstandingBalanceFilter(admin.SimpleListFilter):
    """
    Custom filter to show clients with outstanding balances.
    """
    title = 'Outstanding Balance'
    parameter_name = 'outstanding_balance'

    def lookups(self, request, model_admin):
        return [
            ('has_balance', 'Has Outstanding Balance'),
            ('no_balance', 'No Outstanding Balance'),
            ('high_balance', 'High Balance (> KSh 1,000)'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'has_balance':
            return queryset.filter(outstanding_balance__gt=0)
        if self.value() == 'no_balance':
            return queryset.filter(outstanding_balance=0)
        if self.value() == 'high_balance':
            return queryset.filter(outstanding_balance__gt=1000)
        return queryset


# configure site-wide admin titles
admin.site.site_header = "Cyber Poa Administration"
admin.site.site_title = "Cyber Poa Admin"
admin.site.index_title = "Manage Records"


class ClientInline(admin.TabularInline):
    model = Client
    extra = 0
    fields = ('full_name', 'phone_number', 'client_type', 'total_spending', 'outstanding_balance')
    readonly_fields = ('total_spending', 'outstanding_balance')


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner_name', 'phone', 'email', 'date_created')
    search_fields = ('name', 'owner_name', 'phone', 'email')
    inlines = (ClientInline,)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """
    Admin interface for Client model with enhanced features.
    """

    # Display fields in list view
    list_display = (
        'full_name',
        'phone_number',
        'client_type',
        'total_spending',
        'outstanding_balance',
        'created_date',
        'whatsapp_link'
    )

    # Filters for the right sidebar
    list_filter = (
        'client_type',
        OutstandingBalanceFilter,
        'created_date',
        'business'
    )

    # Search functionality
    search_fields = ('full_name', 'phone_number', 'notes')

    # Fields to display in detail view
    fields = (
        'business',
        'full_name',
        'phone_number',
        'client_type',
        'total_spending',
        'outstanding_balance',
        'created_date',
        'notes'
    )

    # Read-only fields (auto-calculated)
    readonly_fields = ('total_spending', 'outstanding_balance', 'created_date')

    # Ordering
    ordering = ('-created_date', 'full_name')

    # List view configuration
    list_per_page = 25

    def whatsapp_link(self, obj):
        """
        Display a clickable WhatsApp link for the client.
        """
        whatsapp_url = obj.get_whatsapp_url()
        if whatsapp_url:
            return format_html(
                '<a href="{}" target="_blank" class="button" style="background: #25D366; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none;">📱 WhatsApp</a>',
                whatsapp_url
            )
        return "No phone number"
    whatsapp_link.short_description = "WhatsApp"
    whatsapp_link.allow_tags = True

    def get_queryset(self, request):
        """
        Optimize queryset by selecting related business.
        """
        return super().get_queryset(request).select_related('business')

    def outstanding_balance_status(self, obj):
        """
        Display outstanding balance with color coding.
        """
        if obj.outstanding_balance > 0:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">{}</span>',
                format_ksh(obj.outstanding_balance)
            )
        return format_html(
            '<span style="color: #28a745;">KSh 0.00</span>'
        )
    outstanding_balance_status.short_description = "Balance Status"
    outstanding_balance_status.admin_order_field = 'outstanding_balance'

    # Custom actions
    actions = ['mark_as_regular_client', 'export_client_data']

    def mark_as_regular_client(self, request, queryset):
        """
        Bulk action to mark selected clients as regular clients.
        """
        updated = queryset.update(client_type='regular')
        self.message_user(
            request,
            f'{updated} client(s) marked as regular clients.'
        )
    mark_as_regular_client.short_description = "Mark selected clients as regular"

    def export_client_data(self, request, queryset):
        """
        Export selected clients to CSV (placeholder for future implementation).
        """
        self.message_user(
            request,
            f'Export functionality for {queryset.count()} clients would be implemented here.'
        )
    export_client_data.short_description = "Export selected clients to CSV"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('service_name', 'date', 'business', 'client', 'total_amount', 'amount_paid', 'balance', 'status')
    list_filter = ('status', 'date', 'business')
    search_fields = ('service_name',)
    readonly_fields = ('total_amount', 'balance')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('category', 'date', 'business', 'amount')
    list_filter = ('category', 'date', 'business')
    search_fields = ('description',)


@admin.register(SupplyExpense)
class SupplyExpenseAdmin(admin.ModelAdmin):
    list_display = ('supplier_name', 'supplier_contact', 'date', 'business', 'amount')
    list_filter = ('date', 'business')
    search_fields = ('supplier_name', 'supplier_contact', 'description')
