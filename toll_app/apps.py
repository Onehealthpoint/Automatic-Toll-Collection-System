from django.apps import AppConfig
from django.conf import settings
from ultralytics import YOLO
import easyocr
import torch
import os


class TollAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'toll_app'


    def ready(self):
        # Load models only once when Django starts
        if not os.environ.get('DJANGO_LOAD_MODELS'):
            os.environ['DJANGO_LOAD_MODELS'] = '1'

            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"Using device: {self.device}")

            print("Loading YOLOV8n model...")
            self.coco_model = YOLO(os.path.join(settings.BASE_DIR, 'models/od/yolov8n.pt'))
            self.coco_model.to(self.device)

            print("Loading Custom Number Plate Recognition model...")
            self.plate_model = YOLO(os.path.join(settings.BASE_DIR, 'models/od/best.pt'))
            self.plate_model.to(self.device)

            print("Loading EasyOCR model...")
            self.easyocr_reader = easyocr.Reader(
                # ['en', 'ne'],
                ['en'],
                gpu=(self.device == 'cuda'),
                model_storage_directory=os.path.join(settings.BASE_DIR, 'models/ocr'),
                download_enabled=False
            )
            print("Models loaded successfully!")