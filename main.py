import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# ----------------- DB FONKSİYONLARI -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ogrenciler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT, veli TEXT, telefon TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS odemeler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ogrenci_id INTEGER, vade DATE, tutar REAL, durum TEXT
    )""")
    conn.commit()
    conn.close()

create_tables()

st.title("📊 Tahsilat Sistemi")

# ----------------- ÖĞRENCİ EKLE -----------------
st.subheader("👨‍🎓 Öğrenci Ekle")
col1, col2, col3 = st.columns(3)
with col1:
    ogrenci = st.text_input("Öğrenci Adı")
with col2:
    veli = st.text_input("Veli Adı")
with col3:
    telefon = st.text_input("Telefon")

if st.button("Öğrenci Kaydet"):
    if ogrenci:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ogrenciler (ad, veli, telefon) VALUES (?, ?, ?)", (ogrenci, veli, telefon))
        conn.commit()
        conn.close()
        st.success("Öğrenci eklendi!")
        st.rerun()

# Verileri Çek
conn = get_connection()
df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)
conn.close()

# ----------------- TAKSİT PLANI OLUŞTUR -----------------
if not df_ogr.empty:
    st.divider()
    st.subheader("📅 Taksit Planı Oluştur")
    
    ogrenci_sec = st.selectbox("Öğrenci Seç", df_ogr["ad"])
    c1, c2, c3 = st.columns(3)
    toplam = c1.number_input("Toplam Borç", 0.0)
    taksit = c2.number_input("Taksit Sayısı", 1, 24)
    ilk_tarih = c3.date_input("İlk Ödeme Tarihi")

    if st.button("Plan Oluştur"):
        conn = get_connection()
        cursor = conn.cursor()
        ogr_id = int(df_ogr[df_ogr["ad"] == ogrenci_sec]["id"].values[0])
        tutar = toplam / taksit
        for i in range(int(taksit)):
            vade = ilk_tarih + timedelta(days=30 * i)
            cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, ?)",
                           (ogr_id, vade, tutar, "Bekliyor"))
        conn.commit()
        conn.close()
        st.success("Taksit planı oluşturuldu!")
        st.rerun()

# ----------------- TAHSİLAT YAP -----------------
st.divider()
st.subheader("💰 Tahsilat Yap")
conn = get_connection()
df_plan = pd.read_sql("SELECT o.id, ogr.ad as ogrenci, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id WHERE o.durum = 'Bekliyor'", conn)
conn.close()

if not df_plan.empty:
    secim = st.selectbox("Ödenecek Taksiti Seç", 
                         df_plan.apply(lambda x: f"{x['ogrenci']} | Vade: {x['vade']} | Tutar: {x['tutar']}", axis=1))
    
    if st.button("Ödemeyi Onayla"):
        sec_id = df_plan.iloc[df_plan.apply(lambda x: f"{x['ogrenci']} | Vade: {x['vade']} | Tutar: {x['tutar']}", axis=1) == secim]["id"].values[0]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (int(sec_id),))
        conn.commit()
        conn.close()
        st.success("Tahsilat başarıyla kaydedildi!")
        st.rerun()
else:
    st.info("Bekleyen ödeme bulunamadı.")

# ----------------- ANALİZ VE ÖZET (Sizin Eklediğiniz Soluk Kısım) -----------------
st.divider()
st.subheader("📊 Genel Durum")
conn = get_connection()
df_ozet = pd.read_sql("""
    SELECT ogr.ad, SUM(o.tutar) as toplam_borc,
    SUM(CASE WHEN o.durum = 'Ödendi' THEN o.tutar ELSE 0 END) as odenen,
    SUM(CASE WHEN o.durum != 'Ödendi' THEN o.tutar ELSE 0 END) as kalan
    FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id GROUP BY ogr.ad
""", conn)

if not df_ozet.empty:
    st.table(df_ozet)

st.subheader("⏰ Geciken Ödemeler")
bugun_str = date.today().strftime('%Y-%m-%d')
df_geciken = pd.read_sql(f"""
    SELECT ogr.ad, o.vade, o.tutar FROM odemeler o 
    JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
    WHERE o.durum != 'Ödendi' AND o.vade < '{bugun_str}'
""", conn)
conn.close()

if not df_geciken.empty:
    st.warning("Vadesi geçmiş ödemeler var!")
    st.dataframe(df_geciken)
else:
    st.success("Gecikmiş ödeme bulunmuyor.")
