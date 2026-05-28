"""
payriff.py — Payriff.com Ödəniş İnteqrasiyası
===============================================
Payriff Azərbaycanın yerli ödəniş şlüzüdür.
Visa/Mastercard, M10, Kapital Bank kartları qəbul edir.

QURAŞDIRMA:
  1. payriff.com-da biznes hesabı aç
  2. API açarlarını al (dashboard → API Keys)
  3. Webhook URL-ni qur: https://sənin-url.railway.app/payriff/webhook
  4. .env faylına PAYRIFF_API_KEY və PAYRIFF_SECRET yaz

API SƏNƏDLƏRI: https://payriff.com/docs
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime

import httpx

from config import PAYRIFF_API_KEY, PAYRIFF_SECRET, PREMIUM_QİYMƏT

log = logging.getLogger(__name__)

PAYRIFF_BASE_URL = "https://api.payriff.com/api/v2"


async def odenis_linki_yarat(
    telegram_id: int,
    mebleg: float = PREMIUM_QİYMƏT,
    aciklama: str = "Vakansiya Botu — Premium Abunə (1 ay)"
) -> dict:
    """
    Payriff-də ödəniş sessiyası yarat, ödəniş linkini qaytarır.

    Qaytarılan dict:
      success      : bool
      payment_url  : str  (istifadəçini bu linkə yönləndir)
      order_id     : str  (webhook-da identifikasiya üçün)
      xeta         : str  (uğursuz olduqda)
    """
    if not PAYRIFF_API_KEY:
        log.error("PAYRIFF_API_KEY tapılmadı!")
        return {"success": False, "xeta": "Ödəniş sistemi konfiqurasiya edilməyib."}

    # Webhook URL — Railway-dəki botun ünvanı
    webhook_base = os.getenv("WEBHOOK_URL", "https://your-app.railway.app")
    geri_url     = f"{webhook_base}/payriff/success"
    xeta_url     = f"{webhook_base}/payriff/cancel"

    # Sifariş ID-si — telegram_id + timestamp
    order_id = f"PRE-{telegram_id}-{int(datetime.now().timestamp())}"

    sorgu_govdesi = {
        "amount":      int(mebleg * 100),  # qəpik cinsindən
        "currency":    "AZN",
        "orderId":     order_id,
        "description": aciklama,
        "language":    "az",
        "callbackUrl": f"{webhook_base}/payriff/webhook",
        "successUrl":  geri_url,
        "cancelUrl":   xeta_url,
        "merchantId":  os.getenv("PAYRIFF_MERCHANT_ID", ""),
    }

    başlıqlar = {
        "Authorization": f"Bearer {PAYRIFF_API_KEY}",
        "Content-Type":  "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            cavab = await client.post(
                f"{PAYRIFF_BASE_URL}/orders/payment",
                json    = sorgu_govdesi,
                headers = başlıqlar,
            )
            cavab.raise_for_status()
            məlumat = cavab.json()

        if məlumat.get("code") == "00000":  # Payriff uğur kodu
            return {
                "success":     True,
                "payment_url": məlumat["payload"]["paymentUrl"],
                "order_id":    order_id,
            }
        else:
            log.error(f"Payriff xəta: {məlumat}")
            return {"success": False, "xeta": "Ödəniş linki yaradıla bilmədi."}

    except httpx.TimeoutException:
        return {"success": False, "xeta": "Ödəniş serveri cavab vermir. Yenidən cəhd et."}
    except Exception as e:
        log.error(f"Payriff sorğu xəta: {e}")
        return {"success": False, "xeta": "Ödəniş sistemilə bağlantı xətası."}


def webhook_imzasini_yoxla(imza: str, gövdə: bytes) -> bool:
    """
    Payriff webhook-unun həqiqiliyini HMAC ilə yoxla.
    Bu yoxlama olmadan saxta webhook göndərilə bilər — TƏHLÜKƏSİZLİK vacibdir!
    """
    if not PAYRIFF_SECRET:
        log.warning("PAYRIFF_SECRET tapılmadı — webhook yoxlama deaktivdir!")
        return True  # Development rejimindən istifadə etmə produksiyada!

    gözlənilən = hmac.new(
        PAYRIFF_SECRET.encode(),
        gövdə,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(imza, gözlənilən)


def webhook_parse(gövdə: dict) -> dict | None:
    """
    Payriff webhook gövdəsini parse et.
    Uğurlu ödəniş üçün order_id qaytarır.

    Payriff webhook nümunəsi:
    {
      "code": "00000",
      "payload": {
        "orderId": "PRE-123456789-1234567890",
        "status": "APPROVED",
        "amount": 1000
      }
    }
    """
    try:
        payload = gövdə.get("payload", {})
        status  = payload.get("status", "")
        order   = payload.get("orderId", "")
        code    = gövdə.get("code", "")

        if code == "00000" and status in ("APPROVED", "SUCCESS", "PAID"):
            return {"order_id": order, "status": "tamamlandi"}
        else:
            return {"order_id": order, "status": "uğursuz"}
    except Exception as e:
        log.error(f"Webhook parse xəta: {e}")
        return None
