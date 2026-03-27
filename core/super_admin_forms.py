from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import BusinessProfile, Payment


class SuperAdminClientForm(forms.ModelForm):
    owner_username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    owner_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    owner_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text='Required when creating a new client owner.',
    )

    class Meta:
        model = BusinessProfile
        fields = [
            'name',
            'owner_name',
            'phone',
            'email',
            'location',
            'subscription_start_date',
            'subscription_end_date',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'owner_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'subscription_start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'subscription_end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        owner = getattr(self.instance, 'owner', None)
        if owner:
            self.fields['owner_username'].initial = owner.username
            self.fields['owner_email'].initial = owner.email
            self.fields['owner_password'].help_text = 'Leave blank to keep the current password.'

    def clean_owner_username(self):
        username = self.cleaned_data['owner_username'].strip()
        owner = getattr(self.instance, 'owner', None)
        queryset = User.objects.filter(username__iexact=username)
        if owner:
            queryset = queryset.exclude(pk=owner.pk)
        if queryset.exists():
            raise ValidationError('A user with this username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk and not cleaned_data.get('owner_password'):
            self.add_error('owner_password', 'Owner password is required when creating a new client.')
        return cleaned_data

    def save(self, commit=True):
        business = super().save(commit=False)
        owner = getattr(self.instance, 'owner', None)

        if owner:
            owner.username = self.cleaned_data['owner_username']
            owner.email = self.cleaned_data.get('owner_email') or ''
            if self.cleaned_data.get('owner_password'):
                owner.set_password(self.cleaned_data['owner_password'])
            owner.save()
        else:
            owner = User.objects.create_user(
                username=self.cleaned_data['owner_username'],
                email=self.cleaned_data.get('owner_email') or '',
                password=self.cleaned_data['owner_password'],
            )
            from .models import BusinessProfile

            business = BusinessProfile.get_or_create_for_user(owner)
            business.name = self.cleaned_data['name']
            business.owner_name = self.cleaned_data['owner_name']
            business.phone = self.cleaned_data['phone']
            business.email = self.cleaned_data.get('email')
            business.location = self.cleaned_data['location']
            business.subscription_start_date = self.cleaned_data.get('subscription_start_date')
            business.subscription_end_date = self.cleaned_data.get('subscription_end_date')
            business.is_active = self.cleaned_data['is_active']
            business.owner = owner

        if commit:
            business.save()

        return business


class SuperAdminPaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_date', 'duration_days', 'reference', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'duration_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
