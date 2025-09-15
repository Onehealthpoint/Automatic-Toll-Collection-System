import os
import cv2
import uuid
import datetime
import collections
import numpy as np
from django.core.mail import send_mail
from django.core.files.storage import default_storage
from .sort import Sort
from PIL import Image
from decimal import Decimal
from django.apps import apps
from collections import deque
from django.conf import settings
from django.utils import timezone
from django.db import transaction as db_transaction

from .utlis import *
from .helper import *
from .config import *
from .intermediate import *
from .validator import validate_nepali, validate_english
from ..models import Transactions, UserDetails
from ..enums import VehicleType, VehicleRate

# TollAppConfig = apps.get_app_config('toll_app')
# plate_model = TollAppConfig.get_plate_model()
# coco_model = TollAppConfig.get_coco_model()
# easyocr_reader = TollAppConfig.get_easyocr_reader()
# device = TollAppConfig.get_device()

tracker = Sort(max_age=TRACK_MAX_AGE, min_hits=TRACK_MIN_HITS)
track_texts = {}

tracked_plates = {}
next_plate_id = 0

realtime_recognized_plates = {}
last_detection_times = {}
DEBOUNCE_SECONDS = 30

EXIT_LIVE = False


def detect_vehicle_type(plate_text):
    user = UserDetails.objects.filter(vehicle_number=plate_text).first()
    if user:
        return user.vehicle_type
    return 'unknown'


def should_process_plate(plate_text):
    global last_detection_times

    current_time = timezone.now()

    clean_plate = plate_text.strip().upper()

    if clean_plate in last_detection_times.keys():
        last_time = last_detection_times[clean_plate]
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < DEBOUNCE_SECONDS:
            return False

    last_detection_times[clean_plate] = current_time
    return True


@db_transaction.atomic
def process_transaction(plate_text, vehicle_type, image_path):
    if not should_process_plate(plate_text):
        return None, "Plate processed recently (debounce active)"

    try:
        user = UserDetails.objects.select_for_update().filter(vehicle_number=plate_text).first()

        if not user:
            return None, "Vehicle not registered in system"

        if vehicle_type == VehicleType.BIKE.value:
            fee = VehicleRate.BIKE.value
        elif vehicle_type == VehicleType.CAR.value:
            fee = VehicleRate.CAR.value
        elif vehicle_type == VehicleType.LARGE.value:
            fee = VehicleRate.LARGE.value
        else:
            return None, f"Unknown vehicle type: {vehicle_type}"

        if user.balance < fee:
            return None, f"Insufficient balance: NRP {user.balance} (Required: NRP {fee})"

        transaction = Transactions(
            id=uuid.uuid4(),
            user=user,
            vehicle_type=vehicle_type,
            fee=Decimal(fee),
            remaining_balance=user.balance - Decimal(fee),
            image_path=image_path,
            timestamp=timezone.now()
        )

        user.balance -= Decimal(fee)
        user.save()
        transaction.save()

        try:
            send_mail(
                subject="Toll Payment Notification",
                message=f"Dear {user.first_name},\n\nA toll fee of NRP {fee} has been deducted from your account for vehicle number {plate_text}.\n\nRemaining Balance: NRP {user.balance}\n\nThank you for using our service.\n\nBest regards,\nToll Management System",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['r9nbgso1rz@jxpomup.com'],
                fail_silently=True
            )
            print(f"Email sent to {user.email}")
        except Exception as email_error:
            print(f"Failed to send email: {email_error}")

        return transaction, f"NRP {fee} deducted from {user.first_name}'s account"

    except Exception as e:
        return None, f"Error processing transaction: {str(e)}"


