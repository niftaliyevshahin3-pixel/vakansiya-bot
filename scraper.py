"""
scraper.py — 5 Saytdan Vakansiya Toplama Sistemi
=================================================
Hədəf saytlar: jobsearch.az, boss.az, ejob.az, jobex.az, hh.az

5 QORUMA TƏBƏQƏSİ:
  1. 15 fərqli User-Agent rotasiyası
  2. Qeyri-müntəzəm (random) fasilələr
  3. Session yeniləmə hər 10-15 sorğudan bir
  4. Honeypot element filtri
  5. Gecə saatlarında işləmə (GitHub Actions cron)

ƏSAS QEYD:
  CSS selektor adları (* ilə işarələnib) Bina.az metodikası ilə
  müəyyənləşdirilməlidir: saytı aç → sağ klik → Inspect →
  elan kartının class adını tap → aşağıdakı yerə yaz.
"""

import hashlib, logging, random, re, time
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (SAHƏLƏR, SAYTLAR, MIN_GÖZLƏMƏ,
                    MAX_GÖZLƏMƏ, MAX_CƏHD, BAZAR_MAAŞ)
from database import elan_saxla

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
# QORUMA TƏBƏQƏSİ 1: USER-AGENT ROTASİYASI
# ══════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OPR/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
]


class AntiBotSession:
    """
    Bütün 5 qoruma təbəqəsini tətbiq edən session sinifi.
    Hər scraper instance bu sinfin bir nüsxəsini istifadə edir.
    """

    def __init__(self):
        self.session     = requests.Session()
        self.sorgu_sayı  = 0
        self._yenile()

    def _yenile(self):
        """Yeni brauzer kimliyi — hər 10-15 sorğudan bir çağırılır."""
        agent = random.choice(USER_AGENTS)
        self.session.headers.update({
            "User-Agent":                agent,
            "Accept":                    "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language":           "az-AZ,az;q=0.9,en;q=0.7,ru;q=0.5",
            "Accept-Encoding":           "gzip, deflate, br",
            "Connection":                "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "same-origin",
            "Cache-Control":             "max-age=0",
        })
        # Cookie-ləri sıfırla
        self.session.cookies.clear()

    def _gozle(self):
        """
        QORUMA 2: Qeyri-müntəzəm fasilə.
        Hər 8 sorğudan birində uzun fasilə (oxuma simulyasiyası).
        """
        self.sorgu_sayı += 1

        # QORUMA 3: Session yeniləmə
        if self.sorgu_sayı % random.randint(10, 15) == 0:
            self._yenile()
            log.debug("Session yeniləndi")

        if self.sorgu_sayı % 8 == 0:
            t = random.uniform(15, 25)
            log.debug(f"Uzun fasilə: {t:.0f}s")
            time.sleep(t)
        else:
            time.sleep(random.uniform(MIN_GÖZLƏMƏ, MAX_GÖZLƏMƏ))

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """Sorğu göndər — xəta olduqda MAX_CƏHD qədər yenidən cəhd et."""
        self._gozle()
        for cəhd in range(MAX_CƏHD):
            try:
                r = self.session.get(url, timeout=15, **kwargs)
                r.raise_for_status()
                return r
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 429:
                    # Rate limited — 60 saniyə gözlə
                    log.warning("Rate limit! 60s gözlənilir...")
                    time.sleep(60)
                elif e.response and e.response.status_code in (403, 503):
                    # Blok — session yenilə, 30s gözlə
                    self._yenile()
                    time.sleep(30)
                else:
                    log.error(f"HTTP xəta ({url}): {e}")
                    break
            except requests.exceptions.ConnectionError:
                log.warning(f"Bağlantı xətası ({url}), {cəhd+1}/{MAX_CƏHD}")
                time.sleep(20)
            except requests.exceptions.Timeout:
                log.warning(f"Zaman aşımı ({url})")
                break
        return None


