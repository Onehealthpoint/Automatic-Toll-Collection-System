import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from toll_app.enums import VehicleType


class Transactions(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('UserDetails', on_delete=models.CASCADE)
    vehicle_type = models.CharField(max_length=10)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    remaining_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    timestamp = models.DateTimeField(auto_now_add=True)
    image_path = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.user.first_name.title()} {self.user.last_name.title()} paid {self.fee} on {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"


class UserDetails(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=10, unique=True, null=True)
    vehicle_number = models.CharField(max_length=30, unique=True, blank=False, null=False)
    vehicle_type = models.CharField(max_length=10, null=False)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)


    def __str__(self):
        return f"{self.first_name} {self.last_name}".title()