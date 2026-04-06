# Giải Thích Chi Tiết Hệ Thống Gợi Ý Phim (Movie Recommendation System)

Tài liệu này tóm tắt toàn bộ cấu trúc và logic của dự án để bạn có thể dễ dàng giải thích cho thầy cô. Hệ thống được xây dựng bằng **Python (Django)** kết hợp với các công nghệ **Trí tuệ nhân tạo (AI)** để tìm kiếm và gợi ý phim.

---

## 1. Cấu trúc Tổng quan (High-level Architecture)
Dự án tuân theo mô hình **MVT (Model-View-Template)** của Django:
*   **Model**: Định nghĩa cấu trúc dữ liệu phím, người dùng, đánh giá.
*   **View**: Xử lý logic nghiệp vụ và kết nối dữ liệu với giao diện.
*   **Template**: Giao diện người dùng (HTML/CSS).
*   **AI Services**: Lớp xử lý đặc biệt dùng để tính toán vector và đưa ra gợi ý.

---

## 2. Chi tiết các thành phần chính (Source Code Breakdown)

### A. Thư mục `config/` (Cấu hình hệ thống)
Đây là "bộ não" điều khiển toàn bộ dự án:
*   `settings.py`: Chứa các cài đặt về Cơ sở dữ liệu (PostgreSQL), bảo mật, và các thư viện hỗ trợ.
*   `urls.py`: Khai báo các đường dẫn (links) của toàn bộ trang web.

### B. Ứng dụng `apps/movies/` (Lõi của hệ thống)
Đây là nơi chứa toàn bộ logic về phim và AI:
1.  **`models.py`**: Định nghĩa bảng `Movie` (thông tin phim), `Genre` (thể loại) và `Review` (đánh giá từ người dùng).
2.  **`services.py` (Quan trọng nhất)**:
    *   Sử dụng mô hình AI `SentenceTransformer` để hiểu ý nghĩa văn bản.
    *   Hàm `semantic_search`: Giúp tìm kiếm phim không chỉ theo từ khóa mà còn theo "ý nghĩa" (ví dụ: tìm "phim buồn" sẽ ra các phim tâm lý mặc dù tiêu đề không có chữ "buồn").
    *   Hàm `get_recommendations`: Sử dụng thuật toán vector (FAISS) để tìm các phim tương tự.
3.  **`views.py`**: Tiếp nhận yêu cầu từ người dùng (như nhấn vào xem chi tiết phim) và gọi các hàm từ `services.py` để lấy dữ liệu hiển thị.

### C. Ứng dụng `apps/accounts/` (Quản lý người dùng)
Xử lý các tính năng cơ bản của một hệ thống web:
*   Đăng ký, Đăng nhập, Đăng xuất.
*   Phân quyền người dùng (User permissions).

---

## 3. Cách AI hoạt động trong dự án này (The AI Logic)

Nếu thầy hỏi "AI nằm ở đâu?", bạn có thể trả lời dựa trên 2 điểm này:
1.  **Chuyển đổi văn bản thành Vector (Embedding)**: Hệ thống chuyển mô tả của mỗi bộ phim thành một dãy số (vector). Các phim có nội dung giống nhau sẽ có các dãy số "gần nhau" trong không gian toán học.
2.  **Tìm kiếm & Gợi ý**:
    *   Khi bạn xem phim A, hệ thống lấy vector của phim A đi so sánh với hàng ngàn phim khác.
    *   **Công thức**: `0.7 * độ giống nhau + 0.3 * điểm đánh giá`. Điều này giúp phim được gợi ý vừa phải giống nội dung, vừa phải là phim hay (rating cao).

---

## 4. Các luồng xử lý chính (Main Workflows)

1.  **Luồng tìm kiếm**: Người dùng nhập từ khóa -> Hệ thống thực hiện tìm kiếm từ khóa TRƯỚC -> Sau đó tìm theo ngữ nghĩa AI SAU -> Gộp kết quả lại và hiển thị.
2.  **Luồng gợi ý**: Khi xem chi tiết một phim -> Hệ thống gọi API AI -> Trả về danh sách 5-10 phim có vector gần nhất.

---

## 5. Công nghệ sử dụng (Tech Stack)
*   **Ngôn ngữ**: Python.
*   **Web Framework**: Django & Django REST Framework (DRF).
*   **Database**: PostgreSQL.
*   **AI Libraries**: 
    *   `sentence-transformers`: Xử lý ngôn ngữ tự nhiên.
    *   `FAISS`: Tìm kiếm vector tốc độ cao.
    *   `NumPy/Scikit-learn`: Tính toán toán học.
