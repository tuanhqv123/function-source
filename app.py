from flask import Flask, request, jsonify, send_file
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import logging
import requests
import os
from datetime import datetime
from pytz import timezone
from urllib.parse import urlsplit, urlunsplit

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def get_font_path(font_name):
    """
    Trả về đường dẫn tuyệt đối tới tệp font trong thư mục fonts.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(current_dir, 'fonts', font_name)
    if not os.path.isfile(font_path):
        logging.error(f"Không tìm thấy font tại đường dẫn: {font_path}")
        return None
    return font_path

def process_signature(img_bytes, full_name, job_title, img_width=300, img_height=100, font_size=11):
    """
    Xử lý ảnh chữ ký: chuyển nền trắng thành trong suốt, chuyển màu chữ ký thành đỏ, resize ảnh,
    thêm thông tin tên và chức vụ vào ảnh tạo thành ảnh chữ ký hoàn chỉnh.
    """
    try:
        logging.info("Bắt đầu xử lý chữ ký")
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")

        # Tách nền trắng và chuyển chữ ký thành màu đỏ
        datas = img.getdata()
        newData = []
        for item in datas:
            # Kiểm tra nếu pixel gần màu trắng để làm trong suốt
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                newData.append((255, 0, 0, 0))  # Trong suốt với màu đỏ không ảnh hưởng vì alpha=0
            else:
                # Chuyển đổi màu chữ ký thành đỏ, giữ nguyên độ trong suốt
                newData.append((255, 0, 0, item[3]))
        img.putdata(newData)

        original_width, original_height = img.size
        aspect_ratio = original_width / original_height
        if (img_width / img_height) > aspect_ratio:
            img_width = int(img_height * aspect_ratio)
        else:
            img_height = int(img_width / aspect_ratio)
        img = img.resize((int(img_width), int(img_height)), Image.Resampling.LANCZOS)
        logging.info(f"Kích thước chữ ký sau khi resize: {img.size}")

        # Load the font (use fallback if Times New Roman not found)
        try:
            font_path = get_font_path('times.ttf')
            if font_path:
                font = ImageFont.truetype(font_path, size=font_size)
                logging.info(f"Sử dụng font từ: {font_path}")
            else:
                raise IOError
        except IOError:
            logging.error("Không tìm thấy font Times New Roman, sử dụng font fallback.")
            try:
                fallback_font_path = get_font_path('DejaVuSerif.ttf')
                if fallback_font_path:
                    font = ImageFont.truetype(fallback_font_path, size=font_size)
                    logging.info(f"Sử dụng font fallback từ: {fallback_font_path}")
                else:
                    raise IOError
            except IOError:
                logging.error("Không tìm thấy font fallback DejaVuSerif.ttf. Sử dụng font mặc định.")
                font = ImageFont.load_default()

        # Sử dụng múi giờ Việt Nam
        vietnam_tz = timezone('Asia/Ho_Chi_Minh')
        current_datetime = datetime.now(vietnam_tz).strftime("%H giờ, %M phút, Ngày %d, tháng %m, năm %Y")
        logging.info(f"Thời gian hiện tại: {current_datetime}")

        dummy_img = Image.new('RGB', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        datetime_bbox = dummy_draw.textbbox((0, 0), current_datetime, font=font)
        name_bbox = dummy_draw.textbbox((0, 0), full_name, font=font)
        job_title_bbox = dummy_draw.textbbox((0, 0), job_title, font=font)

        datetime_size = (datetime_bbox[2] - datetime_bbox[0], datetime_bbox[3] - datetime_bbox[1])
        name_size = (name_bbox[2] - name_bbox[0], name_bbox[3] - name_bbox[1])
        job_title_size = (job_title_bbox[2] - job_title_bbox[0], job_title_bbox[3] - job_title_bbox[1])

        canvas_width = max(img_width, datetime_size[0], name_size[0], job_title_size[0]) + 40
        canvas_height = datetime_size[1] + img_height + name_size[1] + job_title_size[1] + 70
        canvas = Image.new('RGBA', (int(canvas_width), int(canvas_height)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(canvas)

        datetime_x = (canvas_width - datetime_size[0]) / 2
        datetime_y = 10
        draw.text((datetime_x, datetime_y), current_datetime, fill="black", font=font)

        signature_x = (canvas_width - img_width) / 2
        signature_y = datetime_y + datetime_size[1] + 10
        canvas.paste(img, (int(signature_x), int(signature_y)), img)

        name_x = (canvas_width - name_size[0]) / 2
        name_y = signature_y + img_height + 10
        draw.text((name_x, name_y), full_name, fill="black", font=font)

        job_title_x = (canvas_width - job_title_size[0]) / 2
        job_title_y = name_y + name_size[1] + 5
        draw.text((job_title_x, job_title_y), job_title, fill="black", font=font)

        img_byte_arr = BytesIO()
        canvas.save(img_byte_arr, format='PNG', quality=100)
        logging.info("Chữ ký đã được xử lý và tạo thành công.")

        return img_byte_arr.getvalue()
    except Exception as e:
        logging.error(f"Lỗi trong process_signature: {e}")
        raise

def download_file(url):
    try:
        logging.info(f"Đang tải file từ URL: {url}")
        # Loại bỏ fragment khỏi URL
        split_url = urlsplit(url)
        url_no_fragment = urlunsplit((split_url.scheme, split_url.netloc, split_url.path, split_url.query, ''))
        response = requests.get(url_no_fragment)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        logging.info(f"Content-Type của phản hồi: {content_type}")
        if 'application/pdf' not in content_type:
            logging.error(f"URL không trả về PDF: {url_no_fragment}")
            raise ValueError("URL không trả về PDF")

        logging.info(f"Tải file từ URL: {url_no_fragment} thành công.")
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
            logging.error("Không nhận được chức vụ")
            return jsonify({"error": "Không nhận được chức vụ"}), 400

        logging.info(f"Nhận URL PDF: {pdf_url}")
        pdf_stream = download_file(pdf_url)

        logging.info(f"Nhận URL chữ ký: {signature_url}")
        signature_stream = download_file(signature_url)
        signature_bytes = signature_stream.read()

        processed_img_bytes = process_signature(signature_bytes, full_name, job_title)

        # Kiểm tra phiên bản thư viện
        import fitz
        import PIL

        logging.info(f"Phiên bản PyMuPDF: {fitz.__doc__}")
        logging.info(f"Phiên bản Pillow: {PIL.__version__}")

        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
        output_pdf = fitz.open()

        placeholder_text = "ký tại đây"  # Text to search for

        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)

            # Trích xuất và log toàn bộ văn bản của trang
            page_text = page.get_text("text")
            logging.info(f"Nội dung trang {page_num + 1}:\n{page_text}")

            text_instances = page.search_for(placeholder_text)
            logging.info(f"Trang {page_num + 1}: tìm thấy {len(text_instances)} lần '{placeholder_text}'")

            # Tạo một trang mới trong output_pdf
            new_page = output_pdf.new_page(width=page.rect.width, height=page.rect.height)
            new_page.show_pdf_page(page.rect, pdf_document, pno=page_num)

            if text_instances:
                logging.info(f"Found {len(text_instances)} instances of '{placeholder_text}' on page {page_num + 1}")
                signature_img = Image.open(BytesIO(processed_img_bytes))
                signature_width, signature_height = signature_img.size
                logging.info(f"Kích thước ảnh chữ ký: {signature_width}x{signature_height}")

                for rect in text_instances:
                    # Erase the placeholder text by drawing a white rectangle over it
                    new_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))  # White rectangle to cover the text
                    logging.info(f"Vẽ rectangle để che placeholder tại: {rect}")

                    # Tạo Rect cho chữ ký tại vị trí của placeholder
                    signature_rect = fitz.Rect(
                        rect.x0,  # Left
                        rect.y0,  # Top
                        rect.x0 + signature_width,  # Right
                        rect.y0 + signature_height  # Bottom
                    )
                    logging.info(f"Chèn chữ ký tại rect: {signature_rect}")

                    # Insert the signature image tại vị trí đã định
                    new_page.insert_image(signature_rect, stream=BytesIO(processed_img_bytes), overlay=True)
                    logging.info("Chữ ký đã được chèn vào PDF")

        pdf_document.close()

        output_bytes = BytesIO()
        output_pdf.save(output_bytes)
        output_pdf.close()

        output_bytes.seek(0)
        logging.info("Trả về file PDF đã ký")
        return send_file(
            output_bytes,
            as_attachment=True,
            download_name='signed_output.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        logging.error(f"Lỗi trong add_signature: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Đảm bảo sử dụng PORT từ môi trường Render
    app.run(host='0.0.0.0', port=port)