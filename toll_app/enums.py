import enum

class VehicleType(enum.Enum):
    BIKE = 'bike'
    CAR = 'car'
    LARGE = 'large'


class UserStatus(enum.Enum):
    ACTIVE = True
    INACTIVE = False