from .config import *
import cv2
import numpy as np


def preprocess_image(image):
    if not isinstance(image, np.ndarray):
        image = np.array(image)
    height, width = image.shape[:2]
    plate_img = cv2.resize(image, (width * 2, height * 2))
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    filtered = cv2.bilateralFilter(gray, 11, 17, 17)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(filtered)
    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    dilated = cv2.dilate(cleaned, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.ones_like(dilated) * 255

    for contour in contours:
        if cv2.contourArea(contour) < 50:
            cv2.drawContours(mask, [contour], -1, 0, -1)

    return cv2.bitwise_and(dilated, mask)


def preprocess_video(video):
    pass