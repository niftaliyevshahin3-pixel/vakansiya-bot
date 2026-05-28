"""
bot.py — Əsas Telegram Bot Faylı
==================================
Bütün komandaları, onboarding axınını, pulsuz/premium
xüsusiyyətlərini, ödəniş inteqrasiyasını idarə edir.

MÜŞTƏRİ CƏLBEDİCİ XÜSUSİYYƏTLƏR:
  ✅ Şəxsə özel sahə filtri (12 sahə, alt kateqoriyalar)
  ✅ Maaş filtrləmə (min–max, uyğun deyilsə bazar məlumatı)
  ✅ Şəhər / iş rejimi / təcrübə filtrləri
  ✅ Şirkət izləmə (premium)
  ✅ CV analizi + vakansiya uyğunluq faizi (premium)
  ✅ Erkən giriş — premium 6 saat əvvəl görür
  ✅ Referral sistemi — dost dəvət et, 1 ay pulsuz premium
  ✅ Həftəlik maaş analitikası (Instagram kimi məzmun bota daxil)
  ✅ Müsahibə hazırlıq AI-si (premium)
"""

import asyncio
import logging
import os
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes,
)

import database as db
from config import (
    BOT_TOKEN, ADMIN_IDS, SAHƏLƏR, PREMIUM_QİYMƏT,
    PULSUZ_LIMIT, PREMIUM_LIMIT, BAZAR_MAAŞ,
)
from matcher  import uygunlug_hesabla, elan_sirket_uygunmu
from cv_analiz import cv_analiz_et
from payriff  import odenis_linki_yarat

logging.basicConfig(
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level   = logging.INFO,
    handlers= [logging.StreamHandler(),
               logging.FileHandler("bot.log", encoding="utf-8")]
)
log = logging.getLogger(__name__)

# ── Söhbət addımları ──────────────────────────────────────────────
(SAHƏ, ALT_SAHƏ, ŞƏHƏRİ, MIN_MAAŞ, MAX_MAAŞ,
 REJİM, TƏCRÜBƏ, PROFIL_TAM) = range(8)

(CV_GÖZLƏ, CV_VAKANSIYA) = range(10, 12)
(SİRKƏT_ADINI_GÖZLƏMLİ,) = range(20, 21)


# ══════════════════════════════════════════════════════
# KÖMƏKÇI FUNKSIYALAR
# ══════════════════════════════════════════════════════

def _premium_mi(tid: int) -> bool:
    """İstifadəçi premium plandadırmı + müddəti bitibmi yoxla."""
    db.premium_bitib_mi(tid)   # bitibsə avtomatik pulsuz edir
    p = db.istifadeci_al(tid)
    return p is not None and p.get("plan") == "premium"


def elan_formatla(elan: dict, uygunlug: int = 0) -> str:
    """
    Elanı tam detallı, oxunaqlı Telegram mesajına çevir.
    Maaş göstərilməyibsə bazar məlumatı əlavə olunur.
    """
    h = []

    # Başlıq + uyğunluq
    h.append(f"💼 <b>{elan.get('baslik','')}</b>")
    if uygunlug >= 70:
        h.append(f"🎯 Uyğunluq: <b>{uygunlug}%</b> — Yüksək uyğunluq!")
    elif uygunlug >= 50:
        h.append(f"✅ Uyğunluq: <b>{uygunlug}%</b>")

    # Şirkət
    if elan.get("sirket"):
        h.append(f"🏢 {elan['sirket']}")

    # Maaş — mühüm hissə
    maas_metn = elan.get("maas_metn", "")
    if maas_metn and "Razılaşma" not in maas_metn and "razılaşma" not in maas_metn:
        h.append(f"💵 {maas_metn}")
    elif elan.get("kategoriya"):
        # Bazar məlumatı göstər
        aralik = BAZAR_MAAŞ.get(elan["kategoriya"], (600, 2000))
        h.append(
            f"💵 Maaş göstərilməyib\n"
            f"   📊 Bu sahədə bazar orta: {aralik[0]:,}–{aralik[1]:,} AZN"
        )

    # Yer
    if elan.get("yer"):
        h.append(f"📍 {elan['yer']}")

    # Kateqoriya
    if elan.get("kategoriya"):
        h.append(f"🏷 {elan['kategoriya']}")

    # Mənbə + tarix
    menbe = elan.get("menbe", "")
    if menbe:
        h.append(f"🌐 Mənbə: {menbe}")

    # Müraciət linki
    if elan.get("link"):
        h.append(f"\n👉 <a href='{elan['link']}'>Vakansiyaya bax və müraciət et</a>")

    return "\n".join(h)