def _honeypot_mu(element) -> bool:
    """
    QORUMA 4: Honeypot (tələ) elementlərini tanı.
    Gizli CSS ilə saxlanmış elementlər — insan görməz, robot izləyər.
    """
    style = element.get("style", "").replace(" ", "").lower()
    cls   = " ".join(element.get("class", [])).lower()
    gizli = [
        "display:none", "visibility:hidden", "opacity:0",
        "left:-9", "top:-9", "position:absolute;left",
        "trap", "bot-check", "honeypot", "hidden"
    ]
    return any(g in style or g in cls for g in gizli)


# ══════════════════════════════════════════════════════
# MAAŞ PARSINQ KÖMƏKÇİSİ
# ══════════════════════════════════════════════════════

def _maas_parse(maas_metn: str) -> tuple[Optional[int], Optional[int], str]:
    """
    Müxtəlif formatları işlə:
    '1500 AZN' → (1500, 1500, '1500 AZN')
    '1500 - 2500 AZN' → (1500, 2500, '1500–2500 AZN')
    'Razılaşma əsasında' → (None, None, 'Razılaşma əsasında')
    """
    if not maas_metn:
        return None, None, ""

    metn = maas_metn.strip()
    rəqəmlər = re.findall(r"\d[\d\s]*\d|\d+", metn)
    rəqəmlər = [int(r.replace(" ", "")) for r in rəqəmlər if int(r.replace(" ", "")) > 100]

    if len(rəqəmlər) >= 2:
        return min(rəqəmlər), max(rəqəmlər), f"{min(rəqəmlər):,}–{max(rəqəmlər):,} AZN"
    elif len(rəqəmlər) == 1:
        return rəqəmlər[0], rəqəmlər[0], f"{rəqəmlər[0]:,} AZN"
    else:
        return None, None, metn  # "Razılaşma" və s.


def _elan_id_yarat(link: str, baslik: str) -> str:
    """Unikal elan ID — link + başlıqdan hash."""
    return hashlib.md5(f"{link}{baslik}".encode()).hexdigest()[:16]


def _kategoriya_tap(baslik: str, aciklama: str) -> str:
    """Elanın başlıq + açıqlamasına görə sahə kateqoriyası müəyyənləşdir."""
    metn = f"{baslik} {aciklama}".lower()
    max_uygun = 0
    uygun_sahə = "🌐 Digər"

    for sahə, məlumat in SAHƏLƏR.items():
        say = sum(1 for söz in məlumat["açar_sözlər"] if söz in metn)
        if say > max_uygun:
            max_uygun = say
            uygun_sahə = sahə

    return uygun_sahə


def _bazar_maas_mesaji(kategoriya: str) -> str:
    """Maaş göstərilməyən elanlar üçün bazar məlumatı."""
    aralik = BAZAR_MAAŞ.get(kategoriya, (600, 2000))
    return f"💡 Bazar orta: {aralik[0]:,}–{aralik[1]:,} AZN"


# ══════════════════════════════════════════════════════
# SAYT-SPESIFIK SCRAPERS
# ══════════════════════════════════════════════════════
#
# HƏR SCRAPER ÜÇÜN UYĞUNLAŞDIRMA:
# 1. Saytı brauzerindən aç
# 2. Bir elan kartının üzərindən sağ klik → Inspect
# 3. Xarici div-in class adını tap → KART_CLASS-a yaz
# 4. İçindəki başlıq, maaş, şirkət elementlərini tap → uyğun dəyişənlərə yaz
# (* ilə işarələnmiş yerlər uyğunlaşdırılmalıdır)
# ══════════════════════════════════════════════════════

