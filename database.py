import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

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
        telefon TEXT
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

st.title("📊 Tahsilat Sistemi")

# ----------------- ÖĞRENCİ EKLE -----------------
st.subheader("👨‍🎓 Öğrenci Ekle")

ogrenci = st.text_input("Öğrenci Adı")
veli = st.text_input("Veli Adı")
telefon = st.text_input("Telefon")

if st.button("Öğrenci Kaydet"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO ogrenciler (ad, veli, telefon) VALUES (?, ?, ?)",
        (ogrenci, veli, telefon)
    )

    conn.commit()
    conn.close()

    st.success("Öğrenci eklendi!")

# ----------------- ÖĞRENCİLERİ ÇEK -----------------
conn = get_connection()
df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)
conn.close()

if not df_ogr.empty:

    st.subheader("📅 Taksit Planı Oluştur")

    ogrenci_sec = st.selectbox("Öğrenci Seç", df_ogr["ad"])

    toplam = st.number_input("Toplam Borç", 0.0)
    taksit = st.number_input("Taksit Sayısı", 1)

    ilk_tarih = st.date_input("İlk Ödeme Tarihi")

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

        st.success("Taksit planı oluşturuldu!")

# ----------------- TAKSİTLER -----------------
st.subheader("📋 Taksit Listesi")

conn = get_connection()

df_plan = pd.read_sql("""
SELECT o.id, ogr.ad as ogrenci, o.vade, o.tutar, o.durum
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
""", conn)

conn.close()

st.dataframe(df_plan)

# ----------------- TAHSİLAT -----------------
st.subheader("💰 Tahsilat Yap")

if not df_plan.empty:

    secim = st.selectbox(
        "Taksit Seç",
        df_plan.apply(lambda x: f"{x['ogrenci']} - {x['vade']} - {x['tutar']}", axis=1)
    )

    if st.button("Ödendi Yap"):

        sec_id = df_plan.iloc[
            df_plan.apply(lambda x: f"{x['ogrenci']} - {x['vade']} - {x['tutar']}", axis=1)
            == secim
        ]["id"].values[0]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE odemeler SET durum='Ödendi' WHERE id=?",
            (sec_id,)
        )

        conn.commit()
        conn.close()

        st.success("Tahsilat alındı!")

        st.rerun()