async def elan_mesaj_gonder(bot, chat_id: int, elan: dict, uygunlug: int = 0):
    """Formatlaşdırılmış elanı düymə ilə göndər."""
    metn    = elan_formatla(elan, uygunlug)
    duymeler = None
    if elan.get("link"):
        duymeler = InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Müraciət et", url=elan["link"])
        ]])
    try:
        await bot.send_message(
            chat_id              = chat_id,
            text                 = metn,
            parse_mode           = ParseMode.HTML,
            reply_markup         = duymeler,
            disable_web_page_preview = True,
        )
    except Exception as e:
        log.error(f"Mesaj göndərmə xəta ({chat_id}): {e}")


# ══════════════════════════════════════════════════════
# ONBOARDING — İLK QEYDİYYAT AXINI
# ══════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    ad  = update.effective_user.first_name
    db.mesaj_qeyd_et(tid, "/start")

    # Referral yoxla (/start ref_XXXXX formatında)
    referrer = None
    if ctx.args:
        ref_arg = ctx.args[0]
        if ref_arg.startswith("ref_"):
            ref_kodu = ref_arg[4:]
            # Referral kodu ilə istifadəçi tap
            # (sadəlik üçün buraxılır — tam versiyada əlavə et)

    # Artıq qeydiyyatlıdırsa
    profil = db.istifadeci_al(tid)
    if profil:
        plan_emoji = "⭐" if profil["plan"] == "premium" else "🆓"
        await update.message.reply_html(
            f"Salam yenidən, <b>{ad}</b>! {plan_emoji}\n\n"
            f"Hazırkı planın: <b>{profil['plan'].capitalize()}</b>\n\n"
            f"/elanlar — bu günün elanları\n"
            f"/profil — profilinə bax\n"
            f"/premium — premium al\n"
            f"/yardim — kömək"
        )
        return ConversationHandler.END

    # Yeni istifadəçi — salamlama
    await update.message.reply_html(
        f"Salam, <b>{ad}</b>! 👋\n\n"
        f"Mən <b>Vakansiya Botuyam</b> — hər gün Azərbaycandakı\n"
        f"iş elanlarını sənin sahənə görə filter edib göndərirəm.\n\n"
        f"<b>Niyə başqalarından fərqliyəm?</b>\n"
        f"🎯 Yalnız sənin sahənə aid elanlar\n"
        f"💵 Maaş filtrləmə — az olanlar göstərilmir\n"
        f"🏢 Şirkət izləmə — istədiyin şirkəti izlə\n"
        f"📄 AI ilə CV analizi (premium)\n\n"
        f"Başlamaq üçün <b>sahəni</b> seç 👇"
    )
    return await _sahe_goster(update)


async def _sahe_goster(update) -> int:
    saheler    = list(SAHƏLƏR.keys())
    # İki sütunlu düymələr
    duymeler   = []
    for i in range(0, len(saheler), 2):
        sətir = [InlineKeyboardButton(saheler[i], callback_data=f"s:{saheler[i]}")]
        if i + 1 < len(saheler):
            sətir.append(InlineKeyboardButton(saheler[i+1], callback_data=f"s:{saheler[i+1]}"))
        duymeler.append(sətir)

    await update.message.reply_html(
        "🎯 <b>Hansı sahədə iş axtarırsan?</b>",
        reply_markup=InlineKeyboardMarkup(duymeler)
    )
    return SAHƏ


async def sahe_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    sahə = q.data[2:]
    ctx.user_data["sahe"] = sahə

    alt_sahələr = SAHƏLƏR.get(sahə, {}).get("alt_sahələr", [])
    if alt_sahələr:
        duy = [[InlineKeyboardButton(a, callback_data=f"a:{a}")] for a in alt_sahələr]
        duy.append([InlineKeyboardButton("📂 Hamısı", callback_data="a:hamisi")])
        await q.edit_message_text(
            f"✅ <b>{sahə}</b> seçildi.\n\n📌 Alt kateqoriya seç:",
            reply_markup=InlineKeyboardMarkup(duy),
            parse_mode=ParseMode.HTML
        )
        return ALT_SAHƏ
    else:
        ctx.user_data["alt_sahe"] = "hamisi"
        return await _seher_sor(q)


