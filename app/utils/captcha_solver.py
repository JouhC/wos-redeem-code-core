import base64
import io
import cv2
import numpy as np
import ddddocr
from app.db.database import record_captcha

class CaptchaSolver:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr(show_ad=False)

    def preprocess_captcha(self, image_bytes: bytes) -> bytes:
        # Convert bytes to OpenCV image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Failed to decode captcha image.")

        # Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Threshold
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

        # Remove small noise
        kernel = np.ones((2, 2), np.uint8)
        opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # Encode back to bytes
        is_success, buffer = cv2.imencode(".jpg", opening)
        if not is_success:
            raise ValueError("Failed to encode processed captcha image.")

        return io.BytesIO(buffer).getvalue()

    def solve(self, captcha_json):
        # Extract base64 image string
        img_data = captcha_json["data"]["img"]

        # Remove prefix like data:image/jpeg;base64,
        base64_str = img_data.split(",")[1]

        # Decode base64 to bytes
        raw_bytes = base64.b64decode(base64_str)

        # Preprocess before OCR
        processed_bytes = self.preprocess_captcha(raw_bytes)

        # OCR
        result = self.ocr.classification(processed_bytes)

        captcha_id = record_captcha(result, raw_bytes)

        return result, captcha_id
        