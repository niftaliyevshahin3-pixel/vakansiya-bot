"""
database.py — Verilənlər Bazası
================================
SQLite ilə işləyir. Railway-də /data/ qovluğuna saxlanır (persistent).
Bütün sorğular thread-safe connection pool istifadə edir.
"""

import sqlite3
import logging
from datetime import datetime, date
from contextlib import contextmanager
from config import DB_YOLU

log = logging.getLogger(__name__)


@contextmanager
def _baglanti():
    """Thread-safe bağlantı idarəetməsi."""
    conn = sqlite3.connect(DB_YOLU, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Paralel oxuma üçün
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.error(f"DB xəta: {e}")
        raise
    finally:
        conn.close()


def cedvelleri_yarat():
    """İlk işə salınmada bütün cədvəlləri yarat."""
    with _baglanti() as conn:
        conn.executescript("""
        -- İstifadəçilər
        CREATE TABLE IF NOT EXISTS istifadeciler (
            telegram_id      INTEGER  PRIMARY KEY,
            ad               TEXT,
            username         TEXT,
            sahe             TEXT,
            alt_sahe         TEXT     DEFAULT 'hamisi',
            seher            TEXT     DEFAULT 'Hamısı',
            min_maas         INTEGER  DEFAULT 0,
            max_maas         INTEGER  DEFAULT 0,
            is_rejimi        TEXT     DEFAULT 'hamisi',
            tecrube          TEXT     DEFAULT 'hamisi',
            plan             TEXT     DEFAULT 'pulsuz',
            premium_bitis    DATE,
            referral_kodu    TEXT     UNIQUE,
            referral_kimden  INTEGER,
            aktiv            INTEGER  DEFAULT 1,
            dil              TEXT     DEFAULT 'az',
            qeydiyyat_tarix  DATETIME DEFAULT CURRENT_TIMESTAMP,
            son_aktivlik     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Elanlar (scraped jobs)
        CREATE TABLE IF NOT EXISTS elanlar (
            id           TEXT     PRIMARY KEY,
            baslik       TEXT,
            sirket       TEXT,
            maas_min     INTEGER,
            maas_max     INTEGER,
            maas_metn    TEXT,
            yer          TEXT,
            rejim        TEXT,
            tecrube_il   INTEGER,
            aciklama     TEXT,
            teleb_sozler TEXT,
            link         TEXT,
            menbe        TEXT,
            kategoriya   TEXT,
            elan_tarixi  DATE,
            scraped_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            aktiv        INTEGER  DEFAULT 1
        );

        -- Göndərilmişlər (spam-ın qarşısını alır)
        CREATE TABLE IF NOT EXISTS gonderilenler (
            id           INTEGER  PRIMARY KEY AUTOINCREMENT,
            telegram_id  INTEGER  REFERENCES istifadeciler(telegram_id),
            elan_id      TEXT     REFERENCES elanlar(id),
            gonderilib   DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(telegram_id, elan_id)
        );

        -- Ödənişlər
        CREATE TABLE IF NOT EXISTS odenisler (
            id              INTEGER  PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER  REFERENCES istifadeciler(telegram_id),
            payriff_order   TEXT     UNIQUE,
            mebleg          REAL,
            valyuta         TEXT     DEFAULT 'AZN',
            status          TEXT     DEFAULT 'gozlenir',
            yaranib         DATETIME DEFAULT CURRENT_TIMESTAMP,
            tamamlanib      DATETIME
        );

        -- Şirkət izləmə (premium xüsusiyyəti)
        CREATE TABLE IF NOT EXISTS sirket_izleme (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER REFERENCES istifadeciler(telegram_id),
            sirket_adi  TEXT,
            UNIQUE(telegram_id, sirket_adi)
        );

        -- Bot mesajlarının loqu (analitika üçün)
        CREATE TABLE IF NOT EXISTS mesaj_loq (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            komanda     TEXT,
            vaxt        DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- İndekslər — sürətli axtarış üçün
        CREATE INDEX IF NOT EXISTS idx_elanlar_tarix     ON elanlar(elan_tarixi);
        CREATE INDEX IF NOT EXISTS idx_elanlar_kategoriya ON elanlar(kategoriya);
        CREATE INDEX IF NOT EXISTS idx_gonderilenler_tid  ON gonderilenler(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_gonderilenler_tarix ON gonderilenler(gonderilib);
        """)
    log.info("Verilənlər bazası cədvəlləri yoxlandı/yaradıldı")


# ══════════════════════════════════════════════════════
# İSTİFADƏÇİ ƏMƏLİYYATLARI
# ══════════════════════════════════════════════════════

def istifadeci_ekle(telegram_id, ad, username, sahe, alt_sahe,
                    seher, min_maas, max_maas, is_rejimi,
                    tecrube, referral_kimden=None):
    """Yeni istifadəçi yarat və ya mövcudu yenilə."""
    import random, string
    ref_kodu = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    with _baglanti() as conn:
        conn.execute("""
            INSERT INTO istifadeciler
                (telegram_id, ad, username, sahe, alt_sahe, seher,
                 min_maas, max_maas, is_rejimi, tecrube,
                 referral_kodu, referral_kimden)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                ad=excluded.ad, sahe=excluded.sahe,
                alt_sahe=excluded.alt_sahe, seher=excluded.seher,
                min_maas=excluded.min_maas, max_maas=excluded.max_maas,
                is_rejimi=excluded.is_rejimi, tecrube=excluded.tecrube,
                son_aktivlik=CURRENT_TIMESTAMP
        """, (telegram_id, ad, username, sahe, alt_sahe, seher,
              min_maas, max_maas, is_rejimi, tecrube,
              ref_kodu, referral_kimden))


def istifadeci_al(telegram_id: int) -> dict | None:
    with _baglanti() as conn:
        row = conn.execute(
            "SELECT * FROM istifadeciler WHERE telegram_id=?",
            (telegram_id,)
        ).fetchone()
    return dict(row) if row else None


def butun_aktiv_istifadeciiler() -> list[dict]:
    with _baglanti() as conn:
        rows = conn.execute(
            "SELECT * FROM istifadeciler WHERE aktiv=1"
        ).fetchall()
    return [dict(r) for r in rows]


def plan_yenile(telegram_id: int, plan: str):
    """Premium/pulsuz plan yenilə. Premium üçün bitmə tarixi hesabla."""
    from datetime import timedelta
    bitis = None
    if plan == "premium":
        bitis = (date.today() + timedelta(days=30)).isoformat()

    with _baglanti() as conn:
        conn.execute(
            "UPDATE istifadeciler SET plan=?, premium_bitis=?, son_aktivlik=CURRENT_TIMESTAMP WHERE telegram_id=?",
            (plan, bitis, telegram_id)
        )


def premium_bitib_mi(telegram_id: int) -> bool:
    """Premium müddəti bitibmi yoxla — bitibsə pulsuz plana keçir."""
    p = istifadeci_al(telegram_id)
    if not p or p["plan"] != "premium":
        return False
    if p["premium_bitis"]:
        bitis = date.fromisoformat(p["premium_bitis"])
        if date.today() > bitis:
            plan_yenile(telegram_id, "pulsuz")
            return True
    return False


def sirket_izle(telegram_id: int, sirket_adi: str):
    with _baglanti() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sirket_izleme (telegram_id, sirket_adi) VALUES (?,?)",
            (telegram_id, sirket_adi)
        )


