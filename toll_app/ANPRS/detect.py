import os
import cv2
import datetime
import collections
import numpy as np
from .sort import Sort
from PIL import Image
from collections import deque
from django.conf import settings
from django.apps import apps

from .utils import *
from .config import *
from .intermediate import *
from .validator import validate_plate_text
from ..models import UserDetails
from ..enums import VEHICLE_TYPE_MAPPING

TollAppConfig = apps.get_app_config('toll_app')
plate_model = TollAppConfig.get_plate_model()
coco_model = TollAppConfig.get_coco_model()
easyocr_reader = TollAppConfig.get_easyocr_reader()
device = TollAppConfig.get_device()


tracker = Sort(max_age=TRACK_MAX_AGE, min_hits=TRACK_MIN_HITS)
track_texts = {}

tracked_plates = {}
next_plate_id = 0

realtime_recognized_plates = {}


def detect_vehicle_type_from_image(vehicle_region):
    if vehicle_region is None or vehicle_region.size == 0:
        return None, 0.0

    try:
        results = coco_model(vehicle_region)

        vehicle_types = []
        confidences = []

        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    if box.conf >= COCO_THRESHOLD:
                        class_id = int(box.cls[0])
                        class_name = VEHICLE_TYPE_MAPPING[class_id]
                        confidence = float(box.conf)

                        if class_name in VEHICLE_TYPE_MAPPING.keys():
                            vehicle_types.append(class_name)
                            confidences.append(confidence)

        if vehicle_types:
            max_idx = np.argmax(confidences)
            return vehicle_types[max_idx], confidences[max_idx]
        else:
            return None, 0.0

    except Exception as e:
        print(f"Error in vehicle type detection: {e}")
        return None, 0.0


def process_plate(plate_img, full_frame=None, plate_bbox=None):
    if plate_img is None or plate_img.size == 0:
        return "", 0, None

    try:
        processed_img = preprocess_image(plate_img)

        ocr_results = easyocr_reader.readtext(processed_img, **READ_TEXT_CONFIG)

        if not ocr_results:
            return "", 0, None

        best_result = max(ocr_results, key=lambda x: x[2])
        text, confidence = best_result[1], best_result[2]

        text, _ = validate_plate_text(text)

        vehicle_type = None

        if full_frame is not None and plate_bbox is not None:
            x1, y1, x2, y2 = plate_bbox
            h, w = full_frame.shape[:2]

            expand_x = int((x2 - x1) * 1.5)
            expand_y = int((y2 - y1) * 2.0)

            vx1 = max(0, x1 - expand_x // 2)
            vy1 = max(0, y1 - expand_y // 2)
            vx2 = min(w, x2 + expand_x // 2)
            vy2 = min(h, y2 + expand_y // 2)

            vehicle_region = full_frame[vy1:vy2, vx1:vx2]

            if vehicle_region.size > 0:
                vehicle_type, vehicle_confidence = detect_vehicle_type_from_image(vehicle_region)

        return text, confidence, vehicle_type

    except Exception as e:
        print(f"Error processing plate: {e}")
        return "", 0, None


def process_image(image_file):
    from django.core.files.storage import default_storage

    filename = default_storage.save(os.path.join('uploads', image_file.name), image_file)
    filepath = default_storage.path(filename)

    img = Image.open(filepath)
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    plate_results = plate_model(img_cv)
    recognized_plates = []

    for result in plate_results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                if box.conf >= OD_THRESHOLD:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = img_cv[y1:y2, x1:x2]

                    text, confidence, vehicle_type = process_plate(plate_img, img_cv, (x1, y1, x2, y2))

                    if text:
                        recognized_plates.append({
                            'text': text,
                            'confidence': confidence,
                            'vehicle_type': vehicle_type,
                            'bbox': (x1, y1, x2, y2)
                        })

    processed_img = img_cv.copy()
    for plate in recognized_plates:
        x1, y1, x2, y2 = plate['bbox']
        cv2.rectangle(processed_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{plate['text']} ({plate['vehicle_type']})"
        cv2.putText(processed_img, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    processed_filename = f"processed_{os.path.basename(filename)}"
    processed_path = os.path.join(PROCESSED_FOLDER, processed_filename)
    cv2.imwrite(processed_path, processed_img)

    return [(plate['vehicle_type'], plate['text'], processed_path) for plate in recognized_plates]


def generate_frames_sort():
    global realtime_recognized_plates

    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        print("Error: Could not open webcam")
        return

    tracker = Sort(max_age=TRACK_MAX_AGE, min_hits=TRACK_MIN_HITS)
    track_texts = {}
    frame_count = 0

    while True:
        success, frame = cap.read()
        if not success:
            break

        # Process every 4th frame for better performance
        if frame_count % 4 == 0:
            if frame is None or frame.size == 0:
                continue

            plate_results = plate_model(frame)
            detections = []

            for result in plate_results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        if box.conf >= OD_THRESHOLD:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            conf = float(box.conf)
                            detections.append([x1, y1, x2, y2, conf])

            dets = np.array(detections) if detections else np.empty((0, 5))
            tracks = tracker.update(dets)

            for track in tracks:
                x1, y1, x2, y2, track_id = map(int, track)
                plate_img = frame[y1:y2, x1:x2]

                # Process plate every 10 frames or if not processed yet
                if track_id not in track_texts or frame_count % 10 == 0:
                    text, confidence, vehicle_type = process_plate(plate_img, frame, (x1, y1, x2, y2))
                    if text:
                        track_texts[track_id] = {
                            'text': text,
                            'confidence': confidence,
                            'vehicle_type': vehicle_type,
                            'last_updated': frame_count
                        }
                elif track_id in track_texts:
                    track_texts[track_id]['last_updated'] = frame_count

                if track_id in track_texts:
                    info = track_texts[track_id]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (57, 255, 20), 2)
                    label = f"ID:{track_id} {info['text']} ({info['vehicle_type']})"
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (77, 77, 255), 2)

            # Clean up old tracks (not updated for 30 frames)
            current_frame = frame_count
            tracks_to_remove = [tid for tid, info in track_texts.items()
                                if current_frame - info['last_updated'] > 30]
            for tid in tracks_to_remove:
                del track_texts[tid]

            realtime_recognized_plates.clear()
            for tid, info in track_texts.items():
                realtime_recognized_plates[tid] = info

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        frame_count += 1

    cap.release()


def process_frame(frame):
    if isinstance(frame, Image.Image):
        frame = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)

    recognized_plates = []

    plate_results = plate_model(frame)

    for result in plate_results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                if box.conf >= OD_THRESHOLD:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = frame[y1:y2, x1:x2]

                    text, confidence, vehicle_type = process_plate(plate_img, frame, (x1, y1, x2, y2))

                    if text: 
                        recognized_plates.append({
                            'text': text,
                            'confidence': confidence,
                            'vehicle_type': vehicle_type,
                            'bbox': (x1, y1, x2, y2)
                        })

    annotated_frame = frame.copy()
    for plate in recognized_plates:
        x1, y1, x2, y2 = plate['bbox']
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{plate['text']} ({plate['vehicle_type']})"
        cv2.putText(annotated_frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    return annotated_frame, recognized_plates


def get_realtime_plates():
    return realtime_recognized_plates.copy()


def clear_realtime_plates():
    global realtime_recognized_plates
    realtime_recognized_plates.clear()