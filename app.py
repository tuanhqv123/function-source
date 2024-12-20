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

def get_font_path(font_name='Helvetica.ttf'):
    """
    Trả về đường dẫn tuyệt đối tới tệp font trong thư mục fonts.
    """
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
        img_resized = img.resize(new_size, Image.LANCZOS)  # Sử dụng LANCZOS để anti-aliasing
        logging.info(f"Điều chỉnh kích thước chữ ký thành: {img_resized.size}")
        return img_resized
    else:
        logging.info("Kích thước chữ ký hợp lý, không cần điều chỉnh.")
        return img

def process_signature(img_bytes):
    """Chỉ xử lý phần chữ ký"""
    try:
        logging.info("Bắt đầu xử lý chữ ký")
        img = Image.open(BytesIO(img_bytes)).convert("RGBA")

        # Tách nền trắng và làm trong suốt
        datas = img.getdata()
        newData = []
        for item in datas:
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                newData.append((0, 0, 0, 0))  # Trong suốt
            else:
                newData.append(item)
        img.putdata(newData)

        # Cắt ảnh chữ ký để loại bỏ nền trắng dư thừa
        img_cropped = crop_signature(img)
        
        # Điều chỉnh kích thước chữ ký nếu cần
        img_resized = resize_signature(img_cropped, max_height=70)
        
        # Chuyển về bytes
        img_byte_arr = BytesIO()
        img_resized.save(img_byte_arr, format='PNG')
        return img_byte_arr.getvalue()

    except Exception as e:
        logging.error(f"Lỗi trong process_signature: {e}")
        raise

def create_signature_info(full_name, job_title, date_str):
    """
    Tạo ảnh chứa thông tin chữ ký với kích thước font khác nhau:
    - Họ và Tên: Font size 12
    - Các thông tin khác: Font size 11
    """
    try:
        # Tăng scale để có độ phân giải cao hơn
        scale_factor = 3

        # Kích thước font
        font_size_name = 12 * scale_factor  # Font size cho Họ và Tên
        font_size_others = 11 * scale_factor  # Font size cho Chức vụ, Signature valid, và Ngày

        # Load font
        try:
            font_path = get_font_path('Helvetica.ttf')
            if font_path:
                font_name = ImageFont.truetype(font_path, size=font_size_name)
                font_others = ImageFont.truetype(font_path, size=font_size_others)
            else:
                raise IOError
        except IOError:
            try:
                fallback_font_path = get_font_path('DejaVuSerif.ttf')
                if fallback_font_path:
                    font_name = ImageFont.truetype(fallback_font_path, size=font_size_name)
                    font_others = ImageFont.truetype(fallback_font_path, size=font_size_others)
                else:
                    raise IOError
            except IOError:
                font_name = ImageFont.load_default()
                font_others = ImageFont.load_default()

        # Thông tin để hiển thị
        name_text = full_name
        signature_valid_text = "Signature valid"
        signed_by_text = f"Signed by: {full_name}"
        title_text = f"Title: {job_title}"
        date_text = f"Date: {date_str}"

        # Tạo text box cho mỗi dòng với kích thước được scale
        dummy_img = Image.new('RGB', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        name_bbox = dummy_draw.textbbox((0, 0), name_text, font=font_name)
        signature_valid_bbox = dummy_draw.textbbox((0, 0), signature_valid_text, font=font_others)
        signed_by_bbox = dummy_draw.textbbox((0, 0), signed_by_text, font=font_others)
        title_bbox = dummy_draw.textbbox((0, 0), title_text, font=font_others)
        date_bbox = dummy_draw.textbbox((0, 0), date_text, font=font_others)

        # Tính toán kích thước canvas
        canvas_width = max(
            name_bbox[2],
            signature_valid_bbox[2],
            signed_by_bbox[2],
            title_bbox[2],
            date_bbox[2]
        ) + (40 * scale_factor)

        canvas_height = (
            name_bbox[3] +
            signature_valid_bbox[3] +
            signed_by_bbox[3] +
            title_bbox[3] +
            date_bbox[3]
        ) + (45 * scale_factor)

        # Tạo canvas độ phân giải cao với nền trong suốt
        canvas = Image.new('RGBA', (int(canvas_width), int(canvas_height)), (255, 255, 255, 0))
        draw = ImageDraw.Draw(canvas)

        # Vẽ tên đầy đủ với màu đen (font size 12)
        y_pos = 5 * scale_factor
        draw.text((20 * scale_factor, y_pos), name_text, fill=(0, 0, 0), font=font_name, stroke_width=0)
        
        # Tăng khoảng cách trước "Signature valid"
        y_pos += name_bbox[3] + (15 * scale_factor)

        # Vẽ các dòng thông tin signature với màu đỏ (font size 11)
        text_color_red = (255, 0, 0)
        line_spacing = 3 * scale_factor
        
        for text in [signature_valid_text, signed_by_text, title_text, date_text]:
            draw.text((20 * scale_factor, y_pos), text, 
                     fill=text_color_red, 
                     font=font_others,
                     stroke_width=0)  # Tắt stroke để chữ nét hơn
            bbox = draw.textbbox((0, 0), text, font=font_others)
            y_pos += bbox[3] + line_spacing

        # Scale xuống kích thước gốc với chất lượng cao
        original_size = (int(canvas_width/scale_factor), int(canvas_height/scale_factor))
        canvas = canvas.resize(original_size, Image.Resampling.LANCZOS)

        # Chuyển về bytes với chất lượng cao
        img_byte_arr = BytesIO()
        canvas.save(img_byte_arr, format='PNG', dpi=(300, 300), quality=95)
        return img_byte_arr.getvalue()

    except Exception as e:
        logging.error(f"Lỗi trong create_signature_info: {e}")
        raise

def download_file(url):
    """
    Tải xuống tệp từ URL và trả về thư viện BytesIO chứa nội dung.

    Parameters:
        url (str): URL của tệp cần tải xuống.

    Returns:
        BytesIO: Thư viện BytesIO chứa nội dung của tệp.
    """
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

        # Xử lý chữ ký
        processed_signature = process_signature(signature_bytes)
        
        # Tạo ảnh thông tin signature
        signature_info = create_signature_info(full_name, job_title, date_str)

        # Xử lý PDF
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
                signature_img = Image.open(BytesIO(processed_signature))
                signature_width, signature_height = signature_img.size  # Kích thước đã được cắt và điều chỉnh

                logging.info(f"Kích thước ảnh chữ ký: {signature_width}x{signature_height}")

                for rect in text_instances:
                    # Xóa placeholder bằng cách vẽ một hình chữ nhật màu trắng lên đó
                    new_page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))  # Màu trắng

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
                    new_page.insert_image(signature_rect, stream=BytesIO(processed_signature))
                    logging.info("Chữ ký đã được chèn vào PDF")

                    # Chèn thông tin signature
                    info_img = Image.open(BytesIO(signature_info))
                    info_width, info_height = info_img.size
                    
                    info_rect = fitz.Rect(
                        rect.x0,
                        signature_rect.y1 + 5,
                        rect.x0 + info_width,
                        signature_rect.y1 + 5 + info_height
                    )
                    new_page.insert_image(info_rect, stream=BytesIO(signature_info))

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