class JobSearchScraper:
    """jobsearch.az üçün scraper"""
    AD   = "JobSearch.az"
    URL  = SAYTLAR["jobsearch"]["satis_url"]

    def __init__(self, session: AntiBotSession):
        self.s = session

    def sehife_scrape(self, sehife: int = 1) -> list[dict]:
        url = f"{self.URL}?page={sehife}"
        r   = self.s.get(url)
        if not r:
            return []

        soup   = BeautifulSoup(r.text, "html.parser")
        # * Faktiki class adı → Inspect ilə tap
        kartlar = soup.find_all("div", class_=re.compile(
            r"vacancy-item|job-item|list-item|vacancy_item", re.I
        ))

        nəticə = []
        for kart in kartlar:
            if _honeypot_mu(kart):   # QORUMA 4
                continue
            e = self._kart_parse(kart)
            if e:
                nəticə.append(e)
        return nəticə

    def _kart_parse(self, kart) -> Optional[dict]:
        try:
            # * Bu selektor adlarını Inspect ilə yoxla
            baslik_el  = kart.find(["h2","h3","a"],
                            class_=re.compile(r"title|name|vacancy.name", re.I))
            sirket_el  = kart.find(["span","div"],
                            class_=re.compile(r"company|employer|sirket", re.I))
            maas_el    = kart.find(["span","div"],
                            class_=re.compile(r"salary|maas|price", re.I))
            yer_el     = kart.find(["span","div"],
                            class_=re.compile(r"location|city|region", re.I))
            link_el    = kart.find("a", href=True)
            tarix_el   = kart.find(["span","time"],
                            class_=re.compile(r"date|time|posted", re.I))

            baslik = baslik_el.get_text(strip=True) if baslik_el else ""
            if not baslik:
                return None

            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://jobsearch.az" + link

            maas_metn = maas_el.get_text(strip=True) if maas_el else ""
            maas_min, maas_max, maas_format = _maas_parse(maas_metn)

            aciklama  = kart.get_text(separator=" ", strip=True)[:500]
            kategoriya = _kategoriya_tap(baslik, aciklama)

            return {
                "id":        _elan_id_yarat(link, baslik),
                "baslik":    baslik,
                "sirket":    sirket_el.get_text(strip=True) if sirket_el else "",
                "maas_min":  maas_min,
                "maas_max":  maas_max,
                "maas_metn": maas_format or _bazar_maas_mesaji(kategoriya),
                "yer":       yer_el.get_text(strip=True) if yer_el else "Bakı",
                "link":      link,
                "menbe":     self.AD,
                "kategoriya":kategoriya,
                "aciklama":  aciklama,
            }
        except Exception as ex:
            log.debug(f"Parse xəta (JobSearch): {ex}")
            return None


class BossScraper:
    """boss.az üçün scraper"""
    AD  = "Boss.az"
    URL = SAYTLAR["boss"]["satis_url"]

    def __init__(self, session: AntiBotSession):
        self.s = session

    def sehife_scrape(self, sehife: int = 1) -> list[dict]:
        url = f"{self.URL}?page={sehife}"
        r   = self.s.get(url)
        if not r:
            return []

        soup   = BeautifulSoup(r.text, "html.parser")
        # * Boss.az-ın faktiki kart class adı
        kartlar = soup.find_all("div", class_=re.compile(
            r"vacancies-item|job-card|vacancy", re.I
        ))

        return [e for e in (self._kart_parse(k) for k in kartlar
                            if not _honeypot_mu(k)) if e]

    def _kart_parse(self, kart) -> Optional[dict]:
        try:
            baslik_el  = kart.find(["h2","h3","a"],
                            class_=re.compile(r"title|position|job.name", re.I))
            sirket_el  = kart.find(class_=re.compile(r"company|employer", re.I))
            maas_el    = kart.find(class_=re.compile(r"salary|wage", re.I))
            yer_el     = kart.find(class_=re.compile(r"location|city", re.I))
            link_el    = kart.find("a", href=True)

            baslik = baslik_el.get_text(strip=True) if baslik_el else ""
            if not baslik:
                return None

            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://boss.az" + link

            maas_metn  = maas_el.get_text(strip=True) if maas_el else ""
            maas_min, maas_max, maas_format = _maas_parse(maas_metn)
            aciklama   = kart.get_text(separator=" ", strip=True)[:500]
            kategoriya = _kategoriya_tap(baslik, aciklama)

            return {
                "id":        _elan_id_yarat(link, baslik),
                "baslik":    baslik,
                "sirket":    sirket_el.get_text(strip=True) if sirket_el else "",
                "maas_min":  maas_min, "maas_max": maas_max,
                "maas_metn": maas_format or _bazar_maas_mesaji(kategoriya),
                "yer":       yer_el.get_text(strip=True) if yer_el else "Bakı",
                "link":      link,
                "menbe":     self.AD,
                "kategoriya":kategoriya,
                "aciklama":  aciklama,
            }
        except Exception as ex:
            log.debug(f"Parse xəta (Boss): {ex}")
            return None


