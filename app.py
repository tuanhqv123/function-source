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
    # Trả về đường dẫn tuyệt đối tới tệp font trong thư mục fonts.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(current_dir, 'fonts', font_name)
    if not os.path.isfile(font_path):
        logging.error(f"Không tìm thấy font tại đường dẫn: {font_path}")
        return None
    return font_path

def crop_signature(img):
    """
    Tự động cắt hình ảnh chữ ký để loại bỏ phần nền trắng dư thừa.
    
    Parameters:
        img (PIL.Image.Image): Ảnh chữ ký đã được xử lý nền.
    
    Returns:
        PIL.Image.Image: Ảnh chữ ký đã được cắt.
    """
    logging.info("Bắt đầu cắt chữ ký")
    bbox = img.getbbox()
    if bbox:
        logging.info(f"Bounding box tìm thấy: {bbox}")
        img_cropped = img.crop(bbox)
    else:
        logging.warning("Không tìm thấy chữ ký, sử dụng ảnh gốc.")
        img_cropped = img
    return img_cropped

def resize_signature(img, max_height=70):
    """
    Tự động điều chỉnh kích thước chữ ký để đảm bảo chiều cao không vượt quá max_height.
    Chiều rộng được điều chỉnh theo tỷ lệ để giữ nguyên tỷ lệ hình ảnh.
    
    Parameters:
        img (PIL.Image.Image): Ảnh chữ ký đã được cắt.
        max_height (int): Chiều cao tối đa của chữ ký (pixels).
    
    Returns:
        PIL.Image.Image: Ảnh chữ ký đã được điều chỉnh kích thước.
    """
    logging.info(f"Kiểm tra kích thước chữ ký hiện tại: {img.size}")
    width, height = img.size
    if height > max_height:
        scaling_factor = max_height / height
        new_width = int(width * scaling_factor)
        new_size = (new_width, max_height)
        img_resized = img.resize(new_size, Image.LANCZOS)
        logging.info(f"Điều chỉnh kích thước chữ ký thành: {img_resized.size}")
        return img_resized
    else:
        logging.info("Kích thước ch ký hợp lý, không cần điều chỉnh.")
        return img