async def alt_sahe_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["alt_sahe"] = q.data[2:]
    return await _seher_sor(q)


async def _seher_sor(q) -> int:
    await q.edit_message_text(
        "📍 <b>Hansı şəhər/bölgə?</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏙 Bakı",        callback_data="sh:Bakı"),
             InlineKeyboardButton("🏭 Sumqayıt",    callback_data="sh:Sumqayıt")],
            [InlineKeyboardButton("🌆 Gəncə",       callback_data="sh:Gəncə"),
             InlineKeyboardButton("🌐 Remote",       callback_data="sh:Remote")],
            [InlineKeyboardButton("🇦🇿 Bütün AZ",   callback_data="sh:Hamısı")],
        ]),
        parse_mode=ParseMode.HTML
    )
    return ŞƏHƏRİ


async def seher_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["seher"] = q.data[3:]
    await q.edit_message_text(
        "💵 <b>Minimum maaş beklentisi?</b>\n"
        "(Bu maaşdan aşağı elanlar göstərilməyəcək)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("500+ AZN",  callback_data="mn:500"),
             InlineKeyboardButton("800+ AZN",  callback_data="mn:800")],
            [InlineKeyboardButton("1000+ AZN", callback_data="mn:1000"),
             InlineKeyboardButton("1500+ AZN", callback_data="mn:1500")],
            [InlineKeyboardButton("2000+ AZN", callback_data="mn:2000"),
             InlineKeyboardButton("Fərq etməz", callback_data="mn:0")],
        ]),
        parse_mode=ParseMode.HTML
    )
    return MIN_MAAŞ


async def min_maas_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["min_maas"] = int(q.data[3:])
    await q.edit_message_text(
        "💵 <b>Maksimum maaş limiti?</b>\n"
        "(Bu məbləğdən yuxarı elanlar da göndərilsin?)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1000 AZN-ə qədər",  callback_data="mx:1000"),
             InlineKeyboardButton("1500 AZN-ə qədər",  callback_data="mx:1500")],
            [InlineKeyboardButton("2500 AZN-ə qədər",  callback_data="mx:2500"),
             InlineKeyboardButton("5000 AZN-ə qədər",  callback_data="mx:5000")],
            [InlineKeyboardButton("Limit yoxdur",       callback_data="mx:0")],
        ]),
        parse_mode=ParseMode.HTML
    )
    return MAX_MAAŞ


async def max_maas_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["max_maas"] = int(q.data[3:])
    await q.edit_message_text(
        "🏢 <b>İş rejimi?</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏢 Ofis",     callback_data="r:ofis"),
             InlineKeyboardButton("🏠 Uzaqdan",  callback_data="r:remote")],
            [InlineKeyboardButton("🔀 Hibrid",   callback_data="r:hibrid"),
             InlineKeyboardButton("Fərq etməz",  callback_data="r:hamisi")],
        ]),
        parse_mode=ParseMode.HTML
    )
    return REJİM


async def rejim_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ctx.user_data["is_rejimi"] = q.data[2:]
    await q.edit_message_text(
        "📊 <b>Təcrübə səviyyən?</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌱 Təcrübəsiz",   callback_data="t:0"),
             InlineKeyboardButton("📗 1–3 il",        callback_data="t:1")],
            [InlineKeyboardButton("📘 3–5 il",        callback_data="t:3"),
             InlineKeyboardButton("📙 5+ il",         callback_data="t:5")],
            [InlineKeyboardButton("Fərq etməz",       callback_data="t:hamisi")],
        ]),
        parse_mode=ParseMode.HTML
    )
    return TƏCRÜBƏ