def process_video_sort(video_file):
    """
    Process uploaded video file for license plate detection and recognition
    with transaction handling and debounce mechanism.
    """
    # Save uploaded video file
    filename = default_storage.save(f"videos/{video_file.name}", video_file)
    filepath = default_storage.path(filename)

    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        raise ValueError("Could not open video file")

    # Get video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))

    # Create output video file
    processed_filename = f"processed_{os.path.basename(filename)}"
    processed_path = os.path.join(settings.MEDIA_ROOT, 'processed_videos', processed_filename)
    os.makedirs(os.path.dirname(processed_path), exist_ok=True)

    # Use appropriate codec based on platform
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(processed_path, fourcc, fps, (frame_width, frame_height))

    # Initialize tracker and tracking variables
    tracker = Sort(max_age=TRACK_MAX_AGE, min_hits=TRACK_MIN_HITS)
    track_texts = {}
    frame_count = 0
    processed_transactions = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Process every 4th frame for better performance
        if frame_count % 4 == 0:
            # Detect license plates using YOLO model
            od_results = plate_model(frame)
            detections = []

            for result in od_results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        if box.conf >= OD_THRESHOLD:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            conf = float(box.conf)
                            detections.append([x1, y1, x2, y2, conf])

            # Update tracker with detections
            dets = np.array(detections) if detections else np.empty((0, 5))
            tracks = tracker.update(dets)

            # Process each tracked plate
            for track in tracks:
                x1, y1, x2, y2, track_id = map(int, track)
                plate_img = frame[y1:y2, x1:x2]

                # Process plate if new or if confidence is low and it's time to recheck
                should_process = (
                        track_id not in track_texts or
                        (track_texts[track_id]['confidence'] < VIDEO_OCR_THRESHOLD and
                         frame_count % 10 == 0)
                )

                if should_process:
                    text, text_conf = process_plate(plate_img)

                    if text and text_conf > (track_texts.get(track_id, {}).get('confidence', 0) or 0):
                        # Determine vehicle type
                        vehicle_type = detect_vehicle_type(text)

                        # Process transaction with debounce
                        transaction, message = process_transaction(
                            text, vehicle_type, f"video_{filename}_frame_{frame_count}"
                        )

                        track_texts[track_id] = {
                            'text': text,
                            'confidence': text_conf,
                            'vehicle_type': vehicle_type,
                            'last_updated': frame_count,
                            'transaction_status': 'success' if transaction else 'error',
                            'transaction_message': message
                        }

                        if transaction:
                            processed_transactions.append({
                                'track_id': track_id,
                                'plate_text': text,
                                'vehicle_type': vehicle_type,
                                'fee': float(transaction.fee),
                                'status': 'success',
                                'message': message,
                                'timestamp': timezone.now().isoformat()
                            })

                # Draw bounding box and information on frame
                if track_id in track_texts:
                    info = track_texts[track_id]

                    # Choose color based on transaction status
                    color = (0, 255, 0) if info['transaction_status'] == 'success' else (0, 0, 255)

                    # Draw bounding box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    # Draw text with transaction status
                    status_symbol = "✓" if info['transaction_status'] == 'success' else "✗"
                    label = f"ID:{track_id} {info['text']} {status_symbol}"

                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                    # Add confidence score
                    cv2.putText(frame, f"Conf: {info['confidence']:.2f}",
                                (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # Write processed frame to output video
        out.write(frame)
        frame_count += 1

        # Print progress every 100 frames
        if frame_count % 100 == 0:
            print(f"Processed {frame_count} frames...")

    # Release resources
    cap.release()
    out.release()

    # Prepare final results
    recognized_plates = []
    for track_id, info in track_texts.items():
        recognized_plates.append({
            'track_id': track_id,
            'text': info['text'],
            'confidence': info['confidence'],
            'vehicle_type': info['vehicle_type'],
            'transaction_status': info['transaction_status'],
            'message': info['transaction_message']
        })

    # Generate summary statistics
    successful_transactions = [t for t in processed_transactions if t['status'] == 'success']
    total_revenue = sum(t['fee'] for t in successful_transactions)

    video_results = {
        'original_video': filename,
        'processed_video': processed_filename,
        'total_frames': frame_count,
        'plates_detected': len(recognized_plates),
        'transactions_processed': len(processed_transactions),
        'successful_transactions': len(successful_transactions),
        'total_revenue': total_revenue,
        'plates': recognized_plates,
        'transactions': processed_transactions
    }

    return video_results


def process_image(image_file):
    filename = default_storage.save(f"media/uploads/{image_file.name}", image_file)
    filepath = default_storage.path(filename)

    img = Image.open(filepath)
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    od_results = model(img_cv)
    recognized_plates = []
    transaction_results = []

    for result in od_results:
        boxes = result.boxes
        if boxes is not None:
            for box in boxes:
                if box.conf >= OD_THRESHOLD:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = img_cv[y1:y2, x1:x2]

                    text, text_conf = process_plate(plate_img)

                    if text:
                        vehicle_type = detect_vehicle_type(text)

                        transaction, message = process_transaction(
                            text, vehicle_type, filename
                        )

                        plate_info = {
                            'text': text,
                            'confidence': float(text_conf),
                            'bbox': (x1, y1, x2, y2),
                            'plate_conf': float(box.conf),
                            'vehicle_type': vehicle_type,
                            'transaction_status': 'success' if transaction else 'error',
                            'transaction_message': message
                        }

                        recognized_plates.append(plate_info)
                        transaction_results.append({
                            'plate': text,
                            'status': 'success' if transaction else 'error',
                            'message': message,
                            'transaction_id': str(transaction.id) if transaction else None
                        })

    processed_img = img_cv.copy()
    for plate in recognized_plates:
        x1, y1, x2, y2 = plate['bbox']
        color = (0, 255, 0) if plate['transaction_status'] == 'success' else (0, 0, 255)
        cv2.rectangle(processed_img, (x1, y1), (x2, y2), color, 2)

        status_text = "✓" if plate['transaction_status'] == 'success' else "✗"
        label = f"{plate['text']} {status_text}"
        cv2.putText(processed_img, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    processed_filename = f"processed_{os.path.basename(filename)}"
    processed_path = os.path.join(settings.MEDIA_ROOT, 'media/processed', processed_filename)
    os.makedirs(os.path.dirname(processed_path), exist_ok=True)
    cv2.imwrite(processed_path, processed_img)

    return recognized_plates, processed_filename, transaction_results


def generate_frames_sort():
    global realtime_recognized_plates, EXIT_LIVE

    EXIT_LIVE = False

    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        yield None
        return

    tracker = Sort(max_age=TRACK_MAX_AGE, min_hits=TRACK_MIN_HITS)
    track_texts = {}
    frame_count = 0

    while not EXIT_LIVE:
        success, frame = cap.read()
        if not success:
            break

        if frame_count % 1 == 0:
            od_results = model(frame)
            detections = []

            for result in od_results:
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

                if track_id not in track_texts or frame_count % 10 == 0:
                    text, confidence = process_plate(plate_img)
                    if confidence < OD_THRESHOLD or (
                            track_id in track_texts and confidence <= track_texts[track_id]['confidence']):
                        continue
                    if text:
                        vehicle_type = detect_vehicle_type(text)

                        transaction, message = process_transaction(
                            text, vehicle_type, f"live_frame_{frame_count}"
                        )

                        track_texts[track_id] = {
                            'text': text,
                            'confidence': confidence,
                            'last_updated': frame_count,
                            'vehicle_type': vehicle_type,
                            'transaction_status': 'success' if transaction else 'error',
                            'transaction_message': message
                        }

                if track_id in track_texts:
                    info = track_texts[track_id]
                    color = (0, 255, 0) if info['transaction_status'] == 'success' else (0, 0, 255)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = f"ID:{track_id} {info['text']}"
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            current_frame = frame_count
            tracks_to_remove = [tid for tid, info in track_texts.items()
                                if current_frame - info['last_updated'] > 30]
            for tid in tracks_to_remove:
                del track_texts[tid]

            realtime_recognized_plates.clear()
            for tid, info in track_texts.items():
                realtime_recognized_plates[tid] = info

        ret, buffer = cv2.imencode('.jpg', frame)
        if ret:
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        frame_count += 1

    cap.release()


def process_plate(plate_img):
    plate_img = np.array(plate_img)

    if plate_img is None or plate_img.size == 0:
        return None, 0

    processed_plate_img = preprocess_image(plate_img)

    nep_results = ne_reader.readtext(plate_img, **ne_read_text_config)
    eng_results = en_reader.readtext(processed_plate_img, **en_read_text_config)

    validated_nep_results = validate_nepali(nep_results)
    validated_eng_results = validate_english(eng_results)

    eng_conf = max([res[2] for res in eng_results], default=0)
    nep_conf = max([res[2] for res in nep_results], default=0)

    if eng_conf >= nep_conf and validated_eng_results:
        text, confidence = validated_eng_results, eng_conf
    else:
        text, confidence = validated_nep_results, nep_conf

    return text, confidence


def process_frame(frame):
    if isinstance(frame, Image.Image):
        frame = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)

    od_results = plate_model(frame)
    recognized_plates = []

    for result in od_results:
        boxes = result.boxes
        for box in boxes:
            if box.conf >= OD_THRESHOLD and box.cls == 0:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = frame[y1:y2, x1:x2]

                text, text_conf = process_plate(plate_img)

                plate = {
                    'coordinates': (x1, y1, x2, y2),
                    'confidence': float(box.conf),
                    'plate_color': get_plate_color(plate_img),
                    'text': text,
                    'text_confidence': text_conf,
                    'language': 'ne' if any(char in ALLOWED_NEP_CHAR for char in text) else 'en'
                }

                recognized_plates.append(plate)

    return frame, recognized_plates


def get_realtime_plates():
    return realtime_recognized_plates.copy()


def clear_realtime_plates():
    global realtime_recognized_plates
    realtime_recognized_plates.clear()


def stop_live_detection():
    global EXIT_LIVE
    EXIT_LIVE = True
