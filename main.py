import streamlit as st
import pandas as pd
import sqlite3
from datetime import timedelta, date
import urllib.parse

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

st.title("📊 Tahsilat Sistemi")

# ----------------- ÖĞRENCİ EKLE -----------------
with st.expander("👨‍🎓 Öğrenci Ekle"):

    ogrenci = st.text_input("Öğrenci Adı")
    veli = st.text_input("Veli Adı")
    telefon = st.text_input("Telefon")
    tc = st.text_input("TC Kimlik")

    if st.button("Kaydet"):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)",
            (ogrenci, veli, telefon, tc)
        )

        conn.commit()
        conn.close()

        st.success("Kaydedildi")
        st.rerun()

# ----------------- VERİLER -----------------
conn = get_connection()

df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)

df_plan = pd.read_sql("""
SELECT o.id, ogr.ad, ogr.telefon, o.vade, o.tutar, o.durum
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
""", conn)

conn.close()

# ----------------- BORÇ / TAKSİT -----------------
if not df_ogr.empty:

    st.subheader("💳 Borç / Taksit Oluştur")

    sec = st.selectbox("Öğrenci Seç", df_ogr["ad"])

    toplam = st.number_input("Toplam Borç", 0.0)
    taksit = st.number_input("Taksit Sayısı", 1)
    ilk_tarih = st.date_input("İlk Taksit Tarihi")

    if st.button("Oluştur"):

        ogr_id = df_ogr[df_ogr["ad"] == sec]["id"].values[0]
        tutar = toplam / taksit

        conn = get_connection()
        cursor = conn.cursor()

        for i in range(int(taksit)):
            vade = ilk_tarih + timedelta(days=30 * i)

            cursor.execute(
                "INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, ?)",
                (ogr_id, vade, tutar, "Bekliyor")
            )

        conn.commit()
        conn.close()

        st.success("Taksit oluşturuldu")
        st.rerun()

# ----------------- BUGÜN -----------------
st.subheader("📅 Bugün Ödemesi Olanlar")

bugun = date.today()

df_plan["vade"] = pd.to_datetime(df_plan["vade"]).dt.date

df_today = df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")]

if not df_today.empty:
    st.dataframe(df_today)
else:
    st.info("Bugün ödeme yok")

# ----------------- GECİKEN -----------------
st.subheader("⏰ Gecikenler")

df_geciken = df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")]

if not df_geciken.empty:
    st.dataframe(df_geciken)
else:
    st.info("Geciken yok")

# ----------------- ÖĞRENCİ DETAY -----------------
st.subheader("👤 Öğrenci Detay")

if not df_ogr.empty:

    sec_ogr = st.selectbox("Detay için öğrenci", df_ogr["ad"])

    df_detay = df_plan[df_plan["ad"] == sec_ogr].sort_values("vade")

    if not df_detay.empty:
        st.dataframe(df_detay)

# ----------------- TAHSİLAT -----------------
st.subheader("💰 Tahsilat")

if not df_plan.empty:

    secim = st.selectbox(
        "Taksit Seç",
        df_plan.apply(lambda x: f"{x['ad']} | {x['vade']} | {x['tutar']}", axis=1)
    )

    if st.button("Ödendi Yap"):

        sec_id = df_plan.iloc[
            df_plan.apply(lambda x: f"{x['ad']} | {x['vade']} | {x['tutar']}", axis=1)
            == secim
        ]["id"].values[0]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (sec_id,))
        conn.commit()
        conn.close()

        st.success("Ödeme alındı")
        st.rerun()

# ----------------- ARŞİV -----------------
st.subheader("📁 Arşiv (Ödenenler)")

df_odenen = df_plan[df_plan["durum"] == "Ödendi"]

if not df_odenen.empty:
    st.dataframe(df_odenen)
else:
    st.info("Henüz ödeme yok")
