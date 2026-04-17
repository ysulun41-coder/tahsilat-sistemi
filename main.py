import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime, date
import calendar
import time

st.set_page_config(page_title="Okul Tahsilat Sistemi", layout="wide")

# ----------------- DB -----------------
def get_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ogrenciler (
            id SERIAL PRIMARY KEY,
            ad TEXT NOT NULL,
            veli TEXT,
            telefon TEXT,
            tc TEXT UNIQUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS odemeler (
            id SERIAL PRIMARY KEY,
            ogrenci_id INTEGER REFERENCES ogrenciler(id),
            vade DATE NOT NULL,
            tutar DECIMAL(10,2) NOT NULL,
            odenen_tutar DECIMAL(10,2) DEFAULT 0,
            durum TEXT DEFAULT 'Bekliyor',
            odeme_yontemi TEXT,
            makbuz_no TEXT
        )
    """)
    conn.commit()
    cur.close()

init_db()

# ----------------- HELPERS -----------------
def ay_ekle(baslangic_tarihi, ay_sayisi):
    ay = baslangic_tarihi.month - 1 + ay_sayisi
    yil = baslangic_tarihi.year + ay // 12
    ay = ay % 12 + 1
    gun = min(baslangic_tarihi.day, calendar.monthrange(yil, ay)[1])
    return date(yil, ay, gun)


def veri_getir(query, params=None):
    conn = get_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    except:
        return pd.DataFrame()

# ----------------- UI -----------------
st.title("🏫 Tahsilat Sistemi (Geliştirilmiş)")

# ----------------- DASHBOARD -----------------
ozet = veri_getir("SELECT tutar, odenen_tutar FROM odemeler")
if not ozet.empty:
    toplam = ozet['tutar'].sum()
    odenen = ozet['odenen_tutar'].sum()
    kalan = toplam - odenen

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam", f"₺ {toplam:,.2f}")
    c2.metric("Tahsil Edilen", f"₺ {odenen:,.2f}")
    c3.metric("Kalan", f"₺ {kalan:,.2f}")

st.divider()

# ----------------- YENİ KAYIT -----------------
with st.expander("Yeni Öğrenci"):
    ad = st.text_input("Ad")
    tc = st.text_input("TC")
    toplam = st.number_input("Toplam", min_value=0.0)
    taksit = st.number_input("Taksit", min_value=1, value=5)
    tarih = st.date_input("Başlangıç", value=date.today())

    if st.button("Kaydet"):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO ogrenciler (ad, tc) VALUES (%s,%s) RETURNING id", (ad, tc))
        ogr_id = cur.fetchone()[0]

        taksit_tutar = toplam / taksit
        for i in range(int(taksit)):
            cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s,%s,%s)",
                        (ogr_id, ay_ekle(tarih, i), taksit_tutar))
        conn.commit()
        cur.close()
        st.success("Kaydedildi")
        st.rerun()

# ----------------- ÖĞRENCİ SEÇ -----------------
ogrenciler = veri_getir("SELECT id, ad FROM ogrenciler ORDER BY ad LIMIT 500")

if not ogrenciler.empty:
    secim = st.selectbox("Öğrenci", ogrenciler['ad'])
    ogr_id = ogrenciler[ogrenciler['ad'] == secim]['id'].values[0]

    df = veri_getir("SELECT * FROM odemeler WHERE ogrenci_id=%s ORDER BY vade", (ogr_id,))

    df['kalan'] = df['tutar'] - df['odenen_tutar']

    st.dataframe(df)

    bekleyen = df[df['kalan'] > 0]

    if not bekleyen.empty:
        sec = st.selectbox("Ödeme Seç", bekleyen['id'])
        sec_row = bekleyen[bekleyen['id'] == sec].iloc[0]

        odeme = st.number_input("Ödeme", min_value=0.0, max_value=float(sec_row['kalan']))
        yontem = st.selectbox("Yöntem", ["Nakit", "Kart", "Havale"])

        if st.button("Tahsilat Yap"):
            conn = get_connection()
            cur = conn.cursor()

            yeni_odenen = float(sec_row['odenen_tutar']) + odeme
            durum = "Ödendi" if yeni_odenen >= float(sec_row['tutar']) else "Bekliyor"

            makbuz = f"MKBZ-{datetime.now().strftime('%Y%m%d%H%M%S')}-{sec}"

            cur.execute("""
                UPDATE odemeler
                SET odenen_tutar=%s, durum=%s, odeme_yontemi=%s, makbuz_no=%s
                WHERE id=%s
            """, (yeni_odenen, durum, yontem, makbuz, sec))

            conn.commit()
            cur.close()
            st.success("Tahsil edildi")
            st.rerun()

# ----------------- GÜNLÜK TAKİP -----------------
st.divider()

today = date.today()

takip = veri_getir("""
SELECT o.vade, o.tutar - o.odenen_tutar AS kalan, ogr.ad
FROM odemeler o
JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
WHERE o.vade <= %s AND o.tutar > o.odenen_tutar
""", (today,))

if not takip.empty:
    st.dataframe(takip)
else:
    st.success("Geciken yok")
