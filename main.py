import streamlit as st
import pandas as pd
import sqlite3
from datetime import timedelta, date

st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# ----------------- DB -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def fix_database():
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

    try:
        cursor.execute("ALTER TABLE ogrenciler ADD COLUMN tc TEXT")
    except:
        pass

    conn.commit()
    conn.close()

fix_database()

st.title("📊 Tahsilat Sistemi")

# ----------------- VERİLER -----------------
conn = get_connection()
df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)

df_plan = pd.read_sql("""
SELECT o.id, ogr.ad, ogr.telefon, ogr.tc, o.vade, o.tutar, o.durum
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
""", conn)

conn.close()

# ----------------- ÖĞRENCİ + BORÇ -----------------
with st.expander("👨‍🎓 Öğrenci + Borç Ekle", expanded=True):

    ogrenci = st.text_input("Öğrenci Adı")
    veli = st.text_input("Veli Adı")
    telefon = st.text_input("Telefon")
    tc = st.text_input("TC Kimlik")

    toplam = st.number_input("Toplam Borç", 0.0)
    taksit = st.number_input("Taksit Sayısı", 1)
    ilk_tarih = st.date_input("İlk Taksit Tarihi")

    if st.button("Kaydet"):

        conn = get_connection()
        cursor = conn.cursor()

        # aynı öğrenci var mı?
        mevcut = df_ogr[df_ogr["ad"] == ogrenci]

        if not mevcut.empty:
            ogr_id = mevcut["id"].values[0]
        else:
            cursor.execute(
                "INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)",
                (ogrenci, veli, telefon, tc)
            )
            ogr_id = cursor.lastrowid

        # taksit oluştur
        if toplam > 0:
            tutar = toplam / taksit

            for i in range(int(taksit)):
                vade = ilk_tarih + timedelta(days=30 * i)

                cursor.execute(
                    "INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, ?)",
                    (ogr_id, vade, tutar, "Bekliyor")
                )

        conn.commit()
        conn.close()

        st.success("Kayıt tamam")
        st.rerun()

# ----------------- BUGÜN -----------------
st.subheader("📅 Bugün")

if not df_plan.empty:
    df_plan["vade"] = pd.to_datetime(df_plan["vade"]).dt.date
    bugun = date.today()

    st.dataframe(df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")])

# ----------------- GECİKEN -----------------
st.subheader("⏰ Gecikenler")

if not df_plan.empty:
    bugun = date.today()
    st.dataframe(df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")])

# ----------------- TÜM TAKSİTLER -----------------
st.subheader("📋 Tüm Taksitler")

if not df_plan.empty:
    st.dataframe(df_plan)

# ----------------- TAHSİLAT -----------------
st.subheader("💰 Tahsilat")

if not df_plan.empty:

    sec_id = st.selectbox("Taksit Seç", df_plan["id"])

    sec_satir = df_plan[df_plan["id"] == sec_id]

    st.write(sec_satir)

    if st.button("Ödendi"):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (sec_id,))
        conn.commit()
        conn.close()

        st.success("Ödeme alındı")
        st.rerun()

# ----------------- ARŞİV -----------------
st.subheader("📁 Arşiv")

if not df_plan.empty:
    st.dataframe(df_plan[df_plan["durum"] == "Ödendi"])
