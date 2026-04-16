import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# Sayfa Ayarları
st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# ----------------- VERİTABANI FONKSİYONLARI -----------------
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

# --- PARA BİRİMİ VE TARİH GÖRÜNÜM AYARLARI ---
sutun_ayarlar = {
    "tutar": st.column_config.NumberColumn("Tutar", format="₺ %.2f"),
    "vade": st.column_config.DateColumn("Vade Tarihi", format="DD.MM.YYYY")
}

st.title("📊 Tahsilat Sistemi")

# ----------------- YENİ ÖĞRENCİ KAYIT -----------------
with st.expander("👨‍🎓 Yeni Kayıt ve Borçlandırma", expanded=False):
    with st.form("kayit_formu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            y_ad = st.text_input("Öğrenci Adı Soyadı")
            y_veli = st.text_input("Veli Adı")
            y_tc = st.text_input("TC Kimlik")
        with c2:
            y_tel = st.text_input("Telefon")
            y_borc = st.number_input("Toplam Borç (TL)", min_value=0.0, step=100.0, format="%.2f")
            y_taksit = st.number_input("Taksit Sayısı", min_value=1, step=1)
        
        y_tarih = st.date_input("İlk Taksit Tarihi", value=date.today())
        submit = st.form_submit_button("Kaydı Tamamla")

    if submit and y_ad and y_borc > 0:
        conn = get_connection()
        cursor = conn.cursor()
        mevcut = df_ogr[df_ogr["ad"] == y_ad]
        if not mevcut.empty:
            ogr_id = int(mevcut["id"].values[0])
        else:
            cursor.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)", (y_ad, y_veli, y_tel, y_tc))
            ogr_id = cursor.lastrowid
        
        taksit_tutari = y_borc / y_taksit
        for i in range(int(y_taksit)):
            vade = y_tarih + timedelta(days=30 * i)
            cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')", (ogr_id, vade, taksit_tutari))
        
        conn.commit()
        conn.close()
        st.success(f"{y_ad} başarıyla kaydedildi.")
        st.rerun()

# ----------------- GÜNLÜK VE GECİKEN TAKİP -----------------
p1, p2 = st.columns(2)
bugun = date.today()

with p1:
    st.subheader("📅 Bugünün Ödemeleri")
    if not df_plan.empty:
        b_liste = df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")]
        # KISA DEVREYİ ÇÖZEN AÇIK YAZIM ŞEKLİ:
        if not b_liste.empty:
            st.dataframe(b_liste, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
        else:
            st.info("Bugün için ödeme yok.")

with p2:
    st.subheader("⏰ Geciken Ödemeler")
    if not df_plan.empty:
        g_liste = df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")]
        # KISA DEVREYİ ÇÖZEN AÇIK YAZIM ŞEKLİ:
        if not g_liste.empty:
            st.dataframe(g_liste, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
        else:
            st.success("Gecikmiş ödeme bulunmuyor.")

# ----------------- TAHSİLAT GİRİŞİ -----------------
st.divider()
st.subheader("💰 Tahsilat Girişi")

if "arama_sayaci" not in st.session_state:
    st.session_state.arama_sayaci = 0

arama = st.text_input(
    "🔍 Öğrenci Ara (İsim veya Sabit Öğrenci ID giriniz)", 
    key=f"arama_kutusu_{st.session_state.arama_sayaci}", 
    placeholder="Örn: Oğuzhan veya 41"
)

if not df_plan.empty:
    df_bekliyor = df_plan[df_plan["durum"] != "Ödendi"].copy()
    
    if arama:
        aranan = arama.strip().lower()
        df_islem = df_bekliyor[
            df_bekliyor["ad"].str.lower().str.contains(aranan, na=False, regex=False) |
            (df_bekliyor["ogr_id"].astype(str) == aranan)
        ]
    else:
        df_islem = df_bekliyor

    if not df_islem.empty:
        df_islem["etiket"] = df_islem.apply(lambda x: f"Öğr ID: {x['ogr_id']} | {x['ad']} | Vade: {x['vade']} | {x['tutar']:,.2f} TL (İşlem No: {x['islem_no']})", axis=1)
        secenekler = ["--- Lütfen Seçim Yapınız ---"] + df_islem["etiket"].tolist()
        secim = st.selectbox("Tahsil edilecek taksiti seçin:", secenekler)

        if secim != "--- Lütfen Seçim Yapınız ---":
            islem_id = int(secim.split("(İşlem No: ")[1].replace(")", ""))
            secilen_satir = df_islem[df_islem["islem_no"] == islem_id].iloc[0]
            secilen_ogr_id = int(secilen_satir["ogr_id"])

            kisi_tum_kayitlar = df_plan[df_plan["ogr_id"] == secilen_ogr_id]
            t_planlanan = kisi_tum_kayitlar["tutar"].sum()
            t_odenen = kisi_tum_kayitlar[kisi_tum_kayitlar["durum"] == "Ödendi"]["tutar"].sum()
            t_kalan = t_planlanan - t_odenen

            st.markdown(f"### 👤 {secilen_satir['ad']} - Finansal Durum")
            m1, m2, m3 = st.columns(3)
            m1.metric("Toplam Borç", f"₺ {t_planlanan:,.2f}")
            m2.metric("Toplam Tahsil Edilen", f"₺ {t_odenen:,.2f}")
            m3.metric("Kalan Net Borç", f"₺ {t_kalan:,.2f}")

            st.info(f"**Seçili Taksit Vadesi:** {secilen_satir['vade']} | **Asıl Tutar:** ₺ {secilen_satir['tutar']:,.2f}")
            
            tutar_giris = st.number_input("Kasaya Girecek Miktar (TL)", min_value=0.0, value=float(secilen_satir["tutar"]), step=50.0, format="%.2f")

            if st.button("Ödemeyi Onayla ve Kasaya İşle"):
                conn = get_connection()
                cursor = conn.cursor()
                asil = float(secilen_satir["tutar"])

                if tutar_giris < asil:
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (tutar_giris, islem_id))
                    cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')", (secilen_ogr_id, secilen_satir["vade"], asil - tutar_giris))
                    st.session_state.islem_mesaji = "Eksik tahsilat alındı, kalan tutar yeni taksit olarak eklendi."
                else:
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (tutar_giris, islem_id))
                    st.session_state.islem_mesaji = "Tahsilat başarıyla kaydedildi."
                
                conn.commit()
                conn.close()
                
                st.session_state.arama_sayaci += 1 
                st.rerun()
    else:
        st.info("Aramanıza uygun bekleyen taksit bulunamadı.")

if "islem_mesaji" in st.session_state:
    st.success(st.session_state.islem_mesaji)
    del st.session_state.islem_mesaji

# ----------------- ARŞİV VE TÜM LİSTE -----------------
st.divider()
t1, t2 = st.tabs(["📋 Tüm Taksit Hareketleri", "📁 Ödenmiş Arşivi"])

with t1:
    if not df_plan.empty:
        st.dataframe(df_plan.sort_values(by="vade"), use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

with t2:
    if not df_plan.empty:
        arsiv = df_plan[df_plan["durum"] == "Ödendi"]
        # KISA DEVREYİ ÇÖZEN AÇIK YAZIM ŞEKLİ:
        if not arsiv.empty:
            st.dataframe(arsiv, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
        else:
            st.write("Henüz ödeme kaydı yok.")
