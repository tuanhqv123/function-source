import os
import logging
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF

app = Flask(__name__)

# Cấu hình logging
logging.basicConfig(level=logging.INFO)

def process_signature(img_bytes, full_name, job_title, img_width=400, img_height=200, font_size=36):
    try:
        # Mở hình ảnh chữ ký
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")

        # Thay đổi kích thước hình chữ ký, giữ nguyên tỷ lệ
        original_width, original_height = img.size
        aspect_ratio = original_width / original_height
        if (img_width / img_height) > aspect_ratio:
            img_width = int(img_height * aspect_ratio)
        else:
            img_height = int(img_width / aspect_ratio)
        img = img.resize((int(img_width), int(img_height)), Image.Resampling.LANCZOS)

        # Tải font chữ
        try:
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'times.ttf')
            font = ImageFont.truetype(font_path, size=font_size)
        except IOError:
            logging.error("Không tìm thấy font Times New Roman, sử dụng font mặc định.")
            font = ImageFont.load_default()

        # Lấy thông tin thời gian hiện tại
        current_datetime = datetime.now().strftime("%H giờ, %M phút, Ngày %d, tháng %m, năm %Y")

        # Tính toán kích thước của các dòng văn bản
        dummy_img = Image.new('RGB', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        datetime_bbox = dummy_draw.textbbox((0, 0), current_datetime, font=font)
        name_bbox = dummy_draw.textbbox((0, 0), full_name, font=font)
        job_title_bbox = dummy_draw.textbbox((0, 0), job_title, font=font)

        datetime_size = (datetime_bbox[2] - datetime_bbox[0], datetime_bbox[3] - datetime_bbox[1])
        name_size = (name_bbox[2] - name_bbox[0], name_bbox[3] - name_bbox[1])
        job_title_size = (job_title_bbox[2] - job_title_bbox[0], job_title_bbox[3] - job_title_bbox[1])

        # Tạo canvas
        canvas_width = max(img_width, datetime_size[0], name_size[0], job_title_size[0]) + 80
        canvas_height = datetime_size[1] + img_height + name_size[1] + job_title_size[1] + 120
        canvas = Image.new('RGBA', (int(canvas_width), int(canvas_height)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(canvas)

        # Vẽ thời gian ở trên cùng, căn giữa
        datetime_x = (canvas_width - datetime_size[0]) / 2
        datetime_y = 20
        draw.text((datetime_x, datetime_y), current_datetime, fill="black", font=font)

        # Vẽ hình chữ ký ở giữa
        signature_x = (canvas_width - img_width) / 2
        signature_y = datetime_y + datetime_size[1] + 20
        canvas.paste(img, (int(signature_x), int(signature_y)), img)

        # Vẽ tên đầy đủ dưới chữ ký, căn giữa
        name_x = (canvas_width - name_size[0]) / 2
        name_y = signature_y + img_height + 20
        draw.text((name_x, name_y), full_name, fill="black", font=font)

        # Vẽ chức vụ dưới tên đầy đủ, căn giữa
        job_title_x = (canvas_width - job_title_size[0]) / 2
        job_title_y = name_y + name_size[1] + 10
        draw.text((job_title_x, job_title_y), job_title, fill="black", font=font)

        # Lưu canvas vào bytes
        img_byte_arr = BytesIO()
        canvas.save(img_byte_arr, format='PNG')

        return img_byte_arr.getvalue()
    except Exception as e:
        logging.error(f"Lỗi trong process_signature: {e}")
        raise

@app.route('/add_signature', methods=['POST'])
def add_signature():
    logging.info("Nhận yêu cầu tới /add_signature")
    try:
        # Nhận file PDF và thông tin chữ ký từ request
        if 'pdf' not in request.files or 'signature' not in request.files:
            return jsonify({"error": "Thiếu file PDF hoặc chữ ký"}), 400

        pdf_file = request.files['pdf']
        signature_file = request.files['signature']
        full_name = request.form.get('full_name', 'Người ký')
        job_title = request.form.get('job_title', 'Chức vụ')

        # Đọc nội dung của các file
        pdf_stream = pdf_file.read()
        signature_bytes = signature_file.read()

        # Xử lý chữ ký
        processed_img_bytes = process_signature(signature_bytes, full_name, job_title)

        # Mở PDF và thêm chữ ký
        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
        output_pdf = BytesIO()

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            width, height = page.rect.width, page.rect.height
            signature_img = Image.open(BytesIO(processed_img_bytes))
            
            # Tăng kích thước chữ ký
            new_width = int(width * 0.4)  # 40% chiều rộng trang
            new_height = int(new_width * signature_img.size[1] / signature_img.size[0])
            signature_img = signature_img.resize((new_width, new_height), Image.LANCZOS)
            
            signature_width, signature_height = signature_img.size

            # Xoay ảnh chữ ký 180 độ
            signature_img = signature_img.rotate(180)
            
            # Lật ngược ảnh theo chiều ngang (mirror)
            signature_img = signature_img.transpose(Image.FLIP_LEFT_RIGHT)
            
            modified_signature_bytes = BytesIO()
            signature_img.save(modified_signature_bytes, format='PNG')
            modified_signature_bytes = modified_signature_bytes.getvalue()

            # Vị trí chèn chữ ký ở góc phải bên dưới
            margin_right = 30  # Khoảng cách từ mép phải trang
            margin_bottom = 30  # Khoảng cách từ mép dưới trang
            rect = fitz.Rect(
                width - signature_width - margin_right,
                height - signature_height - margin_bottom,
                width - margin_right,
                height - margin_bottom
            )

            # Chèn ảnh chữ ký đã xoay và lật ngược vào PDF
            page.insert_image(rect, stream=modified_signature_bytes, overlay=True)

        pdf_document.save(output_pdf)
        pdf_document.close()

        output_pdf.seek(0)
        logging.info("Trả về file PDF đã ký")
        return send_file(output_pdf, as_attachment=True, download_name='signed_output.pdf', mimetype='application/pdf')
    except Exception as e:
        logging.error(f"Lỗi trong add_signature: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)