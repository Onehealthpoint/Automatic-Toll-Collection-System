from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import UserDetails, Transactions

class UserDetailsAdmin(UserAdmin):
    model = UserDetails
    list_display = ['username', 'email', 'phone', 'vehicle_number', 'vehicle_type', 'balance']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('phone', 'vehicle_number', 'vehicle_type', 'balance')}),
    )

class TransactionsAdmin(admin.ModelAdmin):
    model = Transactions
    list_display = ['user', 'vehicle_type', 'fee', 'remaining_balance', 'timestamp']
    readonly_fields = ['id', 'timestamp']

admin.site.register(UserDetails, UserDetailsAdmin)
admin.site.register(Transactions, TransactionsAdmin)