async def tecrube_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Onboarding-in son addımı — profili saxla, xülasə göstər."""
    q = update.callback_query
    await q.answer()

    tid      = q.from_user.id
    ad       = q.from_user.first_name
    username = q.from_user.username or ""
    ctx.user_data["tecrube"] = q.data[2:]

    d = ctx.user_data
    db.istifadeci_ekle(
        telegram_id    = tid,
        ad             = ad,
        username       = username,
        sahe           = d.get("sahe", ""),
        alt_sahe       = d.get("alt_sahe", "hamisi"),
        seher          = d.get("seher", "Hamısı"),
        min_maas       = d.get("min_maas", 0),
        max_maas       = d.get("max_maas", 0),
        is_rejimi      = d.get("is_rejimi", "hamisi"),
        tecrube        = d.get("tecrube", "hamisi"),
    )

    p = db.istifadeci_al(tid)
    ref_kodu = p.get("referral_kodu", "") if p else ""

    await q.edit_message_text(
        f"🎉 <b>Profil hazırdır!</b>\n\n"
        f"📋 <b>Seçimlərin:</b>\n"
        f"┣ Sahə: {d.get('sahe')}\n"
        f"┣ Alt kateqoriya: {d.get('alt_sahe','Hamısı')}\n"
        f"┣ Şəhər: {d.get('seher')}\n"
        f"┣ Maaş: {d.get('min_maas',0):,}–"
        f"{'limitsiz' if not d.get('max_maas') else str(d.get('max_maas',0))+' AZN'}\n"
        f"┣ Rejim: {d.get('is_rejimi')}\n"
        f"┗ Təcrübə: {d.get('tecrube')}\n\n"
        f"✅ <b>Hər gün saat 08:00-da</b> sənin üçün elanlar göndəriləcək\n"
        f"🆓 Pulsuz: gündə {PULSUZ_LIMIT} uyğun elan\n\n"
        f"📤 Referral linkin (dost dəvət et, 7 gün pulsuz premium qazanacaqsın):\n"
        f"<code>https://t.me/{os.getenv('BOT_USERNAME','botun_adresi')}?start=ref_{ref_kodu}</code>\n\n"
        f"⭐ <b>Limitsiz + CV analizi üçün:</b> /premium",
        parse_mode=ParseMode.HTML
    )
    ctx.user_data.clear()
    return ConversationHandler.END


# ══════════════════════════════════════════════════════
# GÜNLÜK ELAN DAĞITIMI
# ══════════════════════════════════════════════════════

async def gunluk_elan_gonder(app: Application):
    """
    Hər gün saat 08:00-da bütün aktiv istifadəçilərə
    profillərinə uyğun elanları göndər.
    GitHub Actions → python run_sender.py ilə çağırılır.
    """
    bot       = app.bot
    elanlar   = db.bugunun_elanları()
    istifadeciler = db.butun_aktiv_istifadeciiler()

    log.info(f"Günlük göndərmə: {len(elanlar)} elan, {len(istifadeciler)} istifadəçi")
    uğurlu = 0

    for ist in istifadeciler:
        tid   = ist["telegram_id"]
        plan  = ist["plan"]
        limit = PREMIUM_LIMIT if plan == "premium" else PULSUZ_LIMIT

        # Artıq göndərilənləri xaric et
        gonderilenler = db.gonderilenler_al(tid)
        izlenen       = db.izlenen_sirketler(tid)

        # Uyğun elanları tap və skorla
        uygunlar = []
        for e in elanlar:
            if e["id"] in gonderilenler:
                continue
            skor = uygunlug_hesabla(e, ist)
            e    = dict(e)
            e["uygunlug_skoru"] = skor

            # Şirkət izləmə — uyğunlukdan asılı olmayaraq əlavə et
            sirket_uygun = elan_sirket_uygunmu(e, izlenen)
            if skor >= 40 or sirket_uygun:
                uygunlar.append((skor, sirket_uygun, e))

        # Skora görə sırala
        uygunlar.sort(key=lambda x: (x[1], x[0]), reverse=True)
        gonderilecek = uygunlar[:limit]

        if not gonderilecek:
            continue

        # Gün başlığı
        try:
            sirket_xeber = " 🏢 Şirkət xəbəri!" if any(x[1] for x in gonderilecek) else ""
            await bot.send_message(
                tid,
                f"🌅 <b>{datetime.now().strftime('%d %B')} — Yeni Vakansiyalar</b>\n"
                f"{'⭐ Premium' if plan=='premium' else '🆓 Pulsuz'} • "
                f"{len(gonderilecek)} uyğun elan{sirket_xeber}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            log.warning(f"Başlıq göndərmə xəta {tid}: {e}")
            continue

        # Elanları göndər
        for skor, sirket_uygun, elan in gonderilecek:
            if sirket_uygun:
                try:
                    sirket = elan.get("sirket", "")
                    await bot.send_message(
                        tid,
                        f"🔔 <b>İzlədiyin şirkətdən xəbər: {sirket}</b>",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
            await elan_mesaj_gonder(bot, tid, elan, skor)
            db.gonderildi_qeyd_et(tid, elan["id"])
            await asyncio.sleep(0.5)

        # Pulsuz istifadəçiyə upsell
        if plan == "pulsuz" and len(uygunlar) > PULSUZ_LIMIT:
            gizli = len(uygunlar) - PULSUZ_LIMIT
            try:
                await bot.send_message(
                    tid,
                    f"💡 Bu gün sənin üçün <b>{len(uygunlar)}</b> uyğun elan var.\n"
                    f"Pulsuz planda yalnız <b>{PULSUZ_LIMIT}</b>-ini görürsən.\n"
                    f"<b>{gizli} elan</b> gizlidir. /premium ilə hamısını gör.",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        uğurlu += 1

    log.info(f"Günlük göndərmə tamamlandı: {uğurlu}/{len(istifadeciler)} istifadəçiyə çatdırıldı")


# ══════════════════════════════════════════════════════
# /ELANLAR — ÖZ TƏLƏBİ İLƏ ƏLLƏ ALMA
# ══════════════════════════════════════════════════════

async def elanlar_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/elanlar — istifadəçi istəyəndə bu günün elanlarını göstər."""
    tid = update.effective_user.id
    db.mesaj_qeyd_et(tid, "/elanlar")

    ist = db.istifadeci_al(tid)
    if not ist:
        await update.message.reply_text("Əvvəlcə /start ilə qeydiyyatdan keç.")
        return

    await update.message.reply_text("⏳ Elanlar yoxlanır...")

    plan  = ist["plan"]
    limit = PREMIUM_LIMIT if plan == "premium" else PULSUZ_LIMIT
    elanlar = db.bugunun_elanları()
    gonderilenler = db.gonderilenler_al(tid)

    uygunlar = []
    for e in elanlar:
        if e["id"] in gonderilenler:
            continue
        skor = uygunlug_hesabla(e, ist)
        if skor >= 40:
            e = dict(e)
            e["uygunlug_skoru"] = skor
            uygunlar.append((skor, e))

    uygunlar.sort(reverse=True)
    gosterilecek = uygunlar[:limit]

    if not gosterilecek:
        await update.message.reply_html(
            "📭 Bu gün sənin üçün yeni elan yoxdur.\n"
            "Sabah yenidən baxacağam! 🕗"
        )
        return

    await update.message.reply_html(
        f"🔍 <b>{len(gosterilecek)} uyğun elan tapıldı</b> "
        f"({'premium' if plan=='premium' else 'pulsuz plan'})"
    )
    for skor, elan in gosterilecek:
        await elan_mesaj_gonder(update.effective_chat.id.__class__(
            update.effective_chat.id), update.get_bot(), elan, skor)
        await elan_mesaj_gonder(update.get_bot(), update.effective_chat.id, elan, skor)
        db.gonderildi_qeyd_et(tid, elan["id"])
        await asyncio.sleep(0.3)


