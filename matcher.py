"""
matcher.py — Ağıllı Elan-İstifadəçi Uyğunluq Mühərriki
=========================================================
Hər elan üçün hər istifadəçinin profilinə uyğunluq skoru hesablanır.
Skor 0-100 aralığındadır. Yalnız 40+ skor alanlar göndərilir.
"""

import re
from config import SAHƏLƏR, BAZAR_MAAŞ


def uygunlug_hesabla(elan: dict, istifadeci: dict) -> int:
    """
    Elan ilə istifadəçi profili arasında uyğunluq skoru (0-100).

    Bal sistemi:
      +50 — sahə uyğunluğu (əsas kriteriya)
      +15 — alt sahə uyğunluğu
      +15 — şəhər uyğunluğu
      +10 — maaş uyğunluğu
      +10 — iş rejimi uyğunluğu
      -20 — maaş çox aşağıdırsa (istifadəçinin min-dan aşağı)
    """
    skor = 0

    elan_metn = f"{elan.get('baslik','')} {elan.get('aciklama','')}".lower()
    ist_sahə  = istifadeci.get("sahe", "")
    ist_alt   = istifadeci.get("alt_sahe", "hamisi")

    # ── 1. SAHƏ UYĞUNLUĞU (+50) ─────────────────────────────────
    sahə_info   = SAHƏLƏR.get(ist_sahə, {})
    açar_sözlər = sahə_info.get("açar_sözlər", [])

    if açar_sözlər:
        uyğun_sözlər = sum(1 for söz in açar_sözlər if söz in elan_metn)
        if uyğun_sözlər >= 3:
            skor += 50
        elif uyğun_sözlər >= 2:
            skor += 35
        elif uyğun_sözlər == 1:
            skor += 20
        # Elan kateqoriyası birbaşa uyğundursa bonus
        if elan.get("kategoriya") == ist_sahə:
            skor += 15
    else:
        # "Digər" sahə seçibsə — hamısı uyğundur
        skor += 40

    # ── 2. ALT SAHƏ UYĞUNLUĞU (+15) ────────────────────────────
    if ist_alt and ist_alt != "hamisi":
        if ist_alt.lower() in elan_metn:
            skor += 15

    # ── 3. ŞƏHƏR UYĞUNLUĞU (+15) ────────────────────────────────
    ist_şəhər = istifadeci.get("seher", "Hamısı")
    elan_yer  = elan.get("yer", "").lower()

    if ist_şəhər == "Hamısı":
        skor += 15
    elif ist_şəhər == "Remote":
        if any(s in elan_metn for s in ["remote", "uzaqdan", "evdən"]):
            skor += 15
    elif ist_şəhər.lower() in elan_yer:
        skor += 15

    # ── 4. MAAŞ UYĞUNLUĞU (+10 / -20) ──────────────────────────
    ist_min_maas = istifadeci.get("min_maas", 0)
    ist_max_maas = istifadeci.get("max_maas", 0)
    elan_maas_max = elan.get("maas_max")

    if ist_min_maas == 0:
        # Fərq etməz seçilib
        skor += 10
    elif elan_maas_max is None:
        # Elanda maaş yoxdur — neytral
        skor += 5
    elif elan_maas_max >= ist_min_maas:
        skor += 10
    else:
        # Maaş istifadəçinin minimumundan aşağıdır
        skor -= 20

    # ── 5. İŞ REJİMİ (+10) ──────────────────────────────────────
    ist_rejim  = istifadeci.get("is_rejimi", "hamisi")
    elan_rejim = elan.get("rejim", "").lower()

    if ist_rejim == "hamisi":
        skor += 10
    elif ist_rejim == "remote" and any(
            s in elan_metn for s in ["remote", "uzaqdan", "evdən", "hybrid", "hibrid"]):
        skor += 10
    elif ist_rejim == "ofis" and "remote" not in elan_metn:
        skor += 10
    elif ist_rejim in elan_rejim:
        skor += 10

    return max(0, min(100, skor))  # 0-100 aralığında saxla


def uygunlug_yoxla(elan: dict, istifadeci: dict,
                   min_skor: int = 40) -> bool:
    """Elan bu istifadəçiyə göndərilməlidirsə True qaytarır."""
    skor = uygunlug_hesabla(elan, istifadeci)
    elan["uygunlug_skoru"] = skor   # Sonrakı sıralama üçün saxla
    return skor >= min_skor


def elan_sirket_uygunmu(elan: dict, izlenen_sirketler: list[str]) -> bool:
    """Bu elan izlənən şirkətdən gəlirsə True (şirkət izləmə xüsusiyyəti)."""
    elan_sirket = elan.get("sirket", "").lower()
    return any(s.lower() in elan_sirket for s in izlened_sirketler)
