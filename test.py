from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

def create_pdf_with_vietnamese_text(output_path, text, font_path="DejaVuSans.ttf", font_size=12):
    """
    Tạo file PDF từ văn bản tiếng Việt.

    Args:
        output_path (str): Đường dẫn file PDF đầu ra.
        text (str): Văn bản tiếng Việt cần ghi vào PDF.
        font_path (str): Đường dẫn đến file font hỗ trợ Unicode (mặc định là DejaVuSans.ttf).
        font_size (int): Kích thước font chữ.
    """
    try:
        # Kiểm tra font tồn tại
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Không tìm thấy file font: {font_path}")

        # Đăng ký font
        pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))

        # Tạo file PDF
        c = canvas.Canvas(output_path, pagesize=A4)
        c.setFont("DejaVuSans", font_size)

        # Lấy kích thước trang
        page_width, page_height = A4

        # Viết text vào PDF (hỗ trợ xuống dòng)
        text_lines = text.split("\n")  # Tách dòng
        x, y = 50, page_height - 50  # Vị trí bắt đầu (cách biên trên và trái 50px)
        line_spacing = font_size + 5  # Khoảng cách giữa các dòng

        for line in text_lines:
            if y < 50:  # Nếu xuống dòng quá thấp, tạo trang mới
                c.showPage()
                c.setFont("DejaVuSans", font_size)
                y = page_height - 50

            c.drawString(x, y, line)
            y -= line_spacing  # Di chuyển vị trí vẽ xuống dòng

        # Lưu file PDF
        c.save()
        print(f"PDF đã được tạo thành công tại: {output_path}")

    except Exception as e:
        print(f"Lỗi: {e}")

""
if __name__ == "__main__":
    # Đầu vào văn bản tiếng Việt
    vietnamese_text = """Xin chào!
Đây là một đoạn văn bản tiếng Việt.
Hệ thống này hỗ trợ font Unicode, vì vậy bạn có thể viết tiếng Việt có dấu.
Chúc bạn một ngày tốt lành!"""

    # Đường dẫn tới file font (đảm bảo bạn đã tải font DejaVuSans.ttf hoặc cung cấp font Unicode khác)
    font_file_path = "/Users/tuantran/WorkSpace/Python/function-source/fonts/DejaVuSans.ttf"  # Đặt đường dẫn tới font DejaVuSans.ttf hoặc font Unicode khác

    # Đường dẫn file PDF đầu ra
    output_pdf_path = "output_vietnamese_text.pdf"

    # Tạo PDF từ văn bản
    create_pdf_with_vietnamese_text(output_pdf_path, vietnamese_text, font_file_path, font_size=14)