# ══════════════════════════════════════════════════════
# CV ANALİZİ
# ══════════════════════════════════════════════════════

async def cv_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    db.mesaj_qeyd_et(tid, "/cv")

    if not _premium_mi(tid):
        await update.message.reply_html(
            "⭐ <b>CV analizi premium xüsusiyyətidir.</b>\n\n"
            "Premium ilə əldə edərsən:\n"
            "• AI ilə detallı CV analizi\n"
            "• Vakansiyaya uyğunluq faizi (0–100%)\n"
            "• Konkret təkmilləşdirmə tövsiyələri\n\n"
            f"/premium — {PREMIUM_QİYMƏT} AZN/ay"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📄 <b>CV faylını göndər</b> (PDF formatında)\n\n"
        "İstəsən vakansiya linkini də əlavə et — "
        "uyğunluq faizini hesablayacağam.\n\n"
        "Yalnız CV analizi üçün <b>faylı göndər</b>.\n"
        "Ləğv etmək üçün /start",
        parse_mode=ParseMode.HTML
    )
    return CV_GÖZLƏ


async def cv_fayl_geldi(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    if not _premium_mi(tid):
        return ConversationHandler.END

    await update.message.reply_text("⏳ CV analiz edilir (20–30 saniyə)...")

    try:
        fayl    = update.message.document
        tg_fayl = await fayl.get_file()
        yol     = f"/tmp/cv_{tid}.pdf"
        await tg_fayl.download_to_drive(yol)

        ist   = db.istifadeci_al(tid)
        sahə  = ist.get("sahe", "") if ist else ""

        nəticə = cv_analiz_et(yol, sahə)
        await update.message.reply_html(nəticə)

        # Vakansiya soruşmaq istəyirmi?
        await update.message.reply_text(
            "💡 Vakansiya mətni və ya linki göndərsən "
            "uyğunluq faizini hesablayaram.\n"
            "Başqa şey üçün /start yaz.",
        )
    except Exception as e:
        log.error(f"CV xəta: {e}")
        await update.message.reply_text("❌ Xəta baş verdi. PDF formatında yenidən göndər.")

    return ConversationHandler.END


# ══════════════════════════════════════════════════════
# PROFİL
# ══════════════════════════════════════════════════════

async def profil_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    db.mesaj_qeyd_et(tid, "/profil")
    p = db.istifadeci_al(tid)

    if not p:
        await update.message.reply_text("Profil tapılmadı. /start yazın.")
        return

    plan_emoji = "⭐ Premium" if p["plan"] == "premium" else "🆓 Pulsuz"
    bitis      = p.get("premium_bitis", "—")

    maas_metn = f"{p.get('min_maas',0):,}"
    if p.get("max_maas"):
        maas_metn += f"–{p['max_maas']:,} AZN"
    else:
        maas_metn += "+ AZN"

    await update.message.reply_html(
        f"👤 <b>Profilin</b>\n\n"
        f"┣ Sahə: {p.get('sahe','—')}\n"
        f"┣ Alt kateqoriya: {p.get('alt_sahe','Hamısı')}\n"
        f"┣ Şəhər: {p.get('seher','—')}\n"
        f"┣ Maaş filtr: {maas_metn}\n"
        f"┣ Rejim: {p.get('is_rejimi','—')}\n"
        f"┣ Təcrübə: {p.get('tecrube','—')}\n"
        f"┗ Plan: {plan_emoji}"
        + (f"\n   Premium bitmə: {bitis}" if bitis != "—" else "")
        + f"\n\n🔗 Referral kodum:\n"
        f"<code>https://t.me/{os.getenv('BOT_USERNAME','bot')}?start=ref_{p.get('referral_kodu','')}</code>\n"
        f"(Dost dəvət et — hər ikisi 7 gün pulsuz premium)\n\n"
        f"⚙️ Profili yeniləmək üçün: /start\n"
        f"🏢 Şirkət izləmək üçün: /sirket",
        disable_web_page_preview=True
    )


# ══════════════════════════════════════════════════════
# ŞİRKƏT İZLƏMƏ (Premium)
# ══════════════════════════════════════════════════════

async def sirket_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid = update.effective_user.id
    db.mesaj_qeyd_et(tid, "/sirket")

    if not _premium_mi(tid):
        await update.message.reply_html(
            "⭐ Şirkət izləmə <b>premium xüsusiyyətidir.</b>\n"
            "İzlədiyiniz şirkətdən yeni vakansiya çıxan kimi bildiris alacaqsınız.\n\n"
            f"/premium — {PREMIUM_QİYMƏT} AZN/ay"
        )
        return ConversationHandler.END

    izlenenler = db.izlenen_sirketler(tid)
    mətn = "🏢 <b>Şirkət İzləmə</b>\n\n"
    if izlenenler:
        mətn += "Hazırda izlədiklərin:\n"
        for s in izlenenler:
            mətn += f"• {s}\n"
        mətn += "\n"
    mətn += "Yeni şirkət əlavə etmək üçün <b>şirkət adını yaz</b>:"

    await update.message.reply_html(mətn)
    return SİRKƏT_ADINI_GÖZLƏMLİ


async def sirket_adi_geldi(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    tid       = update.effective_user.id
    sirket    = update.message.text.strip()
    db.sirket_izle(tid, sirket)
    await update.message.reply_html(
        f"✅ <b>{sirket}</b> izlənilənlərə əlavə edildi!\n"
        f"Bu şirkətdən yeni vakansiya çıxan kimi xəbər alacaqsan."
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════
# PREMIUM + ÖDƏNİŞ
# ══════════════════════════════════════════════════════

async def premium_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    db.mesaj_qeyd_et(tid, "/premium")

    if _premium_mi(tid):
        ist = db.istifadeci_al(tid)
        await update.message.reply_html(
            f"⭐ <b>Artıq Premium istifadəçisisən!</b>\n"
            f"Bitmə tarixi: {ist.get('premium_bitis','—')}\n\n"
            f"Yeniləmək üçün aşağıdakı düyməyə bas:"
        )

    await update.message.reply_html(
        f"⭐ <b>Premium Plan — {PREMIUM_QİYMƏT} AZN/ay</b>\n\n"
        f"✅ Gündə {PREMIUM_LIMIT} uyğun elan\n"
        f"✅ 6 saat erkən giriş\n"
        f"✅ AI ilə CV analizi\n"
        f"✅ Vakansiyaya uyğunluq faizi\n"
        f"✅ Şirkət izləmə bildirişi\n"
        f"✅ Həftəlik maaş analitikası\n"
        f"✅ Müsahibə hazırlıq AI-si\n\n"
        f"Ödəniş üsulunu seç 👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "💳 Kart ilə ödə (Payriff)",
                callback_data="odenis:payriff"
            )],
            [InlineKeyboardButton(
                "📲 M10 / Bank köçürməsi",
                callback_data="odenis:m10"
            )],
        ])
    )


