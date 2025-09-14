from decimal import Decimal
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .enums import VehicleType, VehicleRate
from .models import UserDetails, Transactions
import uuid


class SignupForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Enter your email'})
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your first name'})
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your last name'})
    )
    phone = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your 10-digit phone number'})
    )
    vehicle_number = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your vehicle number'})
    )
    vehicle_type = forms.ChoiceField(
        choices=[
            (VehicleType.BIKE.value, 'Bike'),
            (VehicleType.CAR.value, 'Car'),
            (VehicleType.LARGE.value, 'Jeep, Bus or Truck')],
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = UserDetails
        fields = ('username', 'email', 'first_name', 'last_name', 'phone',
                  'vehicle_number', 'vehicle_type', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'vehicle_type':
                field.widget.attrs['class'] = 'form-control'
            if field_name in ['password1', 'password2']:
                field.widget.attrs['placeholder'] = 'Enter your password'
            if field_name == 'username':
                field.widget.attrs['placeholder'] = 'Choose a username'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        user.vehicle_number = self.cleaned_data['vehicle_number']
        user.vehicle_type = self.cleaned_data['vehicle_type']
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter your password'})
    )


class ManualEntryForm(forms.ModelForm):
    vehicle_number = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter vehicle number'})
    )
    timestamp = forms.DateTimeField(
        required=True,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control',
            'placeholder': 'YYYY-MM-DD HH:MM:SS',
            'type': 'datetime-local'
        })
    )

    class Meta:
        model = Transactions
        fields = ()

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(ManualEntryForm, self).__init__(*args, **kwargs)

    def clean_vehicle_number(self):
        vehicle_number = self.cleaned_data.get('vehicle_number')
        try:
            return UserDetails.objects.get(vehicle_number=vehicle_number)
        except UserDetails.DoesNotExist:
            raise forms.ValidationError("Vehicle number not found in our system.")

    def calculate_fee(self, vehicle_type):
        """Clean fee calculation using enums"""
        return VehicleRate.get_rate(vehicle_type)

    def save(self, commit=True):
        user_details = self.cleaned_data['vehicle_number']
        timestamp = self.cleaned_data['timestamp']

        fee = self.calculate_fee(user_details.vehicle_type)
        fee = Decimal(fee)

        if user_details.balance < fee:
            raise forms.ValidationError("Insufficient balance. Please recharge your account.")

        txn = Transactions(
            id=uuid.uuid4(),
            user=user_details,
            vehicle_type=user_details.vehicle_type,
            fee=fee,
            remaining_balance=user_details.balance - fee,
            timestamp=timestamp,
            image_path="manual_entry"
        )

        if commit:
            user_details.balance -= fee
            user_details.save()
            txn.save()

        return txn