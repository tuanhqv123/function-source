from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import logging
import requests
import os
from datetime import datetime
import numpy as np

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def remove_background(img):
    if img.format == 'PNG':
        return img
    
    img_array = np.array(img)
    alpha = img_array[:, :, 3]
    threshold = np.array(alpha).mean() * 0.8
    mask = alpha > threshold
    img_array[:, :, 3] = mask * 255
    return Image.fromarray(img_array)

def process_signature(img_bytes, full_name, job_title, img_scale=0.4, font_size=36):
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
        img = remove_background(img)
        
        img_width = int(img.width * img_scale)
        img_height = int(img.height * img_scale)
        img = img.resize((img_width, img_height), Image.Resampling.LANCZOS)

        canvas_width = max(img_width, 600)
        canvas_height = img_height + 150
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (255, 255, 255, 0))
        
        signature_position = (50, 0)
        canvas.paste(img, signature_position, img)

        draw = ImageDraw.Draw(canvas)

        try:
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'times.ttf')
            font = ImageFont.truetype(font_path, size=font_size)
        except IOError:
            logging.error("Không tìm thấy font Times New Roman, sử dụng font mặc định.")
            font = ImageFont.load_default()

        current_datetime = datetime.now().strftime("%H giờ, %M phút, Ngày %d, tháng %m, năm %Y")
        date_bbox = draw.textbbox((0, 0), current_datetime, font=font)
        date_width = date_bbox[2] - date_bbox[0]
        date_position = (canvas_width - date_width - 50, img_height + 20)
        draw.text(date_position, current_datetime, fill="black", font=font)

        name_bbox = draw.textbbox((0, 0), full_name, font=font)
        name_width = name_bbox[2] - name_bbox[0]
        name_position = (canvas_width - name_width - 50, img_height + 60)
        draw.text(name_position, full_name, fill="black", font=font)

        job_bbox = draw.textbbox((0, 0), job_title, font=font)
        job_width = job_bbox[2] - job_bbox[0]
        job_position = (canvas_width - job_width - 50, img_height + 100)
        draw.text(job_position, job_title, fill="black", font=font)

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

        job_title = request.form.get('job_title')
        if not job_title:
            logging.error("Không nhận được chức danh")
            return jsonify({"error": "Không nhận được chức danh"}), 400

        logging.info(f"Nhận URL PDF: {pdf_url}")
        pdf_stream = download_file(pdf_url)

        logging.info(f"Nhận URL chữ ký: {signature_url}")
        signature_stream = download_file(signature_url)
        signature_bytes = signature_stream.read()

        processed_img_bytes = process_signature(signature_bytes, full_name, job_title)

        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
        output_pdf = BytesIO()

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            width, height = page.rect.width, page.rect.height
            signature_img = Image.open(BytesIO(processed_img_bytes))
            signature_width, signature_height = signature_img.size

            rect = fitz.Rect(
                width - signature_width - 50,
                height - signature_height - 50,
                width - 50,
                height - 50
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