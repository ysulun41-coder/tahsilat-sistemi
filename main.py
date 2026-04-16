import os

if os.path.exists("data.db"):
    os.remove("data.db"
              
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date
import urllib.parse
)

st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# ----------------- DB -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ogrenciler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT,
        veli TEXT,
        telefon TEXT,
        tc TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS odemeler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ogrenci_id INTEGER,
        vade DATE,
        tutar REAL,
        durum TEXT
    )
    """)

    conn.commit()
    conn.close()

create_tables()

st.title("📊 Tahsilat Yönetim Paneli")

# ----------------- ÖĞRENCİ EKLE -----------------
with st.expander("👨‍🎓 Öğrenci Ekle", expanded=True):

    col1, col2 = st.columns(2)

    with col1:
        ogrenci = st.text_input("Öğrenci Adı")
        veli = st.text_input("Veli Adı")

    with col2:
        telefon = st.text_input("Telefon (5XXXXXXXXX)")
        tc = st.text_input("TC Kimlik No")

    if st.button("Kaydet"):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)",
            (ogrenci, veli, telefon, tc)
        )

        conn.commit()
        conn.close()

        st.success("Öğrenci eklendi!")

# ----------------- VERİLER -----------------
conn = get_connection()
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE ogrenciler ADD COLUMN tc TEXT")
except:
    pass

conn.commit()
conn.close()

# ----------------- PLAN -----------------
if not df_ogr.empty:

    with st.expander("📅 Taksit Planı Oluştur"):

        ogrenci_sec = st.selectbox("Öğrenci", df_ogr["ad"])

        col1, col2, col3 = st.columns(3)

        with col1:
            toplam = st.number_input("Toplam Borç", 0.0)

        with col2:
            taksit = st.number_input("Taksit", 1)

        with col3:
            ilk_tarih = st.date_input("İlk Tarih")

        if st.button("Plan Oluştur"):

            conn = get_connection()
            cursor = conn.cursor()

            ogr_id = df_ogr[df_ogr["ad"] == ogrenci_sec]["id"].values[0]
            tutar = toplam / taksit

            for i in range(int(taksit)):
                vade = ilk_tarih + timedelta(days=30 * i)

                cursor.execute(
                    "INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, ?)",
                    (ogr_id, vade, tutar, "Bekliyor")
                )

            conn.commit()
            conn.close()

            st.success("Plan oluşturuldu!")

# ----------------- TABLO -----------------
st.subheader("📋 Taksitler")

if not df_plan.empty:
    st.dataframe(df_plan)
else:
    st.info("Veri yok")

# ----------------- TAHSİLAT -----------------
st.subheader("💰 Tahsilat")

if not df_plan.empty:

    secim = st.selectbox(
        "Seç",
        df_plan.apply(lambda x: f"{x['ogrenci']} | {x['vade']} | {x['tutar']}", axis=1)
    )

    if st.button("Ödendi Yap"):

        sec_id = df_plan.iloc[
            df_plan.apply(lambda x: f"{x['ogrenci']} | {x['vade']} | {x['tutar']}", axis=1)
            == secim
        ]["id"].values[0]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (sec_id,))

        conn.commit()
        conn.close()

        st.success("Tahsilat alındı!")
        st.rerun()

# ----------------- ÖZET -----------------
st.subheader("📊 Genel Durum")

conn = get_connection()

df_ozet = pd.read_sql("""
SELECT 
    ogr.ad,
    SUM(o.tutar) as toplam,
    SUM(CASE WHEN o.durum = 'Ödendi' THEN o.tutar ELSE 0 END) as odenen,
    SUM(CASE WHEN o.durum != 'Ödendi' THEN o.tutar ELSE 0 END) as kalan
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
GROUP BY ogr.ad
""", conn)

conn.close()

if not df_ozet.empty:
    for _, row in df_ozet.iterrows():
        st.metric(row["ad"], f"Kalan: {row['kalan']} ₺", f"Ödenen: {row['odenen']} ₺")
else:
    st.info("Veri yok")

# ----------------- GECİKEN -----------------
st.subheader("⏰ Gecikenler")

conn = get_connection()

df_geciken = pd.read_sql("""
SELECT ogr.ad, ogr.telefon, o.vade, o.tutar
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
WHERE o.durum != 'Ödendi'
""", conn)

conn.close()

if not df_geciken.empty:

    df_geciken["vade"] = pd.to_datetime(df_geciken["vade"]).dt.date
    bugun = date.today()

    df_geciken = df_geciken[df_geciken["vade"] < bugun]

    for _, row in df_geciken.iterrows():

        mesaj = f"Sayın veli, {row['ad']} için {row['tutar']} TL ödemeniz gecikmiştir."
        url = "https://wa.me/90" + str(row["telefon"]) + "?text=" + urllib.parse.quote(mesaj)

        col1, col2, col3 = st.columns([2,1,1])

        with col1:
            st.write(f"{row['ad']} - {row['tutar']} ₺ - {row['vade']}")

        with col2:
            st.link_button("WhatsApp", url)

else:
    st.info("Geciken yok")