class EJobScraper:
    """ejob.az üçün scraper"""
    AD  = "eJob.az"
    URL = SAYTLAR["ejob"]["satis_url"]

    def __init__(self, session: AntiBotSession):
        self.s = session

    def sehife_scrape(self, sehife: int = 1) -> list[dict]:
        url = f"{self.URL}?page={sehife}"
        r   = self.s.get(url)
        if not r:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        kartlar = soup.find_all(class_=re.compile(r"vacancy|job.item|listing", re.I))
        return [e for e in (self._parse(k) for k in kartlar
                            if not _honeypot_mu(k)) if e]

    def _parse(self, kart) -> Optional[dict]:
        try:
            baslik_el = kart.find(["h2","h3","a"],
                          class_=re.compile(r"title|name", re.I))
            link_el   = kart.find("a", href=True)
            sirket_el = kart.find(class_=re.compile(r"company|employer", re.I))
            maas_el   = kart.find(class_=re.compile(r"salary|maas", re.I))
            yer_el    = kart.find(class_=re.compile(r"location|city", re.I))

            baslik = baslik_el.get_text(strip=True) if baslik_el else ""
            if not baslik:
                return None

            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://ejob.az" + link

            maas_metn  = maas_el.get_text(strip=True) if maas_el else ""
            maas_min, maas_max, maas_format = _maas_parse(maas_metn)
            aciklama   = kart.get_text(separator=" ", strip=True)[:500]
            kategoriya = _kategoriya_tap(baslik, aciklama)

            return {
                "id": _elan_id_yarat(link, baslik), "baslik": baslik,
                "sirket": sirket_el.get_text(strip=True) if sirket_el else "",
                "maas_min": maas_min, "maas_max": maas_max,
                "maas_metn": maas_format or _bazar_maas_mesaji(kategoriya),
                "yer": yer_el.get_text(strip=True) if yer_el else "Bakı",
                "link": link, "menbe": self.AD,
                "kategoriya": kategoriya, "aciklama": aciklama,
            }
        except:
            return None


class JobexScraper:
    """jobex.az üçün scraper"""
    AD  = "Jobex.az"
    URL = SAYTLAR["jobex"]["satis_url"]

    def __init__(self, session):
        self.s = session

    def sehife_scrape(self, sehife=1):
        r = self.s.get(f"{self.URL}?page={sehife}")
        if not r:
            return []
        soup    = BeautifulSoup(r.text, "html.parser")
        kartlar = soup.find_all(class_=re.compile(r"vacancy|job.card|position", re.I))
        return [e for e in (self._parse(k) for k in kartlar
                            if not _honeypot_mu(k)) if e]

    def _parse(self, kart):
        try:
            baslik_el = kart.find(["h2","h3","a"], class_=re.compile(r"title|name", re.I))
            link_el   = kart.find("a", href=True)
            sirket_el = kart.find(class_=re.compile(r"company|firm", re.I))
            maas_el   = kart.find(class_=re.compile(r"salary|income", re.I))
            yer_el    = kart.find(class_=re.compile(r"location|region", re.I))

            baslik = baslik_el.get_text(strip=True) if baslik_el else ""
            if not baslik:
                return None
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://jobex.az" + link

            maas_metn  = maas_el.get_text(strip=True) if maas_el else ""
            maas_min, maas_max, maas_format = _maas_parse(maas_metn)
            aciklama   = kart.get_text(separator=" ", strip=True)[:500]
            kategoriya = _kategoriya_tap(baslik, aciklama)

            return {
                "id": _elan_id_yarat(link, baslik), "baslik": baslik,
                "sirket": sirket_el.get_text(strip=True) if sirket_el else "",
                "maas_min": maas_min, "maas_max": maas_max,
                "maas_metn": maas_format or _bazar_maas_mesaji(kategoriya),
                "yer": yer_el.get_text(strip=True) if yer_el else "Bakı",
                "link": link, "menbe": self.AD,
                "kategoriya": kategoriya, "aciklama": aciklama,
            }
        except:
            return None


