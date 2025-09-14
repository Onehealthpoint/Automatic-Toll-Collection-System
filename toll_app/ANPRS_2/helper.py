from .config import *
import uuid
import cv2
import os
import numpy as np

def get_guid():
    return str(uuid.uuid4())

def get_plate_color(plate):
    plate = np.array(plate)
    if plate is None or plate.size == 0:
        return "Unknown"

    plate_rgb = cv2.cvtColor(plate, cv2.COLOR_BGR2RGB)
    r, g, b = np.mean(plate_rgb, axis=(0, 1))

    if r > 150 and g < 100 and b < 100:
        return "Red"
    elif g > 150 and r < 100 and b < 100:
        return "Green"
    elif b > 150 and r < 100 and g < 100:
        return "Blue"
    elif r > 150 and g > 150 and b < 100:
        return "Yellow"
    elif r < 80 and g < 80 and b < 80:
        return "Black"
    elif r > 180 and g > 180 and b > 180:
        return "White"
    else:
        return "Unknown"

def get_plate_lot_number(text):
    lot_number = ""
    for t in text:
        if t.isdigit():
            lot_number += t
        if len(lot_number) == 3:
            break
    return lot_number

def is_file_allowed(file):
    ext = file.filename.rsplit('.', 1)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return False

    start_pos = file.tell()
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(start_pos)

    if file_size > ALLOWED_FILE_SIZE:
        return False

    return True