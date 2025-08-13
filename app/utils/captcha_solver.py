import ddddocr
import base64
from app.db.database import record_captcha

class CaptchaSolver:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr(show_ad=False)

    def solve(self, captcha_json):
        # Extract the base64 image string
        img_data = captcha_json['data']['img']
        # Remove the 'data:image/jpeg;base64,' prefix
        base64_str = img_data.split(",")[1]

        # decode base64 to bytes
        img_data = base64.b64decode(base64_str)
        result = self.ocr.classification(img_data)

        captcha_id = record_captcha(result, img_data)
        
        return result, captcha_id