def izlenen_sirketler(telegram_id: int) -> list[str]:
    with _baglanti() as conn:
        rows = conn.execute(
            "SELECT sirket_adi FROM sirket_izleme WHERE telegram_id=?",
            (telegram_id,)
        ).fetchall()
    return [r["sirket_adi"] for r in rows]


# ══════════════════════════════════════════════════════
# ELAN ƏMƏLİYYATLARI
# ══════════════════════════════════════════════════════

def elan_saxla(elan: dict) -> bool:
    """Yeni elanı saxla. Artıq varsa False qaytarır."""
    with _baglanti() as conn:
        try:
            conn.execute("""
                INSERT INTO elanlar
                    (id, baslik, sirket, maas_min, maas_max, maas_metn,
                     yer, rejim, tecrube_il, aciklama, teleb_sozler,
                     link, menbe, kategoriya, elan_tarixi)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                elan.get("id"), elan.get("baslik"), elan.get("sirket"),
                elan.get("maas_min"), elan.get("maas_max"), elan.get("maas_metn"),
                elan.get("yer"), elan.get("rejim"), elan.get("tecrube_il"),
                elan.get("aciklama"), str(elan.get("teleb_sozler", [])),
                elan.get("link"), elan.get("menbe"), elan.get("kategoriya"),
                date.today().isoformat()
            ))
            return True
        except sqlite3.IntegrityError:
            return False  # artıq mövcuddur


def bugunun_elanları() -> list[dict]:
    with _baglanti() as conn:
        rows = conn.execute(
            "SELECT * FROM elanlar WHERE elan_tarixi=date('now') AND aktiv=1"
        ).fetchall()
    return [dict(r) for r in rows]


def elan_tapildi_mi(elan_id: str) -> bool:
    with _baglanti() as conn:
        row = conn.execute(
            "SELECT id FROM elanlar WHERE id=?", (elan_id,)
        ).fetchone()
    return row is not None


# ══════════════════════════════════════════════════════
# GÖNDƏRİLMİŞ ELANLAR
# ══════════════════════════════════════════════════════

def gonderilenler_al(telegram_id: int) -> set[str]:
    """Bu istifadəçiyə əvvəl göndərilmiş elan ID-ləri."""
    with _baglanti() as conn:
        rows = conn.execute(
            "SELECT elan_id FROM gonderilenler WHERE telegram_id=?",
            (telegram_id,)
        ).fetchall()
    return {r["elan_id"] for r in rows}


def gonderildi_qeyd_et(telegram_id: int, elan_id: str):
    with _baglanti() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO gonderilenler (telegram_id, elan_id) VALUES (?,?)",
            (telegram_id, elan_id)
        )


# ══════════════════════════════════════════════════════
# ÖDƏNİŞ ƏMƏLİYYATLARI
# ══════════════════════════════════════════════════════

def odenis_yarat(telegram_id: int, payriff_order: str, mebleg: float):
    with _baglanti() as conn:
        conn.execute(
            "INSERT INTO odenisler (telegram_id, payriff_order, mebleg) VALUES (?,?,?)",
            (telegram_id, payriff_order, mebleg)
        )


def odenis_tamamla(payriff_order: str) -> int | None:
    """Ödənişi tamamlandı olaraq qeyd et, telegram_id qaytarır."""
    with _baglanti() as conn:
        row = conn.execute(
            "SELECT telegram_id FROM odenisler WHERE payriff_order=?",
            (payriff_order,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE odenisler SET status='tamamlandi', tamamlanib=CURRENT_TIMESTAMP WHERE payriff_order=?",
            (payriff_order,)
        )
    return row["telegram_id"]


# ══════════════════════════════════════════════════════
# ANALİTİKA VƏ STATİSTİKA
# ══════════════════════════════════════════════════════

def statistika_al() -> dict:
    with _baglanti() as conn:
        cemi     = conn.execute("SELECT COUNT(*) FROM istifadeciler").fetchone()[0]
        premium  = conn.execute("SELECT COUNT(*) FROM istifadeciler WHERE plan='premium'").fetchone()[0]
        bu_gun   = conn.execute("SELECT COUNT(*) FROM istifadeciler WHERE date(qeydiyyat_tarix)=date('now')").fetchone()[0]
        bu_ay_od = conn.execute("""
            SELECT COALESCE(SUM(mebleg),0) FROM odenisler
            WHERE status='tamamlandi' AND strftime('%Y-%m',tamamlanib)=strftime('%Y-%m','now')
        """).fetchone()[0]
        elan_say = conn.execute("SELECT COUNT(*) FROM elanlar WHERE elan_tarixi=date('now')").fetchone()[0]
    return {
        "cemi":         cemi,
        "premium":      premium,
        "pulsuz":       cemi - premium,
        "bu_gun_yeni":  bu_gun,
        "bu_ay_gelir":  bu_ay_od,
        "bugun_elanlar":elan_say,
    }


def mesaj_qeyd_et(telegram_id: int, komanda: str):
    """Analitika üçün istifadəçi əməliyyatlarını qeydə al."""
    with _baglanti() as conn:
        conn.execute(
            "INSERT INTO mesaj_loq (telegram_id, komanda) VALUES (?,?)",
            (telegram_id, komanda)
        )
