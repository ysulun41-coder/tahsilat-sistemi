import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# Sayfa Ayarları
st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# --- YARDIMCI FONKSİYON: Türkçe Karakter ve Büyük Harf Dönüştürücü ---
def tr_upper(text):
    if text is None: return ""
    text = str(text)
    duzeltme = {"i": "İ", "ı": "I", "ğ": "Ğ", "Ğ": "Ğ", "ü": "Ü", "Ü": "Ü", "ş": "Ş", "Ş": "Ş", "ö": "Ö", "Ö": "Ö", "ç": "Ç", "Ç": "Ç"}
    for k, v in duzeltme.items():
        text = text.replace(k, v)
    return text.upper()

# ----------------- VERİTABANI İŞLEMLERİ -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def fix_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ogrenciler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT, veli TEXT, telefon TEXT, tc TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS odemeler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ogrenci_id INTEGER, vade DATE, tutar REAL, durum TEXT
    )""")
    try:
        cursor.execute("ALTER TABLE ogrenciler ADD COLUMN tc TEXT")
    except:
        pass
    conn.commit()
    conn.close()

fix_database()

# ----------------- VERİ YÜKLEME -----------------
def verileri_yukle():
    conn = get_connection()
    df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)
    df_plan = pd.read_sql("""
        SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, ogr.telefon, ogr.tc, o.vade, o.tutar, o.durum
        FROM odemeler o
        JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
    """, conn)
    if not df_plan.empty:
        df_plan["vade"] = pd.to_datetime(df_plan["vade"]).dt.date
    conn.close()
    return df_ogr, df_plan

df_ogr, df_plan = verileri_yukle()

st.title("📊 Tahsilat Sistemi")

# ----------------- YENİ KAYIT BÖLÜMÜ -----------------
with st.expander("👨‍🎓 Yeni Öğrenci ve Borç Kaydı", expanded=False):
    if "basari_notu" in st.session_state:
        st.success(st.session_state.basari_notu)
        del st.session_state.basari_notu

    with st.form("kayit_formu", clear_on_submit=True):
        f1, f2 = st.columns(2)
        with f1:
            y_ad = st.text_input("Öğrenci Adı Soyadı")
            y_veli = st.text_input("Veli Adı")
            y_tc = st.text_input("TC Kimlik")
        with f2:
            y_tel = st.text_input("Telefon")
            y_borc = st.number_input("Toplam Borç", min_value=0.0, step=100.0)
            y_taksit = st.number_input("Taksit Sayısı", min_value=1, step=1)
        
        y_tarih = st.date_input("İlk Taksit Tarihi", value=date.today())
        submit = st.form_submit_button("Kaydet ve Borçlandır")

    if submit:
        if y_ad and y_borc > 0:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Öğrenci ekle veya var olanı al
            mevcut = df_ogr[df_ogr["ad"] == y_ad]
            if not mevcut.empty:
                ogr_id = int(mevcut["id"].values[0])
            else:
                cursor.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)", (y_ad, y_veli, y_tel, y_tc))
                ogr_id = cursor.lastrowid

            # Taksitleri dağıt
            t_tutar = y_borc / y_taksit
            for i in range(int(y_taksit)):
                vade = y_tarih + timedelta(days=30 * i)
                cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')", (ogr_id, vade, t_tutar))
            
            conn.commit()
            conn.close()
            st.session_state.basari_notu = f"{y_ad} başarıyla kaydedildi."
            st.rerun()

# ----------------- TAKİP PANELİ (BUGÜN / GECİKEN) -----------------
p1, p2 = st.columns(2)
bugun = date.today()

with p1:
    st.subheader("📅 Bugün")
    if not df_plan.empty:
        b_liste = df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")]
        if not b_liste.empty:
            st.dataframe(b_liste, use_container_width=True, hide_index=True)
        else:
            st.info("Bugün için ödeme yok.")

with p2:
    st.subheader("⏰ Gecikenler")
    if not df_plan.empty:
        g_liste = df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")]
        if not g_liste.empty:
            st.warning(f"{len(g_liste)} gecikmiş ödeme!")
            st.dataframe(g_liste, use_container_width=True, hide_index=True)
        else:
            st.success("Gecikmiş ödeme bulunmuyor.")

# ----------------- TAHSİLAT VE AKILLI ARAMA -----------------
st.divider()
st.subheader("💰 Tahsilat Girişi")

arama = st.text_input("Arama (İsim veya Öğrenci ID yazın)", placeholder="Örn: Oğuzhan")

if not df_plan.empty:
    # Arama Filtreleme (Bekleyenler üzerinden)
    df_islem = df_plan[df_plan["durum"] != "Ödendi"].copy()
    
    if arama:
        arama_u = tr_upper(arama)
        df_islem = df_islem[
            df_islem["ad"].apply(tr_upper).str.contains(arama_u, regex=False) |
            (df_islem["ogr_id"].astype(str) == arama)
        ]

    if not df_islem.empty:
        df_islem["secim_etiketi"] = df_islem.apply(lambda x: f"{x['ad']} | Vade: {x['vade']} | Tutar: {x['tutar']} TL (İşlem No: {x['islem_no']})", axis=1)
        liste = ["--- Seçim Yapınız ---"] + df_islem["secim_etiketi"].tolist()
        secim = st.selectbox("Ödeme yapacak taksiti seçin:", liste)

        if secim != "--- Seçim Yapınız ---":
            islem_id = int(secim.split("(İşlem No: ")[1].replace(")", ""))
            satir = df_islem[df_islem["islem_no"] == islem_id].iloc[0]
            
            # Hesap Özeti Panosu
            kisi_ozet = df_plan[df_plan["ogr_id"] == satir["ogr_id"]]
            t_plan = kisi_ozet["tutar"].sum()
            t_oden = kisi_ozet[kisi_ozet["durum"] == "Ödendi"]["tutar"].sum()
            t_kalan = t_plan - t_oden

            st.markdown(f"### 👤 {satir['ad']} Hesap Bilgisi")
            m1, m2, m3 = st.columns(3)
            m1.metric("Toplam Borç", f"{t_plan:,.2f} TL")
            m2.metric("Toplam Ödenen", f"{t_oden:,.2f} TL")
            m3.metric("Kalan Borç", f"{t_kalan:,.2f} TL")

            st.write(f"**Seçilen Taksit:** {satir['vade']} tarihli {satir['tutar']} TL'lik ödeme.")
            
            tutar_giris = st.number_input("Kasaya Giren Miktar (TL)", min_value=0.0, value=float(satir["tutar"]), step=10.0)

            if st.button("Ödemeyi Onayla"):
                conn = get_connection()
                cursor = conn.cursor()
                asıl_tutar = float(satir["tutar"])

                if tutar_giris < asıl_tutar:
                    # Eksik ödeme
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (tutar_giris, islem_id))
                    fark = asıl_tutar - tutar_giris
                    cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')", (satir["ogr_id"], satir["vade"], fark))
                    st.toast("Eksik ödeme alındı, kalan borç yeni taksit olarak eklendi.")
                else:
                    # Tam veya Fazla ödeme
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (tutar_giris, islem_id))
                    st.toast("Tahsilat başarıyla yapıldı.")

                conn.commit()
                conn.close()
                st.rerun()
    else:
        st.info("Aramanıza uygun bekleyen ödeme bulunamadı.")

# ----------------- ARŞİV VE TÜM LİSTE -----------------
st.divider()
tab_tum, tab_arsiv = st.tabs(["📋 Tüm Kayıtlar", "📁 Ödenmiş Arşiv"])

with tab_tum:
    if not df_plan.empty:
        st.dataframe(df_plan.sort_values(by="vade"), use_container_width=True, hide_index=True)

with tab_arsiv:
    if not df_plan.empty:
        df_arsiv = df_plan[df_plan["durum"] == "Ödendi"]
        if not df_arsiv.empty:
            st.dataframe(df_arsiv, use_container_width=True, hide_index=True)
        else:
            st.info("Henüz ödenmiş bir kayıt bulunmuyor.")
