from django.apps import AppConfig
from django.conf import settings
import torch
import os


class TollAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'toll_app'

    device = None
    coco_model = None
    plate_model = None
    easyocr_reader = None
    models_loaded = False

    def ready(self):
        if not os.environ.get('DJANGO_LOAD_MODELS'):
            os.environ['DJANGO_LOAD_MODELS'] = '1'
            # self.load_models()

    def load_models(self):
        if self.models_loaded:
            return

        try:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"Using device: {self.device}")

            print("Loading YOLOV8n model...")
            self.coco_model = self._load_yolo_model('models/od/yolov8n.pt')

            print("Loading Custom Number Plate Recognition model...")
            self.plate_model = self._load_yolo_model('models/od/best.pt')

            print("Loading EasyOCR model...")
            self.easyocr_reader = self._load_easyocr_model()

            self.models_loaded = True
            print("Models loaded successfully!")

        except Exception as e:
            print(f"Error loading models: {e}")
            self.coco_model = None
            self.plate_model = None
            self.easyocr_reader = None

    def _load_yolo_model(self, model_path):
        try:
            from ultralytics import YOLO
            full_path = os.path.join(settings.BASE_DIR, model_path)
            model = YOLO(full_path)
            model.to(self.device)
            return model
        except Exception as e:
            print(f"Error loading YOLO model {model_path}: {e}")
            return None

    def _load_easyocr_model(self):
        try:
            import easyocr
            return easyocr.Reader(
                ['en'],
                gpu=(self.device == 'cuda'),
                model_storage_directory=os.path.join(settings.BASE_DIR, 'models/ocr'),
                download_enabled=False
            )
        except Exception as e:
            print(f"Error loading EasyOCR model: {e}")
            return None

    def get_coco_model(self):
        if not self.models_loaded:
            self.load_models()
        return self.coco_model

    def get_plate_model(self):
        if not self.models_loaded:
            self.load_models()
        return self.plate_model

    def get_easyocr_reader(self):
        if not self.models_loaded:
            self.load_models()
        return self.easyocr_reader

    def get_device(self):
        if self.device is None:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        return self.device