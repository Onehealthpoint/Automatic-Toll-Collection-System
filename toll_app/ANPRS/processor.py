import os
import cv2
import datetime
import collections
import numpy as np
from sort import Sort
from PIL import Image
from collections import deque
from flask import render_template
from werkzeug.utils import secure_filename

import config
from db import *
from utlis import *
from helper import *
from config import *
from intermediate import *
from validator import validate_nepali, validate_english


tracker = Sort(max_age=config.TRACK_MAX_AGE, min_hits=config.TRACK_MIN_HITS)
track_texts = {}

tracked_plates = {}
next_plate_id = 0

realtime_recognized_plates = {}


def process_image(image_file):
    filename = secure_filename(image_file.filename)
    filepath = os.path.join(config.UPLOAD_PATH, filename)
    image_file.save(filepath)

    img = Image.open(filepath)
    od_results = model(img)
    recognized_plates = []

    plates = []
    for result in od_results:
        boxes = result.boxes
        for box in boxes:
            if box.conf >= config.OD_THRESHOLD and box.cls == 0:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = img.crop((x1, y1, x2, y2))
                text, text_conf = process_plate(plate_img)
                plate = Plate(
                    plate_bbox=(x1, y1, x2, y2),
                    plate_conf=float(box.conf),
                    plate_color=get_plate_color(plate_img),
                    text=text,
                    text_conf=text_conf,
                    source=Source.IMAGE,
                    original_image_path=filename,
                    result_image_path=None)
                recognized_plates.append(plate)
                plates.append({'text': text, 'confidence': text_conf})

    processed_filename = f"processed_{filename}"
    processed_filepath = os.path.join(config.PROCESSED_FOLDER, processed_filename)
    processed_img = img.copy()

    for plate in recognized_plates:
        processed_img = draw_text(processed_img, plate.text, plate.text_conf, plate.lang, plate.plate_bbox)
        plate.recognized_plates = processed_filename
        plate.save_to_db()

    if not isinstance(processed_img, Image.Image):
        Image.fromarray(processed_img).save(processed_filepath)
    else:
        processed_img.save(processed_filepath)

    return render_template(
        'image_result.html',
        original_image=filename,
        processed_image=processed_filename,
        plates=plates
    )


def generate_frames_sort():
    global realtime_recognized_plates

    cap = cv2.VideoCapture(0)
    tracker = Sort(max_age=config.TRACK_MAX_AGE, min_hits=config.TRACK_MIN_HITS)
    track_texts = {}
    frame_count = 0

    while True:
        success, frame = cap.read()
        if not success:
            break

        od_results = model(frame)
        detections = []
        for result in od_results:
            for box in result.boxes:
                if box.conf >= config.OD_THRESHOLD and box.cls == 0:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf)
                    detections.append([x1, y1, x2, y2, conf])

        dets = np.array(detections)
        if len(dets) == 0:
            dets = np.empty((0, 5))
        tracks = tracker.update(dets)

        for track in tracks:
            x1, y1, x2, y2, track_id = map(int, track)
            plate_img = frame[y1:y2, x1:x2]
            if track_id not in track_texts or frame_count % 10 == 0:
                text, text_conf = process_plate(plate_img)
                track_texts[track_id] = {'text': text, 'confidence': text_conf}
            else:
                text = track_texts[track_id]['text']
                text_conf = track_texts[track_id]['confidence']

            cv2.rectangle(frame, (x1, y1), (x2, y2), (57, 255, 20), 2)
            cv2.putText(frame, f"ID:{track_id}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (77, 77, 255), 2)

        realtime_recognized_plates.clear()
        for tid, info in track_texts.items():
            realtime_recognized_plates[tid] = {
                'text': info['text'],
                'confidence': info['confidence']
            }

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        frame_count += 1

    cap.release()


def process_plate(plate_img):
    plate_img = np.array(plate_img)

    if plate_img is None or plate_img.size == 0:
        return "", 0

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

    od_results = model(frame)
    recognized_plates = []

    for result in od_results:
        boxes = result.boxes
        for box in boxes:
            if box.conf >= config.OD_THRESHOLD and box.cls == 0:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                plate_img = frame[y1:y2, x1:x2]

                text, text_conf = process_plate(plate_img)

                plate = {
                    'coordinates': (x1, y1, x2, y2),
                    'confidence': float(box.conf),
                    'plate_color': get_plate_color(plate_img),
                    'text': text,
                    'text_confidence': text_conf,
                    'language': 'ne' if any(char in config.ALLOWED_NEP_CHAR for char in text) else 'en'
                }

                recognized_plates.append(plate)

    return frame, recognized_plates