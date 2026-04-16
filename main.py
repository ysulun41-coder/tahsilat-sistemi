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
        odenen REAL DEFAULT 0,
        durum TEXT
    )
    """)

    # kolon ekleme (varsa hata vermez)
    try:
        cursor.execute("ALTER TABLE odemeler ADD COLUMN odenen REAL DEFAULT 0")
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
SELECT o.id, ogr.ad, o.vade, o.tutar, o.odenen, o.durum
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
""", conn)

conn.close()

# ----------------- ÖĞRENCİ + BORÇ -----------------
with st.expander("👨‍🎓 Öğrenci + Borç Ekle", expanded=True):

    ogrenci = st.text_input("Öğrenci Adı")
    veli = st.text_input("Veli")
    telefon = st.text_input("Telefon")
    tc = st.text_input("TC")

    toplam = st.number_input("Toplam Borç", 0.0)
    taksit = st.number_input("Taksit", 1)
    ilk_tarih = st.date_input("İlk Tarih")

    if st.button("Kaydet"):

        conn = get_connection()
        cursor = conn.cursor()

        mevcut = df_ogr[df_ogr["ad"] == ogrenci]

        if not mevcut.empty:
            ogr_id = mevcut["id"].values[0]
        else:
            cursor.execute(
                "INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)",
                (ogrenci, veli, telefon, tc)
            )
            ogr_id = cursor.lastrowid

        if toplam > 0:
            tutar = toplam / taksit

            for i in range(int(taksit)):
                vade = ilk_tarih + timedelta(days=30 * i)

                cursor.execute(
                    "INSERT INTO odemeler (ogrenci_id, vade, tutar, odenen, durum) VALUES (?, ?, ?, ?, ?)",
                    (ogr_id, vade, tutar, 0, "Bekliyor")
                )

        conn.commit()
        conn.close()

        st.success("Kayıt tamam")
        st.rerun()

# ----------------- TAKSİTLER -----------------
st.subheader("📋 Taksitler")

if not df_plan.empty:
    df_plan["kalan"] = df_plan["tutar"] - df_plan["odenen"]
    st.dataframe(df_plan)

# ----------------- TAHSİLAT -----------------
st.subheader("💰 Tahsilat (Kısmi Ödeme)")

if not df_plan.empty:

    sec_id = st.selectbox("Taksit Seç", df_plan["id"])

    sec = df_plan[df_plan["id"] == sec_id]

    if not sec.empty:

        tutar = float(sec["tutar"].values[0])
        odenen = float(sec["odenen"].values[0])
        kalan = tutar - odenen

        st.write(f"Toplam: {tutar} ₺")
        st.write(f"Ödenen: {odenen} ₺")
        st.write(f"Kalan: {kalan} ₺")

        odeme = st.number_input("Ödeme Gir", 0.0)

        if st.button("Ödeme Yap"):

            yeni_odenen = odenen + odeme

            if yeni_odenen >= tutar:
                durum = "Ödendi"
                yeni_odenen = tutar
            else:
                durum = "Bekliyor"

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
            UPDATE odemeler 
            SET odenen=?, durum=? 
            WHERE id=?
            """, (yeni_odenen, durum, sec_id))

            conn.commit()
            conn.close()

            st.success("Ödeme kaydedildi")
            st.rerun()

# ----------------- ARŞİV -----------------
st.subheader("📁 Arşiv")

if not df_plan.empty:
    st.dataframe(df_plan[df_plan["durum"] == "Ödendi"])
