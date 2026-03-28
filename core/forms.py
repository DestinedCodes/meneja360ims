from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Sum

from .models import BusinessProfile, Client, Transaction, TransactionLineItem, Expense, SupplyExpense, SupplyExpenseLineItem
from .auth_security import UserProfile


class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = ['name', 'owner_name', 'phone', 'email', 'location', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'owner_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class ClientForm(forms.ModelForm):
    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business or getattr(self.instance, 'business', None)

    class Meta:
        model = Client
        fields = ['full_name', 'phone_number', 'email', 'company_name', 'address', 'client_type', 'notes']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'client_type': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def save(self, commit=True):
        client = super().save(commit=False)
        if not self.business:
            raise ValidationError("A business is required for each client.")
        client.business = self.business
        if commit:
            client.save()
        return client


class TransactionForm(forms.ModelForm):
    client_name = forms.CharField(
        label="Client Name",
        required=False,
        help_text="Type the client's name. An existing client will be reused or a new client will be created automatically.",
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Enter client name',
            }
        ),
    )

    class Meta:
        model = Transaction
        fields = ['date', 'amount_paid', 'invoice_tax_rate']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'invoice_tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        self.business = self.business or getattr(self.instance, 'business', None)
        if self.instance.pk and self.instance.client:
            self.fields['client_name'].initial = self.instance.client.full_name

    def clean_client_name(self):
        return self.cleaned_data.get('client_name', '').strip()

    @staticmethod
    def _recalculate_client_totals(client):
        if not client:
            return
        totals = client.transactions.aggregate(
            total_spending=Sum('total_amount'),
            outstanding_balance=Sum('balance'),
        )
        client.total_spending = totals['total_spending'] or 0
        client.outstanding_balance = totals['outstanding_balance'] or 0
        client.save(update_fields=['total_spending', 'outstanding_balance'])

    def save(self, commit=True):
        previous_client = None
        if self.instance.pk:
            previous_client = Transaction.objects.filter(pk=self.instance.pk).values_list('client_id', flat=True).first()
            if previous_client:
                previous_client = Client.objects.filter(pk=previous_client).first()

        transaction = super().save(commit=False)
        business = self.business
        if not business:
            raise ValidationError("A business is required for each transaction.")
        client_name = self.cleaned_data.get('client_name', '')

        if client_name:
            client = Client.objects.filter(
                business=business,
                full_name__iexact=client_name,
            ).first()
            if client is None:
                client = Client.objects.create(
                    business=business,
                    full_name=client_name,
                    phone_number='',
                    client_type=Client.WALK_IN,
                )
            transaction.client = client
        else:
            transaction.client = None
        transaction.business = business
        if not transaction.service_name:
            transaction.service_name = 'Pending items'
        if not transaction.unit_price:
            transaction.unit_price = 0
        if not transaction.quantity:
            transaction.quantity = 1

        if commit:
            transaction.save()
            if previous_client and (transaction.client_id != previous_client.id):
                self._recalculate_client_totals(previous_client)
            if transaction.client:
                self._recalculate_client_totals(transaction.client)
        return transaction


class ExpenseForm(forms.ModelForm):
    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business or getattr(self.instance, 'business', None)
        self.fields['category'].choices = [
            choice for choice in Expense.CATEGORY_CHOICES if choice[0] != Expense.SUPPLIES
        ]

    class Meta:
        model = Expense
        fields = ['date', 'category', 'description', 'amount']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def save(self, commit=True):
        expense = super().save(commit=False)
        if not self.business:
            raise ValidationError("A business is required for each expense.")
        expense.business = self.business
        expense.supplier_name = ''
        expense.supplier_contact = ''
        if commit:
            expense.save()
        return expense


class SupplyExpenseForm(forms.ModelForm):
    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business or getattr(self.instance, 'business', None)

    class Meta:
        model = SupplyExpense
        fields = ['date', 'supplier_name', 'supplier_contact', 'amount_paid']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter supplier name'}),
            'supplier_contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone, email, or other contact'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }

    def save(self, commit=True):
        expense = super().save(commit=False)
        if not self.business:
            raise ValidationError("A business is required for each supply expense.")
        expense.business = self.business
        if commit:
            expense.save()
        return expense


class SupplyExpenseLineItemForm(forms.ModelForm):
    class Meta:
        model = SupplyExpenseLineItem
        fields = ['item_name', 'description', 'quantity', 'unit_price']
        widgets = {
            'item_name': forms.TextInput(attrs={'class': 'form-control item-name', 'placeholder': 'Supplied item'}),
            'description': forms.TextInput(attrs={'class': 'form-control item-description', 'placeholder': 'Optional notes'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control item-quantity', 'step': '0.01', 'min': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control item-unit-price', 'step': '0.01', 'min': '0'}),
        }


class BaseSupplyExpenseLineItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        active_forms = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            item_name = (form.cleaned_data.get('item_name') or '').strip()
            quantity = form.cleaned_data.get('quantity')
            unit_price = form.cleaned_data.get('unit_price')
            if item_name and quantity and unit_price is not None:
                active_forms += 1
        if active_forms == 0:
            raise ValidationError("Add at least one supplied item to the record.")


SupplyExpenseLineItemFormSet = inlineformset_factory(
    SupplyExpense,
    SupplyExpenseLineItem,
    form=SupplyExpenseLineItemForm,
    formset=BaseSupplyExpenseLineItemFormSet,
    extra=1,
    can_delete=True,
)


class InvoiceSettingsForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['invoice_due_date', 'invoice_discount', 'invoice_tax_rate', 'document_notes']
        widgets = {
            'invoice_due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'invoice_discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'invoice_tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'document_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Payment instructions, remarks, or comments'}),
        }


class TransactionLineItemForm(forms.ModelForm):
    class Meta:
        model = TransactionLineItem
        fields = ['description', 'quantity', 'unit_price']
        labels = {
            'description': 'Service Name',
        }
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control item-description', 'placeholder': 'Service name'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control item-quantity', 'min': '1'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control item-unit-price', 'step': '0.01', 'min': '0'}),
        }


class BaseTransactionLineItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        active_forms = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            description = (form.cleaned_data.get('description') or '').strip()
            quantity = form.cleaned_data.get('quantity')
            unit_price = form.cleaned_data.get('unit_price')
            if description and quantity and unit_price is not None:
                active_forms += 1
        if active_forms == 0:
            raise ValidationError("Add at least one item or service to the transaction.")


TransactionLineItemFormSet = inlineformset_factory(
    Transaction,
    TransactionLineItem,
    form=TransactionLineItemForm,
    formset=BaseTransactionLineItemFormSet,
    extra=1,
    can_delete=True,
)


class RegistrationForm(UserCreationForm):
    phone_number = forms.CharField(
        required=True,
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-lg'}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control form-control-lg'}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'phone_number', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Choose a username',
        })
        self.fields['email'].widget.attrs.update({
            'placeholder': 'Enter your email address',
        })
        self.fields['phone_number'].widget.attrs.update({
            'placeholder': 'Enter your phone number',
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Create a password',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Confirm your password',
        })

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number'].strip()
        clean_number = ''.join(filter(str.isdigit, phone_number))
        if len(clean_number) < 9:
            raise ValidationError('Enter a valid phone number with at least 9 digits.')
        return phone_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_active = False
        if commit:
            user.save()
            business = getattr(user, 'business_profile', None)
            if business:
                business.phone = self.cleaned_data['phone_number']
                business.email = self.cleaned_data['email']
                business.approval_status = BusinessProfile.APPROVAL_PENDING
                business.save(update_fields=['phone', 'email', 'approval_status'])
        return user


class StaffUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        choices=[
            ('staff', 'Staff / Receptionist'),
            ('viewer', 'Viewer'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Choose what this team member is allowed to do in the cyber cafe.',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'role', 'password1', 'password2')

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter a username',
        })
        self.fields['email'].widget.attrs.update({
            'placeholder': 'Optional email address',
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Create a password',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm the password',
        })

    def save(self, commit=True):
        if not self.business:
            raise ValidationError("A business is required to create staff accounts.")

        user = super().save(commit=commit)
        profile = user.profile
        original_business = getattr(user, 'business_profile', None)

        profile.business = self.business
        profile.role = self.cleaned_data['role']
        profile.save(update_fields=['business', 'role'])

        if original_business and original_business.pk != self.business.pk:
            original_business.delete()

        return user


class TeamMemberUpdateForm(forms.ModelForm):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = User
        fields = ('email', 'is_active')

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business
        self.profile = getattr(self.instance, 'profile', None)
        self.fields['email'].initial = self.instance.email
        if self.profile:
            self.fields['role'].initial = self.profile.role
        self.fields['is_active'].initial = self.instance.is_active

        if business and business.owner_id == self.instance.id:
            self.fields['role'].disabled = True
            self.fields['is_active'].disabled = True
            self.fields['role'].help_text = 'The business owner always remains an admin.'
            self.fields['is_active'].help_text = 'The owner account cannot be deactivated here.'

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Another account already uses this email address.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        if self.business and self.business.owner_id == self.instance.id:
            cleaned_data['role'] = 'admin'
            cleaned_data['is_active'] = True
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email', '')
        user.is_active = self.cleaned_data.get('is_active', True)

        if commit:
            user.save(update_fields=['email', 'is_active'])
            if self.profile:
                self.profile.business = self.business or self.profile.business
                self.profile.role = self.cleaned_data.get('role', self.profile.role)
                self.profile.save(update_fields=['business', 'role'])

        return user