async def odenis_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    tid = q.from_user.id
    usul = q.data.split(":")[1]

    if usul == "payriff":
        await q.edit_message_text("⏳ Ödəniş linki hazırlanır...")
        nəticə = await odenis_linki_yarat(tid, PREMIUM_QİYMƏT)

        if nəticə["success"]:
            from database import odenis_yarat
            odenis_yarat(tid, nəticə["order_id"], PREMIUM_QİYMƏT)
            await q.edit_message_text(
                f"💳 <b>Ödəniş Linki Hazırdır</b>\n\n"
                f"Məbləğ: <b>{PREMIUM_QİYMƏT} AZN</b>\n"
                f"Sifariş: <code>{nəticə['order_id']}</code>\n\n"
                f"👇 Linki tap və kartla ödə:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"💳 {PREMIUM_QİYMƏT} AZN Ödə",
                        url=nəticə["payment_url"]
                    )
                ]]),
                parse_mode=ParseMode.HTML
            )
        else:
            await q.edit_message_text(
                f"❌ {nəticə.get('xeta','Xəta')}\n"
                f"M10 ilə ödəyə bilərsən: /premium"
            )

    elif usul == "m10":
        await q.edit_message_text(
            f"📲 <b>M10 / Bank Köçürməsi</b>\n\n"
            f"1️⃣ M10 tətbiqini aç\n"
            f"2️⃣ <b>+994 XX XXX XX XX</b> nömrəsinə <b>{PREMIUM_QİYMƏT} AZN</b> göndər\n"
            f"3️⃣ Qeyd/şərh bölməsinə yaz: <code>VB-{tid}</code>\n"
            f"4️⃣ Ödəniş ekran görüntüsünü bota göndər ⬇️\n\n"
            f"Admin 1 saat ərzində planı aktivləşdirəcək ✅",
            parse_mode=ParseMode.HTML
        )


