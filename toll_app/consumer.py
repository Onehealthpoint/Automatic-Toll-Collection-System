# toll_app/consumers.py
import json
import cv2
import base64
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer
import asyncio
from django.apps import apps
from .models import Transactions, UserDetails
from .enums import VehicleRate
import uuid
from datetime import datetime, timedelta
import os
from django.conf import settings


class LiveDetectionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.cap = None
        self.frame_count = 0
        self.detected_plates = {}  # Store recent detections to avoid duplicates
        self.is_processing = False

        # Get models from AppConfig
        TollAppConfig = apps.get_app_config('toll_app')
        self.plate_model = TollAppConfig.plate_model
        self.coco_model = TollAppConfig.coco_model
        self.easyocr_reader = TollAppConfig.easyocr_reader
        self.device = TollAppConfig.device

        await self.send(text_data=json.dumps({
            'type': 'status',
            'message': 'Connected to live detection system. Ready to start.'
        }))

    async def disconnect(self, close_code):
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_processing = False
        await self.send(text_data=json.dumps({
            'type': 'status',
            'message': 'Disconnected from detection system'
        }))

    async def receive(self, text_data):
        """Handle messages from client"""
        try:
            data = json.loads(text_data)

            if data.get('type') == 'control':
                action = data.get('action')

                if action == 'start':
                    if not self.is_processing:
                        self.is_processing = True
                        await self.start_webcam()
                        await self.send(text_data=json.dumps({
                            'type': 'status',
                            'message': 'Detection started successfully'
                        }))
                    else:
                        await self.send(text_data=json.dumps({
                            'type': 'warning',
                            'message': 'Detection is already running'
                        }))

                elif action == 'stop':
                    self.is_processing = False
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                    await self.send(text_data=json.dumps({
                        'type': 'status',
                        'message': 'Detection stopped'
                    }))

                elif action == 'status':
                    await self.send(text_data=json.dumps({
                        'type': 'status',
                        'message': f'Processing: {self.is_processing}, Webcam: {self.cap is not None and self.cap.isOpened()}'
                    }))

        except json.JSONDecodeError as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Invalid JSON: {str(e)}'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Error processing message: {str(e)}'
            }))

    async def start_webcam(self):
        """Start webcam capture and processing"""
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Cannot access webcam. Please check camera permissions.'
                }))
                self.is_processing = False
                return

            # Set camera properties for better performance
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'Webcam started successfully. Processing frames...'
            }))

            # Start processing frames in background
            asyncio.create_task(self.process_frames())

        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Webcam error: {str(e)}'
            }))
            self.is_processing = False

    async def process_frames(self):
        """Process video frames and send to client"""
        while self.is_processing and self.cap and self.cap.isOpened():
            try:
                ret, frame = self.cap.read()
                if not ret:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to read frame from webcam'
                    }))
                    break

                self.frame_count += 1

                # Process every 4th frame for better performance
                if self.frame_count % 4 == 0:
                    processed_frame, detections = await self.process_frame(frame)

                    # Send processed frame to client
                    if processed_frame is not None:
                        await self.send_frame(processed_frame)

                    # Process detections
                    if detections:
                        await self.process_detections(detections)
                else:
                    # Send original frame for smooth video
                    await self.send_frame(frame)

                # Control frame rate to prevent overwhelming the client
                await asyncio.sleep(0.033)  # ~30 FPS

            except Exception as e:
                print(f"Error in frame processing: {e}")
                await asyncio.sleep(0.1)  # Brief pause on error

        # Cleanup
        if self.cap:
            self.cap.release()
            self.cap = None

    async def process_frame(self, frame):
        """Process a single frame using detect.py functions"""
        try:
            # Import detect functions
            from .ANPRS.detect import process_frame as detect_process_frame

            # Use the detect.py function to process the frame
            annotated_frame, detections = detect_process_frame(frame)

            return annotated_frame, detections

        except Exception as e:
            print(f"Error in process_frame: {e}")
            # Fallback to basic processing
            return await self.fallback_process_frame(frame)

    async def fallback_process_frame(self, frame):
        """Fallback frame processing if detect.py fails"""
        try:
            # Basic processing without detect.py
            results = self.plate_model(frame)
            detections = []
            annotated_frame = frame.copy()

            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        if box.conf > 0.5:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            plate_region = frame[y1:y2, x1:x2]

                            # Basic OCR
                            ocr_results = self.easyocr_reader.readtext(plate_region)

                            if ocr_results:
                                plate_text = max(ocr_results, key=lambda x: x[2])[1]
                                plate_text = plate_text.upper().replace(' ', '')

                                # Simple vehicle type detection
                                vehicle_type = "4W"  # Default
                                if len(plate_text) <= 8:
                                    vehicle_type = "2W"

                                detections.append({
                                    'plate_text': plate_text,
                                    'vehicle_type': vehicle_type,
                                    'bbox': (x1, y1, x2, y2),
                                    'confidence': float(box.conf)
                                })

                                # Draw bounding box
                                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(annotated_frame, f'{plate_text} ({vehicle_type})',
                                            (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            return annotated_frame, detections

        except Exception as e:
            print(f"Error in fallback processing: {e}")
            return frame, []

    async def process_detections(self, detections):
        """Process detected plates"""
        current_time = datetime.now()

        for detection in detections:
            plate_text = detection.get('plate_text', '')
            vehicle_type = detection.get('vehicle_type', '4W')
            confidence = detection.get('confidence', 0)

            if not plate_text:
                continue

            # Check if this plate was detected recently (within 15 seconds)
            if plate_text in self.detected_plates:
                last_detection_time = self.detected_plates[plate_text]['timestamp']
                if (current_time - last_detection_time).total_seconds() < 15:
                    continue  # Skip if detected recently

            # Update detection time
            self.detected_plates[plate_text] = {
                'timestamp': current_time,
                'vehicle_type': vehicle_type,
                'confidence': confidence
            }

            # Send detection info to client
            await self.send(text_data=json.dumps({
                'type': 'detection',
                'plate_text': plate_text,
                'vehicle_type': vehicle_type,
                'confidence': confidence,
                'message': f'Detected: {plate_text} ({vehicle_type})'
            }))

            # Process transaction
            await self.process_transaction(plate_text, vehicle_type)

    async def process_transaction(self, plate_text, vehicle_type):
        """Process transaction for detected vehicle"""
        try:
            # Find user by vehicle number
            user = UserDetails.objects.filter(vehicle_number=plate_text).first()

            if user:
                # Calculate fee
                fee = VehicleRate.get_rate(vehicle_type)

                # Check balance
                if user.balance >= fee:
                    # Create transaction
                    transaction = Transactions(
                        id=uuid.uuid4(),
                        user=user,
                        vehicle_type=vehicle_type,
                        fee=fee,
                        remaining_balance=user.balance - fee,
                        image_path=f"detected_{plate_text}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    )

                    # Update user balance
                    user.balance -= fee
                    user.save()
                    transaction.save()

                    await self.send(text_data=json.dumps({
                        'type': 'transaction',
                        'plate_text': plate_text,
                        'vehicle_type': vehicle_type,
                        'fee': float(fee),
                        'remaining_balance': float(user.balance),
                        'message': f'Transaction processed: ₹{fee} deducted from {user.first_name}\'s account'
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'warning',
                        'plate_text': plate_text,
                        'message': f'Insufficient balance: ₹{user.balance} (Required: ₹{fee})'
                    }))
            else:
                await self.send(text_data=json.dumps({
                    'type': 'warning',
                    'plate_text': plate_text,
                    'message': 'Vehicle not registered in system'
                }))

        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'plate_text': plate_text,
                'message': f'Error processing transaction: {str(e)}'
            }))

    async def send_frame(self, frame):
        """Convert frame to base64 and send to client"""
        try:
            # Resize frame for better performance
            frame = cv2.resize(frame, (640, 480))

            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')

            # Send to client
            await self.send(text_data=json.dumps({
                'type': 'frame',
                'image': jpg_as_text
            }))
        except Exception as e:
            print(f"Error sending frame: {e}")