from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import logging
import requests
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def process_signature(img_bytes, full_name, img_width=200, img_height=100, font_size=24):
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
        original_width, original_height = img.size
        aspect_ratio = original_width / original_height
        if (img_width / img_height) > aspect_ratio:
            img_width = int(img_height * aspect_ratio)
        else:
            img_height = int(img_width / aspect_ratio)
        img = img.resize((img_width, img_height), Image.Resampling.LANCZOS)

        canvas_height = img_height + font_size + 10
        canvas = Image.new('RGBA', (img_width, canvas_height), (255, 255, 255, 0))
        canvas.paste(img, (0, 0), img)

        draw = ImageDraw.Draw(canvas)

        try:
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'times.ttf')
            font = ImageFont.truetype(font_path, size=font_size)
        except IOError:
            logging.error("Không tìm thấy font Times New Roman, sử dụng font mặc định.")
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), full_name, font=font)
        text_width = bbox[2] - bbox[0]

        text_position = ((img_width - text_width) / 2, img_height + 5)
        draw.text(text_position, full_name, fill="black", font=font)

        img_byte_arr = BytesIO()
        canvas.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()
    except Exception as e:
        logging.error(f"Lỗi trong process_signature: {e}")
        raise

def download_file(url):
    try:
        logging.info(f"Đang tải file từ URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        return BytesIO(response.content)
    except Exception as e:
        logging.error(f"Lỗi khi tải file từ URL {url}: {e}")
        raise

@app.route('/add_signature', methods=['POST'])
def add_signature():
    logging.info("Nhận yêu cầu tới /add_signature")
    try:
        pdf_url = request.form.get('pdf_url')
        signature_url = request.form.get('signature_url')

        if not pdf_url or not signature_url:
            logging.error("Không nhận được URL PDF hoặc URL chữ ký")
            return jsonify({"error": "Không nhận được URL PDF hoặc URL chữ ký"}), 400

        full_name = request.form.get('full_name')
        if not full_name:
            logging.error("Không nhận được tên đầy đủ")
            return jsonify({"error": "Không nhận được tên đầy đủ"}), 400

        logging.info(f"Nhận URL PDF: {pdf_url}")
        pdf_stream = download_file(pdf_url)

        logging.info(f"Nhận URL chữ ký: {signature_url}")
        signature_stream = download_file(signature_url)
        signature_bytes = signature_stream.read()

        processed_img_bytes = process_signature(signature_bytes, full_name)

        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
        output_pdf = BytesIO()

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            width, height = page.rect.width, page.rect.height
            signature_img = Image.open(BytesIO(processed_img_bytes))
            signature_width, signature_height = signature_img.size

            rect = fitz.Rect(
                width - 100 - signature_width,
                height - 100 - signature_height,
                width - 100,
                height - 100
            )

            page.insert_image(rect, stream=processed_img_bytes, overlay=True)

        pdf_document.save(output_pdf)
        pdf_document.close()

        output_pdf.seek(0)
        logging.info("Trả về file PDF đã ký")
        return send_file(output_pdf, as_attachment=True, download_name='signed_output.pdf', mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Lỗi trong add_signature: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)