class HHScraper:
    """hh.az üçün scraper"""
    AD  = "hh.az"
    URL = SAYTLAR["hh"]["satis_url"]

    def __init__(self, session):
        self.s = session

    def sehife_scrape(self, sehife=1):
        r = self.s.get(f"{self.URL}?page={sehife}")
        if not r:
            return []
        soup    = BeautifulSoup(r.text, "html.parser")
        kartlar = soup.find_all(
            attrs={"data-qa": re.compile(r"vacancy.serp.item|vacancy.card", re.I)}
        ) or soup.find_all(class_=re.compile(r"vacancy|resume.serp", re.I))
        return [e for e in (self._parse(k) for k in kartlar
                            if not _honeypot_mu(k)) if e]

    def _parse(self, kart):
        try:
            baslik_el = kart.find(attrs={"data-qa": re.compile(r"vacancy.title|serp.item.title", re.I)}) \
                        or kart.find(["h2","h3","a"])
            link_el   = kart.find("a", href=True)
            sirket_el = kart.find(attrs={"data-qa": re.compile(r"vacancy.company", re.I)}) \
                        or kart.find(class_=re.compile(r"company|employer", re.I))
            maas_el   = kart.find(attrs={"data-qa": re.compile(r"vacancy.serp.item.compensation", re.I)}) \
                        or kart.find(class_=re.compile(r"salary|compensation", re.I))
            yer_el    = kart.find(attrs={"data-qa": re.compile(r"vacancy.address", re.I)}) \
                        or kart.find(class_=re.compile(r"location|address", re.I))

            baslik = baslik_el.get_text(strip=True) if baslik_el else ""
            if not baslik:
                return None
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://hh.az" + link

            maas_metn  = maas_el.get_text(strip=True) if maas_el else ""
            maas_min, maas_max, maas_format = _maas_parse(maas_metn)
            aciklama   = kart.get_text(separator=" ", strip=True)[:500]
            kategoriya = _kategoriya_tap(baslik, aciklama)

            return {
                "id": _elan_id_yarat(link, baslik), "baslik": baslik,
                "sirket": sirket_el.get_text(strip=True) if sirket_el else "",
                "maas_min": maas_min, "maas_max": maas_max,
                "maas_metn": maas_format or _bazar_maas_mesaji(kategoriya),
                "yer": yer_el.get_text(strip=True) if yer_el else "Bakı",
                "link": link, "menbe": self.AD,
                "kategoriya": kategoriya, "aciklama": aciklama,
            }
        except:
            return None


# ══════════════════════════════════════════════════════
# ANA SCRAPING ORKESTRASİYASI
# ══════════════════════════════════════════════════════

def tam_scraping_apar(max_sehife: int = 5) -> int:
    """
    Bütün aktiv saytlardan elanları topla, verilənlər bazasına yaz.
    GitHub Actions tərəfindən hər gün bir dəfə çağırılır.
    max_sehife: hər saytdan neçə səhifə (1 səhifə ≈ 20 elan)
    """
    log.info(f"Scraping başladı — {max_sehife} səhifə × {len(SAYTLAR)} sayt")
    session = AntiBotSession()
    scrapers = [
        JobSearchScraper(session),
        BossScraper(session),
        EJobScraper(session),
        JobexScraper(session),
        HHScraper(session),
    ]

    cəmi_yeni = 0
    cəmi_elan = 0

    for scraper in scrapers:
        sayt_adi  = scraper.AD
        sayt_yeni = 0

        log.info(f"  {sayt_adi} scraplanır...")
        for sehife in range(1, max_sehife + 1):
            elanlar = scraper.sehife_scrape(sehife)
            if not elanlar:
                log.info(f"    Səhifə {sehife}: elan yoxdur, dayandırılır")
                break

            for e in elanlar:
                cəmi_elan += 1
                if elan_saxla(e):
                    sayt_yeni += 1
                    cəmi_yeni += 1

            log.info(f"    Səhifə {sehife}: {len(elanlar)} elan tapıldı")

        log.info(f"  {sayt_adi}: {sayt_yeni} yeni elan")

    log.info(f"Scraping tamamlandı: {cəmi_elan} elan skan edildi, {cəmi_yeni} yeni saxlanıldı")
    return cəmi_yeni