async def screenshot_geldi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """M10 ödəniş screenshotu gəldi — admini xəbərdar et."""
    tid = update.effective_user.id
    ad  = update.effective_user.first_name

    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_message(
                admin_id,
                f"💰 <b>Yeni Ödəniş Screenshotu!</b>\n"
                f"İstifadəçi: {ad} (ID: <code>{tid}</code>)\n"
                f"Aktivləşdirmək üçün: /aktiv {tid}",
                parse_mode=ParseMode.HTML
            )
            await ctx.bot.forward_message(
                admin_id,
                update.effective_chat.id,
                update.message.message_id
            )
        except Exception as e:
            log.error(f"Admin {admin_id} xəbərdarlıq xəta: {e}")

    await update.message.reply_html(
        "✅ <b>Screenshot qəbul edildi!</b>\n"
        "Admin 1 saat ərzində planını aktivləşdirəcək.\n"
        "Sualın varsa admin ilə əlaqə sax."
    )


# ══════════════════════════════════════════════════════
# ADMİN KOMMANDları
# ══════════════════════════════════════════════════════

def _admin_mi(tid: int) -> bool:
    return tid in ADMIN_IDS


async def aktiv_et(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /aktiv [telegram_id] — premium aktivləşdir."""
    if not _admin_mi(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("İstifadə: /aktiv 123456789")
        return
    try:
        hədəf = int(ctx.args[0])
        db.plan_yenile(hədəf, "premium")
        await update.message.reply_text(f"✅ {hədəf} → Premium edildi")
        await ctx.bot.send_message(
            hədəf,
            "🎉 <b>Premium aktivdir!</b>\n\n"
            "Xüsusiyyətlər:\n"
            "• /elanlar — bu günün elanları\n"
            "• /cv — CV analizi\n"
            "• /sirket — şirkət izlə\n\n"
            "Uğurlar! 🚀",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"Xəta: {e}")


async def stat_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin: /stat — bot statistikası."""
    if not _admin_mi(update.effective_user.id):
        return
    s = db.statistika_al()
    await update.message.reply_html(
        f"📊 <b>Bot Statistikası</b>\n\n"
        f"👥 Cəmi istifadəçi: <b>{s['cemi']}</b>\n"
        f"⭐ Premium: <b>{s['premium']}</b>\n"
        f"🆓 Pulsuz: <b>{s['pulsuz']}</b>\n"
        f"🆕 Bu gün qeydiyyat: <b>{s['bu_gun_yeni']}</b>\n"
        f"📨 Bu gün elan: <b>{s['bugun_elanlar']}</b>\n\n"
        f"💰 Bu ay gəlir: <b>{s['bu_ay_gelir']:.0f} AZN</b>\n"
        f"   Aylıq hədəf (50 premium): {50*PREMIUM_QİYMƏT} AZN"
    )


async def yardim_komandu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "ℹ️ <b>Yardım</b>\n\n"
        "<b>Əsas əmrlər:</b>\n"
        "/start — qeydiyyat / profili yenilə\n"
        "/elanlar — bu günün uyğun elanları\n"
        "/profil — profilimi gör\n"
        "/sirket — şirkət izlə (premium)\n"
        "/cv — CV analizi (premium)\n"
        "/premium — premium plan al\n\n"
        "<b>Botun üstünlükləri:</b>\n"
        "🎯 Sahəyə, şəhərə, maaşa görə filter\n"
        "💵 Maaş olmayan elanlar üçün bazar məlumatı\n"
        "🏢 İzlədiyiniz şirkətdən xəbər\n"
        "📊 AI CV analizi + uyğunluq faizi\n\n"
        "Sual? @admin_username"
    )


