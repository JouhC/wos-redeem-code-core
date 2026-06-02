from PIL import Image
import base64
import io
import json
import numpy as np
import onnxruntime as ort
from app.db.supabase import record_captcha


MODEL_PATH = "app/model/captcha_model.onnx"
META_PATH = "app/model/captcha_model_metadata.json"


class CaptchaSolver:
    def __init__(self):
        self.session = ort.InferenceSession(MODEL_PATH)
        with open(META_PATH, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

    def preprocess_image(self, image: Image.Image):
        channels, height, width = self.metadata["input_shape"]

        img = image.resize((width, height)).convert('L')  # convert to grayscale

        arr = np.asarray(img).astype(np.float32) / 255.0

        mean = self.metadata["normalization"]["mean"][0]
        std = self.metadata["normalization"]["std"][0]
        arr = (arr - mean) / std

        # Shape: [1, C, H, W]
        if channels == 1:
            arr = arr[np.newaxis, np.newaxis, :, :]
        else:
            arr = np.repeat(arr[np.newaxis, :, :], channels, axis=0)
            arr = arr[np.newaxis, :, :, :]

        return arr

    def solve(self, captcha_json):
        image_data = captcha_json["data"]["img"]
        base64_str = image_data.split(",")[1]

        raw_bytes = base64.b64decode(base64_str)
        image = Image.open(io.BytesIO(raw_bytes))

        arr = self.preprocess_image(image)

        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: arr})

        predicted_text = ""
        confidences = []

        idx_to_char = self.metadata["idx_to_char"]
        output_positions = self.metadata["output_positions"]

        for pos in range(output_positions):
            probs = outputs[pos]
            probs = np.squeeze(probs)

            max_idx = int(np.argmax(probs))
            max_prob = float(probs[max_idx])

            predicted_text += idx_to_char[str(max_idx)]
            confidences.append(max_prob)
        
        captcha_id = record_captcha(predicted_text, raw_bytes)

        return predicted_text, captcha_id


def main():
    solver = CaptchaSolver()
    result = solver.solve("captcha.png")
    print(result)


if __name__ == "__main__":
    main()