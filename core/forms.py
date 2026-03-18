from django import forms
from .models import BusinessProfile, Client, Transaction, Expense


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
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['business', 'full_name', 'phone_number', 'client_type', 'notes']


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['business', 'date', 'client', 'service_name', 'unit_price', 'quantity', 'amount_paid']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['business', 'date', 'category', 'description', 'amount']
        widgets = {
            'date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