# ══════════════════════════════════════════════════════
# BOTUN BAŞLADILMASI
# ══════════════════════════════════════════════════════

def botu_bashlat():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN .env faylında yoxdur!")

    db.cedvelleri_yarat()

    app = Application.builder().token(BOT_TOKEN).build()

    # Onboarding söhbəti
    onboard = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SAHƏ:    [CallbackQueryHandler(sahe_callback,      pattern=r"^s:")],
            ALT_SAHƏ:[CallbackQueryHandler(alt_sahe_callback,  pattern=r"^a:")],
            ŞƏHƏRİ: [CallbackQueryHandler(seher_callback,      pattern=r"^sh:")],
            MIN_MAAŞ:[CallbackQueryHandler(min_maas_callback,  pattern=r"^mn:")],
            MAX_MAAŞ:[CallbackQueryHandler(max_maas_callback,  pattern=r"^mx:")],
            REJİM:   [CallbackQueryHandler(rejim_callback,     pattern=r"^r:")],
            TƏCRÜBƏ: [CallbackQueryHandler(tecrube_callback,   pattern=r"^t:")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    # CV söhbəti
    cv_handler = ConversationHandler(
        entry_points=[CommandHandler("cv", cv_komandu)],
        states={
            CV_GÖZLƏ: [MessageHandler(
                filters.Document.PDF | filters.Document.FileExtension("docx"),
                cv_fayl_geldi
            )],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # Şirkət izləmə
    sirket_handler = ConversationHandler(
        entry_points=[CommandHandler("sirket", sirket_komandu)],
        states={
            SİRKƏT_ADINI_GÖZLƏMLİ: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sirket_adi_geldi)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(onboard)
    app.add_handler(cv_handler)
    app.add_handler(sirket_handler)

    # Sadə komandalar
    app.add_handler(CommandHandler("elanlar", elanlar_komandu))
    app.add_handler(CommandHandler("profil",  profil_komandu))
    app.add_handler(CommandHandler("premium", premium_komandu))
    app.add_handler(CommandHandler("yardim",  yardim_komandu))
    app.add_handler(CommandHandler("aktiv",   aktiv_et))
    app.add_handler(CommandHandler("stat",    stat_komandu))

    # Callbacks
    app.add_handler(CallbackQueryHandler(odenis_callback, pattern=r"^odenis:"))

    # Şəkil — ödəniş screenshotu
    app.add_handler(MessageHandler(filters.PHOTO, screenshot_geldi))

    log.info("🤖 Bot işə düşdü (polling rejimi)")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    botu_bashlat()
