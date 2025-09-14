from .config import *
import cv2
import numpy as np
from PIL import Image, ImageDraw

def draw_text(plate, text, confidence, lang, bbox):
    if plate is None or plate.size == 0 or text is None or len(text) == 0:
        return plate

    if isinstance(plate, Image.Image):
        plate = np.array(plate)

    output = plate.copy()
    x1, y1, x2, y2 = bbox

    cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 255), 2)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    font_thickness = 2

    if isinstance(confidence, str):
        confidence = float(confidence)

    if lang == 'en' and text:
        label = f"{text} ({confidence:.2f})"
    else:
        label = f"{confidence:.2f}"

    text_size, _ = cv2.getTextSize(label, font, font_scale, font_thickness)
    text_x = x1
    text_y = max(y1 - 10, text_size[1] + 10)

    cv2.rectangle(output, (text_x, text_y - text_size[1] - 5), (text_x + text_size[0], text_y + 5), (0, 0, 0), -1)
    cv2.putText(output, label, (text_x, text_y), font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)

    return output

def calculate_box_iou(box1, box2):
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    x_left = max(x1_1, x1_2)
    y_top = max(y1_1, y1_2)
    x_right = min(x2_1, x2_2)
    y_bottom = min(y2_1, y2_2)

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)

    box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
    box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)

    return intersection / float(box1_area + box2_area - intersection)

def is_plate_tracked(bbox, tracked_plates):
    for tracked_plate in tracked_plates:
        plate_bbox = plate_info['plate'].plate_bbox
        iou = calculate_box_iou(bbox, plate_bbox)
        if iou > IOU_THRESHOLD:
            return tracked_plate.id
    return None