def process_signature(img_bytes, full_name, job_title, date_str, font_size=10):
    try:
        logging.info("Bắt đầu xử lý chữ ký")
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")

        # Tách nền trắng và làm trong suốt
        datas = img.getdata()
        newData = []
        for item in datas:
            # Kiểm tra nếu pixel gần màu trắng để làm trong suốt
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                newData.append((0, 0, 0, 0))  # Trong suốt
            else:
                # Giữ nguyên màu chữ ký
                newData.append(item)
        img.putdata(newData)

        logging.info(f"Kích thước chữ ký sau khi tách nền: {img.size}")

        # Cắt ảnh chữ ký để loại bỏ nền trắng dư thừa
        img_cropped = crop_signature(img)
        logging.info(f"Kích thước chữ ký sau khi cắt: {img_cropped.size}")

        # Điều chỉnh kích thước chữ ký nếu cần
        img_resized = resize_signature(img_cropped, max_height=70)
        logging.info(f"Kích thước chữ ký sau khi điều chỉnh: {img_resized.size}")

        # Load font (fallback nếu không tìm thấy)
        try:
            font_path = get_font_path('Helvetica.ttf')
            if font_path:
                font = ImageFont.truetype(font_path, size=font_size)
                logging.info(f"Sử dụng font từ: {font_path}")
            else:
                raise IOError
        except IOError:
            logging.error("Không tìm thấy font Helvetica, sử dụng font fallback.")
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

        # Thông tin để hiển thị dưới chữ ký
        signature_valid_text = "Signature valid"
        signed_by_text = f"Signed by: {full_name}"
        title_text = f"Title: {job_title}"
        date_text = f"Date: {date_str}"

        # Tạo text box cho mỗi dòng
        dummy_img = Image.new('RGB', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        signature_valid_bbox = dummy_draw.textbbox((0, 0), signature_valid_text, font=font)
        signed_by_bbox = dummy_draw.textbbox((0, 0), signed_by_text, font=font)
        title_bbox = dummy_draw.textbbox((0, 0), title_text, font=font)
        date_bbox = dummy_draw.textbbox((0, 0), date_text, font=font)

        signature_valid_size = (signature_valid_bbox[2] - signature_valid_bbox[0], signature_valid_bbox[3] - signature_valid_bbox[1])
        signed_by_size = (signed_by_bbox[2] - signed_by_bbox[0], signed_by_bbox[3] - signed_by_bbox[1])
        title_size = (title_bbox[2] - title_bbox[0], title_bbox[3] - title_bbox[1])
        date_size = (date_bbox[2] - date_bbox[0], date_bbox[3] - date_bbox[1])

        # Tính toán kích thước canvas để chứa chữ ký và thông tin
        canvas_width = max(img_resized.width, signed_by_size[0], signature_valid_size[0], title_size[0], date_size[0]) + 40
        canvas_height = img_resized.height + signed_by_size[1] + signature_valid_size[1] + title_size[1] + date_size[1] + 60  # Thêm khoảng cách
        canvas = Image.new('RGBA', (int(canvas_width), int(canvas_height)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(canvas)

        # Khởi tạo biến lề trái
        text_left_margin = 20  # Hoặc giá trị bạn muốn

        # Vẽ chữ ký
        signature_x = 0  # Căn lề trái
        signature_y = 5
        canvas.paste(img_resized, (int(signature_x), int(signature_y)), img_resized)

        # Vẽ tên đầy đủ
        full_name_y = signature_y + img_resized.height + 5
        draw.text((text_left_margin, full_name_y), full_name, fill=(0, 0, 0), font=font)  # Vẽ tên đầy đủ

        # Vẽ các dòng văn bản
        text_color_red = (255, 0, 0)  # Màu đỏ cho các thông tin khác

        signature_valid_y = full_name_y + 20  # Căn lề dưới
        draw.text((text_left_margin, signature_valid_y), signature_valid_text, fill=text_color_red, font=font)

        signed_by_y = signature_valid_y + signature_valid_size[1] + 5
        draw.text((text_left_margin, signed_by_y), signed_by_text, fill=text_color_red, font=font)

        title_y = signed_by_y + signed_by_size[1] + 5
        draw.text((text_left_margin, title_y), title_text, fill=text_color_red, font=font)

        date_y = title_y + title_size[1] + 5
        draw.text((text_left_margin, date_y), date_text, fill=text_color_red, font=font)

        img_byte_arr = BytesIO()
        canvas.save(img_byte_arr, format='PNG')
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
        placeholder = request.form.get('placeholder', 'Signature')  # Placeholder mặc định là 'Signature'
        full_name = request.form.get('full_name')
        job_title = request.form.get('job_title')

        # Kiểm tra các tham số bắt buộc
        if not pdf_url or not signature_url:
            logging.error("Không nhận được URL PDF hoặc URL chữ ký")
            return jsonify({"error": "Không nhận được URL PDF hoặc URL chữ ký"}), 400

        if not full_name:
            logging.error("Không nhận được tên đầy đủ")
            return jsonify({"error": "Không nhận được tên đầy đủ"}), 400

        if not job_title:
            logging.error("Không nhận được chức vụ")
            return jsonify({"error": "Không nhận được chức vụ"}), 400

        logging.info(f"Nhận URL PDF: {pdf_url}")
        pdf_stream = download_file(pdf_url)

        logging.info(f"Nhận URL chữ ký: {signature_url}")
        signature_stream = download_file(signature_url)
        signature_bytes = signature_stream.read()

        # Lấy ngày và giờ hiện tại theo múi giờ Việt Nam
        vietnam_tz = timezone('Asia/Ho_Chi_Minh')
        date_str = datetime.now(vietnam_tz).strftime("%d/%m/%Y %H:%M")

        processed_img_bytes = process_signature(signature_bytes, full_name, job_title, date_str)

        # Kiểm tra phiên bản thư viện
        import fitz
        import PIL

        logging.info(f"Phiên bản PyMuPDF: {fitz.__doc__}")
        logging.info(f"Phiên bản Pillow: {PIL.__version__}")

        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")
        output_pdf = fitz.open()

        logging.info(f"Placeholder để tìm kiếm: '{placeholder}'")

        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)

            # Trích xuất và log toàn bộ văn bản của trang
            page_text = page.get_text("text")
            logging.info(f"Nội dung trang {page_num + 1}:\n{page_text}")

            text_instances = page.search_for(placeholder)
            logging.info(f"Trang {page_num + 1}: tìm thấy {len(text_instances)} lần '{placeholder}'")

            # Tạo một trang mới trong output_pdf
            new_page = output_pdf.new_page(width=page.rect.width, height=page.rect.height)
            new_page.show_pdf_page(page.rect, pdf_document, pno=page_num)

            if text_instances:
                logging.info(f"Tìm thấy {len(text_instances)} instances của '{placeholder}' trên trang {page_num + 1}")
                signature_img = Image.open(BytesIO(processed_img_bytes))
                signature_width, signature_height = signature_img.size  # Kích thước đã được cắt và điều chỉnh

                logging.info(f"Kích thước ảnh chữ ký: {signature_width}x{signature_height}")

                for rect in text_instances:
                    # Erase the placeholder text by drawing a white rectangle over it
                    new_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))  # White rectangle to cover the text
                    logging.info(f"Vẽ rectangle để che placeholder tại: {rect}")

                    # Xác định vị trí để chèn chữ ký với kích thước đã cắt và điều chỉnh
                    signature_rect = fitz.Rect(
                        rect.x0,  # Left
                        rect.y0,  # Top
                        rect.x0 + signature_width,  # Right
                        rect.y0 + signature_height  # Bottom
                    )

                    # Nếu chữ ký vượt quá biên trang, điều chỉnh lại
                    if signature_rect.x1 > page.rect.width - 20:
                        signature_rect.x0 = page.rect.width - 20 - signature_width
                        signature_rect.x1 = page.rect.width - 20

                    if signature_rect.y1 > page.rect.height - 20:
                        signature_rect.y0 = page.rect.height - 20 - signature_height
                        signature_rect.y1 = page.rect.height - 20

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