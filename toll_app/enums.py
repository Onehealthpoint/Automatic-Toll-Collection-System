from enum import Enum
from decimal import Decimal


class VehicleType(Enum):
    BIKE = 'Bike'
    CAR = 'Car'
    LARGE = 'Large'

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class VehicleRate(Enum):
    BIKE = 30.00
    CAR = 50.00
    LARGE = 100.00

    @classmethod
    def get_rate(cls, vehicle_type):
        if vehicle_type == VehicleType.BIKE.value:
            return cls.BIKE.value
        elif vehicle_type == VehicleType.CAR.value:
            return cls.CAR.value
        elif vehicle_type == VehicleType.LARGE.value:
            return cls.LARGE.value
        else:
            return 0.0