"""
cv_analiz.py — Anthropic API ilə CV Analizi
============================================
PDF CV-ni oxuyur, Anthropic API-sinə göndərir,
strukturlu analiz nəticəsi qaytarır.
"""

import logging, os, re
from config import ANTHROPIC_API_KEY

log = logging.getLogger(__name__)


def _pdf_oxu(fayl_yolu: str) -> str:
    """PDF-dən mətn çıxar. pdfplumber → fallback PyMuPDF."""
    try:
        import pdfplumber
        metn = ""
        with pdfplumber.open(fayl_yolu) as pdf:
            for sehife in pdf.pages:
                mətn_sehife = sehife.extract_text() or ""
                metn += mətn_sehife + "\n"
        return metn.strip()
    except Exception as e:
        log.error(f"PDF oxuma xətası: {e}")
        return ""


def cv_analiz_et(fayl_yolu: str,
                 istifadeci_sahe: str = "",
                 vakansiya_metn: str = "") -> str:
    """
    CV-ni analiz edib strukturlu Telegram mesajı qaytarır.

    fayl_yolu      : PDF faylının yolu
    istifadeci_sahe: İstifadəçinin seçdiyi sahə (profilindən)
    vakansiya_metn : Əgər vakansiya mətni varsa uyğunluq faizi hesablanır
    """
    import anthropic

    cv_metn = _pdf_oxu(fayl_yolu)
    if not cv_metn or len(cv_metn) < 50:
        return "❌ CV faylı oxuna bilmədi. PDF formatında, mətn əsaslı CV göndər."

    # Çox uzun CV-ləri kəs (API limitinə görə)
    cv_metn = cv_metn[:4000]

    # ── Sistem promptu ────────────────────────────────────────────
    sistem_prompt = """Sən peşəkar CV analitikisən. 
Azərbaycan iş bazarını dərindən bilirsən.
Analiz etdiyin CV haqqında:
1. Güclü tərəfləri tap
2. Zəif/çatışmayan tərəfləri göstər
3. Konkret təkmilləşdirmə tövsiyələri ver
4. Əgər vakansiya mətni verilərsə uyğunluq faizi hesabla

Cavabını MÜTLƏQ bu strukturda ver (emoji-ləri saxla):

📊 UYĞUNLUQ: XX% (yalnız vakansiya verilərsə)

✅ GÜCLÜ TƏRƏFLƏRİ:
• [birinci güclü tərəf]
• [ikinci güclü tərəf]
• [üçüncü güclü tərəf]

⚠️ TƏKMİLLƏŞDİRİLMƏLİ:
• [birinci problem]
• [ikinci problem]

🎯 TÖVSİYƏLƏR:
1. [birinci konkret addım]
2. [ikinci konkret addım]
3. [üçüncü konkret addım]

💡 ƏLAVƏ QEYD:
[qısa ümumi dəyərləndirmə]

Azərbaycan dilində yaz. Qısa, konkret, faydalı ol."""

    # ── İstifadəçi promptu ────────────────────────────────────────
    istifadeci_prompt = f"CV məzmunu:\n\n{cv_metn}"

    if istifadeci_sahe:
        istifadeci_prompt += f"\n\nİstifadəçinin hədəf sahəsi: {istifadeci_sahe}"

    if vakansiya_metn:
        istifadeci_prompt += f"\n\nMüqayisə ediləcək vakansiya:\n{vakansiya_metn[:1000]}"
        istifadeci_prompt += "\n\nBu vakansiya üçün uyğunluq faizini mütləq hesabla."

    # ── Anthropic API sorğusu ─────────────────────────────────────
    try:
        client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model      = "claude-sonnet-4-20250514",
            max_tokens = 1000,
            system     = sistem_prompt,
            messages   = [{"role": "user", "content": istifadeci_prompt}]
        )
        cavab = message.content[0].text

        # Başlıq əlavə et
        başlıq = "🔍 <b>CV Analiz Nəticəsi</b>\n\n"
        return başlıq + cavab

    except anthropic.AuthenticationError:
        log.error("Anthropic API açarı yanlışdır!")
        return "❌ Servis müvəqqəti əlçatmazdır. Yenidən cəhd edin."
    except anthropic.RateLimitError:
        log.warning("Anthropic rate limit!")
        return "⏳ Sistem sənin sorğunu işləyir, 1 dəqiqə sonra yenidən cəhd et."
    except Exception as e:
        log.error(f"CV analiz xəta: {e}")
        return "❌ Analiz zamanı xəta baş verdi. Fayl düzgün PDF formatındadırmı?"
