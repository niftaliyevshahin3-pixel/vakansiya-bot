"""
run_scraper.py — GitHub Actions Scraping Entry Point
=====================================================
GitHub Actions hər gün bu faylı çağırır.
"""
import logging
from database import cedvelleri_yarat
from scraper  import tam_scraping_apar

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)

if __name__ == "__main__":
    cedvelleri_yarat()
    yeni = tam_scraping_apar(max_sehife=5)
    print(f"✅ Scraping tamamlandı: {yeni} yeni elan saxlanıldı")
