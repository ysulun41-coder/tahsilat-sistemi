import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# Sayfa Genişliği ve Başlık
st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# ----------------- VERİTABANI FONKSİYONLARI -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def fix_database():
    conn = get_connection()
    cursor = conn.cursor()
    # Tabloları oluştur 
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
    # Eski veritabanı varsa TC sütununu ekle
    try:
        cursor.execute("ALTER TABLE ogrenciler ADD COLUMN tc TEXT")
    except:
        pass
    conn.commit()
    conn.close()

fix_database()

st.title("📊 Tahsilat Sistemi")

# ----------------- VERİ ÇEKME -----------------
def verileri_yukle():
    conn = get_connection()
    df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)
    # Taksitler ve Öğrenci Bilgileri Birleşik
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

# ----------------- ÖĞRENCİ + BORÇ EKLEME (SIFIRLANAN FORM) -----------------
with st.expander("👨‍🎓 Yeni Kayıt ve Borçlandırma", expanded=False):
    if "kayit_basarili" in st.session_state:
        st.success(st.session_state.kayit_basarili)
        del st.session_state.kayit_basarili

    with st.form("yeni_kayit_formu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            ogrenci = st.text_input("Öğrenci Adı")
            veli = st.text_input("Veli Adı")
            tc = st.text_input("TC Kimlik")
        with c2:
            telefon = st.text_input("Telefon")
            toplam = st.number_input("Toplam Borç", min_value=0.0, step=100.0)
            taksit = st.number_input("Taksit Sayısı", min_value=1, step=1)
        
        ilk_tarih = st.date_input("İlk Taksit Tarihi", value=date.today())
        kaydedildi = st.form_submit_button("Kaydı Tamamla ve Taksitlendir")

    if kaydedildi:
        if ogrenci and toplam > 0:
            conn = get_connection()
            cursor = conn.cursor()
            mevcut = df_ogr[df_ogr["ad"] == ogrenci]
            if not mevcut.empty:
                ogr_id = int(mevcut["id"].values[0])
            else:
                cursor.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)",
                               (ogrenci, veli, telefon, tc))
                ogr_id = cursor.lastrowid

            tutar = toplam / taksit
            for i in range(int(taksit)):
                vade = ilk_tarih + timedelta(days=30 * i)
                cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, ?)",
                               (ogr_id, vade, tutar, "Bekliyor"))
            conn.commit()
            conn.close()
            st.session_state.kayit_basarili = f"{ogrenci} başarıyla kaydedildi!"
            st.rerun()

# ----------------- TAKİP PANELİ (BUGÜN / GECİKEN) -----------------
col_bugun, col_geciken = st.columns(2)
bugun = date.today()

with col_bugun:
    st.subheader("📅 Bugünün Ödemeleri")
    if not df_plan.empty:
        bugun_df = df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")]
        # hide_index=True ile soldaki o kod gibi duran numaraları gizledik
        st.dataframe(bugun_df, use_container_width=True, hide_index=True) if not bugun_df.empty else st.info("Bugün ödeme yok.")

with col_geciken:
    st.subheader("⏰ Geciken Ödemeler")
    if not df_plan.empty:
        geciken_df = df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")]
        st.dataframe(geciken_df, use_container_width=True, hide_index=True) if not geciken_df.empty else st.success("Gec
