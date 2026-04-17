import streamlit as st  # UI framework (buton, input vs.)
import pandas as pd  # tablo işlemleri
import psycopg2  # PostgreSQL bağlantısı
from datetime import datetime, date  # tarih işlemleri
import calendar  # ay/gün hesaplama
import time  # bekletme işlemleri

# ----------------- SAYFA AYARI -----------------
st.set_page_config(page_title="Okul Tahsilat Sistemi", layout="wide")

# ----------------- ŞİFRE KONTROL -----------------
def check_password():
    def password_entered():
        # Kullanıcının girdiği şifre doğru mu kontrol edilir
        if st.session_state["password"] == "1234":  # ← burayı değiştirebilirsin
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # güvenlik için sil
        else:
            st.session_state["password_correct"] = False

    # İlk giriş
    if "password_correct" not in st.session_state:
        st.text_input("🔐 Şifre", type="password", on_change=password_entered, key="password")
        return False

    # Yanlış giriş
    elif not st.session_state["password_correct"]:
        st.text_input("🔐 Şifre", type="password", on_change=password_entered, key="password")
        st.error("❌ Şifre yanlış")
        return False

    # Doğru giriş
    return True

# Şifre doğru değilse uygulamayı durdur
if not check_password():
    st.stop()

# ----------------- BAKIM MODU -----------------
bakim_modu = False  # True yaparsan sistem kapanır

if bakim_modu:
    st.warning("Sistem bakımda")
    st.stop()

# ----------------- DATABASE -----------------
def get_connection():
    # Her çağrıda yeni connection açıyoruz (daha güvenli)
    return psycopg2.connect(st.secrets["DATABASE_URL"])

# ----------------- TABLO OLUŞTUR -----------------
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Öğrenci tablosu
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ogrenciler (
            id SERIAL PRIMARY KEY,
            ad TEXT NOT NULL,
            tc TEXT UNIQUE
        )
    """)

    # Ödeme tablosu (GELİŞTİRİLDİ)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS odemeler (
            id SERIAL PRIMARY KEY,
            ogrenci_id INTEGER REFERENCES ogrenciler(id),
            vade DATE NOT NULL,
            tutar DECIMAL(10,2),
            odenen_tutar DECIMAL(10,2) DEFAULT 0,
            durum TEXT DEFAULT 'Bekliyor'
        )
    """)

    conn.commit()
    cur.close()

init_db()

# ----------------- AY EKLE -----------------
def ay_ekle(baslangic_tarihi, ay_sayisi):
    # Kaç ay ileri gidileceğini hesaplar
    ay = baslangic_tarihi.month - 1 + ay_sayisi
    yil = baslangic_tarihi.year + ay // 12
    ay = ay % 12 + 1

    # Ayın maksimum gününü aşmamak için
    gun = min(baslangic_tarihi.day, calendar.monthrange(yil, ay)[1])

    return date(yil, ay, gun)

# ----------------- VERİ ÇEKME -----------------
def veri_getir(query, params=None):
    conn = get_connection()
    try:
        # SQL çalıştırılır ve DataFrame döner
        return pd.read_sql(query, conn, params=params)
    except:
        return pd.DataFrame()

# ----------------- UI -----------------
st.title("🏫 Tahsilat Sistemi")

# ----------------- YENİ ÖĞRENCİ -----------------
with st.expander("Yeni Kayıt"):
    ad = st.text_input("Ad")
    tc = st.text_input("TC")

    toplam = st.number_input("Toplam Tutar", min_value=0.0)
    taksit = st.number_input("Taksit", min_value=1, value=5)
    tarih = st.date_input("Başlangıç", value=date.today())

    if st.button("Kaydet"):
        conn = get_connection()
        cur = conn.cursor()

        # Öğrenci ekle
        cur.execute("INSERT INTO ogrenciler (ad, tc) VALUES (%s,%s) RETURNING id", (ad, tc))
        ogr_id = cur.fetchone()[0]

        # Taksitleri oluştur
        taksit_tutar = toplam / taksit

        for i in range(int(taksit)):
            cur.execute(
                "INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s,%s,%s)",
                (ogr_id, ay_ekle(tarih, i), taksit_tutar)
            )

        conn.commit()
        cur.close()

        st.success("Kayıt eklendi")
        st.rerun()

# ----------------- ÖĞRENCİ SEÇ -----------------
ogrenciler = veri_getir("SELECT id, ad FROM ogrenciler ORDER BY ad LIMIT 500")

if not ogrenciler.empty:
    secim = st.selectbox("Öğrenci", ogrenciler["ad"])

    # Seçilen öğrencinin ID'sini al
    ogr_id = ogrenciler[ogrenciler["ad"] == secim]["id"].values[0]

    # Öğrencinin ödemelerini çek
    df = veri_getir("SELECT * FROM odemeler WHERE ogrenci_id=%s ORDER BY vade", (ogr_id,))

    # Kalan borç hesapla
    df["kalan"] = df["tutar"] - df["odenen_tutar"]

    st.dataframe(df)

    # Ödenmemişleri filtrele
    bekleyen = df[df["kalan"] > 0]

    if not bekleyen.empty:
        sec = st.selectbox("Ödeme seç", bekleyen["id"])

        sec_row = bekleyen[bekleyen["id"] == sec].iloc[0]

        odeme = st.number_input("Ödeme", min_value=0.0, max_value=float(sec_row["kalan"]))

        if st.button("Tahsil Et"):
            conn = get_connection()
            cur = conn.cursor()

            # Yeni toplam ödenen tutar
            yeni_odenen = float(sec_row["odenen_tutar"]) + odeme

            # Durum belirleme
            durum = "Ödendi" if yeni_odenen >= float(sec_row["tutar"]) else "Bekliyor"

            # Güncelleme
            cur.execute("""
                UPDATE odemeler
                SET odenen_tutar=%s, durum=%s
                WHERE id=%s
            """, (yeni_odenen, durum, sec))

            conn.commit()
            cur.close()

            st.success("Tahsil edildi")
            st.rerun()
