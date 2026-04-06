# Phân Tích Chuyên Sâu Ý Tưởng Phát Triển Hệ Thống

Dưới đây là phân tích chi tiết về 2 hướng phát triển đột phá cho dự án: **Cá nhân hóa gợi ý** và **Trợ lý ảo (Chatbot) tư vấn phim**, giúp bạn có những luận điểm sắc bén khi trao đổi với giảng viên.

---

## 🚀 Ý tưởng 1: Cá nhân hóa sâu (Personalized Recommendation)

### 1. Bản chất sự thay đổi
*   **Hiện tại (Item-Based):** Hệ thống đang gợi ý dựa trên nội dung phim (Phim A giống phim B). Nếu 100 người cùng xem phim *Interstellar*, cả 100 người đều nhận ra các gợi ý giống hệt nhau.
*   **Tương lai (User-Centered):** Hệ thống sẽ dựa trên "Chân dung sở thích" của từng người dùng. Gợi ý cho bạn sẽ khác hoàn toàn gợi ý cho tôi, dù chúng ta đang xem cùng một bộ phim.

### 2. Giải pháp kỹ thuật (Nói với thầy)
Em sẽ áp dụng mô hình **Hybrid Filtering (Lọc hỗn hợp)** kết hợp 2 kỹ thuật:
*   **Content-based (Đã có):** Dùng Vector Embedding để hiểu nội dung phim.
*   **Collaborative Filtering (Lọc cộng tác):** Sử dụng các thư viện như `Surprise` hoặc `LightFM` để phân tích ma trận tương tác (User-Item Matrix). Nếu người dùng A và B có hành vi xem phim tương đương, hệ thống sẽ lấy phim người B đã xem để gợi ý cho người A.
*   **User Embedding:** Chuyển lịch sử xem phim của một người thành một vector 384 chiều (cùng không gian với phim). Khi tìm kiếm, ta chỉ cần tìm các bộ phim có vector gần nhất với "vector sở thích" của người đó.

### 3. Giá trị mang lại
*   **Tăng tỷ lệ giữ chân (Retention):** Người dùng cảm thấy ứng dụng hiểu mình hơn.
*   **Khám phá (Discovery):** Giúp người dùng tìm thấy những bộ phim họ thực sự thích nhưng chưa từng biết tên.

---

## 🤖 Ý tưởng 2: Trợ lý AI tư vấn phim (AI Cinema Concierge)

### 1. Bản chất sự thay đổi
*   **Hiện tại:** Người dùng phải chủ động nhập từ khóa vào thanh tìm kiếm khô khan.
*   **Tương lai:** Một cuộc hội thoại tự nhiên. Thay vì tìm "Phim hành động", người dùng có thể nói: *"Tối nay tôi cảm thấy hơi buồn, hãy tìm cho tôi một bộ phim hoạt hình nhẹ nhàng của Ghibli nhưng phải có kết thúc hạnh phúc nhé."*

### 2. Giải pháp kỹ thuật (Nói với thầy)
Em sẽ sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)**:
*   **LLM (Large Language Model):** Sử dụng API của GPT-4 hoặc mô hình mã nguồn mở như Llama-3 (chạy local) để hiểu ngôn ngữ tự nhiên.
*   **Kết nối dữ liệu (Cốt lõi):** LLM sẽ không tự "chế" ra phim. Khi nhận câu hỏi, LLM sẽ đóng vai trò trích xuất ý định (Intent), sau đó gọi vào hàm `semantic_search` trong file `services.py` hiện tại của em để lấy đúng dữ liệu phim trong database.
*   **Phản hồi:** LLM nhận danh sách phim trả về và viết thành một đoạn giới thiệu thuyết phục người dùng.

### 3. Giá trị mang lại
*   **Trải nghiệm người dùng (UX) hiện đại:** Biến việc tìm phim từ "tra cứu" thành "trò chuyện".
*   **Xử lý các truy vấn phức tạp:** Giải quyết được những yêu cầu mà thanh tìm kiếm thông thường không bao giờ làm được (ví dụ tìm theo cảm xúc hoặc tình huống cụ thể).

---

## 💡 Tổng kết luận điểm trình bày
Khi thầy hỏi về hướng phát triển, bạn nên nhấn mạnh vào cụm từ: **"Chuyển đổi từ tìm kiếm bị động sang gợi ý chủ động và tương tác tự nhiên."**

1.  **Gợi ý chủ động:** Thông qua Personalized Recommendation, hệ thống tự mang phim đến cho người dùng trước khi họ cần tìm.
2.  **Tương tác tự nhiên:** Thông qua AI Chatbot, rào cản giữa con người và cơ sở dữ liệu bị xóa bỏ, giúp bất kỳ ai cũng có thể tìm được bộ phim ưng ý chỉ bằng cách nói chuyện.
