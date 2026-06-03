import sys
import threading
from django.apps import AppConfig

class MoviesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.movies'

    def ready(self):
        # 1. Giữ nguyên import signals cũ của bạn (Rất quan trọng)
        from . import signals  # noqa: F401

        # 2. Khai báo hàm chạy ngầm để tải mô hình AI vào RAM
        def load_ai_models_background():
            try:
                # Gọi 2 hàm này để ép hệ thống tải model ngay lập tức
                from .ml_utils import get_sentiment_pipeline
                from .services import get_semantic_model
                
                print("Bắt đầu nạp ngầm các mô hình AI (DistilBERT & MiniLM)...")
                get_sentiment_pipeline()
                get_semantic_model()
                print("Đã nạp xong tất cả mô hình AI vào RAM!")
            except Exception as e:
                print("Lỗi nạp model ngầm:", e)

        # 3. Kích hoạt luồng chạy ngầm (Chỉ chạy khi bật Server thật)
        # Bỏ qua lúc chạy lệnh migrate hay collectstatic để tiết kiệm thời gian build
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv or any('gunicorn' in arg for arg in sys.argv):
            t = threading.Thread(target=load_ai_models_background)
            t.daemon = True  # Đảm bảo luồng ngầm sẽ tự tắt khi server tắt
            t.start()