"""
config.py — Mərkəzi Konfiqurasiya
==================================
Bütün sabitlər, sahə kateqoriyaları, açar sözlər burada.
Dəyişmək lazım olduqda yalnız bu faylı yeniləmək kifayətdir.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # .env faylından mühit dəyişənlərini yüklə

# ══════════════════════════════════════════════════════
# ƏSAS KREDENSİALLAR — .env faylından gəlir
# ══════════════════════════════════════════════════════
BOT_TOKEN          = os.getenv("BOT_TOKEN", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
PAYRIFF_API_KEY    = os.getenv("PAYRIFF_API_KEY", "")
PAYRIFF_SECRET     = os.getenv("PAYRIFF_SECRET", "")
ADMIN_IDS          = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]
WEBHOOK_URL        = os.getenv("WEBHOOK_URL", "")   # Railway URL
WEBHOOK_SECRET     = os.getenv("WEBHOOK_SECRET", "")

# ══════════════════════════════════════════════════════
# BOT AYARLARI
# ══════════════════════════════════════════════════════
PULSUZ_LIMIT       = 3     # Pulsuz istifadəçiyə gündə neçə elan
PREMIUM_LIMIT      = 20    # Premium istifadəçiyə gündə neçə elan
PREMIUM_QİYMƏT     = 10    # AZN/ay
ELAN_GONDERME_SAATI = 8    # Hər gün saat neçədə göndərilsin (Bakı vaxtı)
ERKƏN_GİRİŞ_SAAT   = 6    # Premium neçə saat əvvəl görür

DB_YOLU            = os.getenv("DB_YOLU", "vakansiya.db")

# ══════════════════════════════════════════════════════
# SCRAPINQ AYARLARI
# ══════════════════════════════════════════════════════
MIN_GÖZLƏMƏ        = 3     # Sorğular arası minimum fasilə (saniyə)
MAX_GÖZLƏMƏ        = 7     # Sorğular arası maksimum fasilə
MAX_CƏHD           = 3     # Uğursuz sorğu üçün təkrar cəhd sayı

# Hədəf saytlar — robots.txt yoxlandıqdan sonra aktiv et
SAYTLAR = {
    "jobsearch": {
        "ad":        "JobSearch.az",
        "aktiv":     True,
        "satis_url": "https://jobsearch.az/vacancies",
    },
    "boss": {
        "ad":        "Boss.az",
        "aktiv":     True,
        "satis_url": "https://boss.az/vacancies",
    },
    "ejob": {
        "ad":        "eJob.az",
        "aktiv":     True,
        "satis_url": "https://ejob.az/vacancies",
    },
    "jobex": {
        "ad":        "Jobex.az",
        "aktiv":     True,
        "satis_url": "https://jobex.az/vacancies",
    },
    "hh": {
        "ad":        "hh.az",
        "aktiv":     True,
        "satis_url": "https://hh.az/vacancies",
    },
}

# ══════════════════════════════════════════════════════
# SAHƏ KATEQORİYALARI VƏ AÇAR SÖZLƏR
# ══════════════════════════════════════════════════════
SAHƏLƏR = {
    "🛢 Neft/Qaz": {
        "açar_sözlər": [
            "neft","qaz","petroleum","oil","gas","socar","drilling",
            "reservoir","geologist","geofizika","offshore","upstream",
            "downstream","refinery","boru","pipeline","mühəndis","engineer",
            "petrokimya","petrochemical","lqn","lng","lpg","kompressor",
        ],
        "alt_sahələr": ["Hasilat","Emal/Refinery","Geoloji","Qazma","Laboratoriya","Layihə"],
    },
    "💻 İT/Texnologiya": {
        "açar_sözlər": [
            "developer","proqramçı","software","python","java","javascript",
            "frontend","backend","fullstack","devops","data","cybersecurity",
            "network","database","sql","cloud","mobile","android","ios",
            "1c","erp","sap","it support","system","qa","test","ui","ux",
        ],
        "alt_sahələr": ["Proqramlaşdırma","Data/AI","Şəbəkə/Sistem","Kibertəhlükəsizlik","QA/Test"],
    },
    "💰 Maliyyə/Bank": {
        "açar_sözlər": [
            "mühasib","accountant","maliyyə","finance","bank","kredit",
            "credit","audit","vergi","tax","iqtisadçı","economist",
            "investisiya","risk","treasury","xəzinə","sığorta","insurance",
            "büdcə","budget","mühasibat","cfo","controller",
        ],
        "alt_sahələr": ["Mühasibat","Bank əməliyyatları","Audit","Sığorta","Risk"],
    },
    "⚕️ Tibb/Sağlamlıq": {
        "açar_sözlər": [
            "həkim","doctor","tibb","medical","nurse","cərrah","surgeon",
            "aptek","pharmacy","stomatolog","psixoloq","laborant","radiolog",
            "klinika","xəstəxana","sanitar","hemşirə","anesteziolog",
        ],
        "alt_sahələr": ["Klinik","Stomatoloji","Psixologiya","Əczaçılıq","Laboratoriya"],
    },
    "⚖️ Hüquq": {
        "açar_sözlər": [
            "hüquqşünas","lawyer","vəkil","advocate","notarius","yurist",
            "compliance","kontrakt","müqavilə","məhkəmə","hüquq",
        ],
        "alt_sahələr": ["Korporativ","Cinayət","Compliance","Əqli mülkiyyət"],
    },
    "🏗 Tikinti/Mühəndislik": {
        "açar_sözlər": [
            "tikinti","construction","memar","architect","layihə","project",
            "inşaat","elektrik","electrical","mexanik","mechanical",
            "hidro","structural","AutoCAD","revit","smeta","qiymətləndirmə",
        ],
        "alt_sahələr": ["Tikinti","Elektrik","Mexanik","Memarlıq","Layihə idarəetməsi"],
    },
    "📦 Logistika/Nəqliyyat": {
        "açar_sözlər": [
            "logistika","logistics","sürücü","driver","ekspeditor",
            "forwarder","anbar","warehouse","idxal","ixrac","import",
            "export","gömrük","customs","brokər","təchizat","supply chain",
        ],
        "alt_sahələr": ["Anbar","Nəqliyyat","Gömrük","Ekspedisiya","Satınalma"],
    },
    "📢 Marketing/Satış": {
        "açar_sözlər": [
            "marketing","satış","sales","smm","reklam","advertising",
            "pr","brend","brand","digital","müştəri","customer","kontent",
            "content","seo","sem","e-commerce","ticarət nümayəndəsi",
        ],
        "alt_sahələr": ["Digital Marketing","Satış","SMM","PR/Brend","E-ticarət"],
    },
    "👔 HR/İnsan Resursları": {
        "açar_sözlər": [
            "hr","human resources","işə qəbul","recruitment","kadr",
            "personnel","təlim","training","maaş","payroll","korporativ",
        ],
        "alt_sahələr": ["İşə qəbul","Kadr inkişafı","Əmək münasibətləri","Payroll"],
    },
    "📚 Təhsil": {
        "açar_sözlər": [
            "müəllim","teacher","təhsil","education","tutor","tədris",
            "metodist","məktəb","school","universitet","kurs","coach",
        ],
        "alt_sahələr": ["Məktəb","Universitet","Xüsusi kurslar","Körpüsahib"],
    },
    "🛒 Pərakəndə/Restoran": {
        "açar_sözlər": [
            "kassir","cashier","satıcı","seller","mağaza","store","market",
            "aşpaz","cook","ofisiant","waiter","barmen","barista",
            "restoran","restaurant","café","kafe","supermarket",
        ],
        "alt_sahələr": ["Pərakəndə satış","Restoran/Kafe","Otel/Turizm"],
    },
    "🌐 Digər": {
        "açar_sözlər": [],
        "alt_sahələr": [],
    },
}

# Bazar orta maaşları (AZN) — Maaş göstərilməyən elanlar üçün
# Bu rəqəmlər Azərbaycan bazarına əsaslanan təxmini dəyərlərdir
BAZAR_MAAŞ = {
    "🛢 Neft/Qaz":           (1500, 4000),
    "💻 İT/Texnologiya":     (1200, 3500),
    "💰 Maliyyə/Bank":       (900,  2500),
    "⚕️ Tibb/Sağlamlıq":    (600,  2000),
    "⚖️ Hüquq":              (800,  2500),
    "🏗 Tikinti/Mühəndislik":(800,  2500),
    "📦 Logistika/Nəqliyyat":(700,  1800),
    "📢 Marketing/Satış":    (700,  2000),
    "👔 HR/İnsan Resursları": (700,  1800),
    "📚 Təhsil":              (500,  1500),
    "🛒 Pərakəndə/Restoran":  (500,  1200),
    "🌐 Digər":               (600,  1500),
}
