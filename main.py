import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# Sayfa Genişliği
st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# ----------------- VERİTABANI FONKSİYONLARI -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def fix_database():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tablo Oluşturma
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
    
    # TC Sütunu Kontrolü (Sigorta)
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
    # Öğrenciler
    df_ogr = pd.read_sql("SELECT * FROM ogrenciler", conn)
    # Taksitler ve Öğrenci Bilgileri Birleşik
    df_plan = pd.read_sql("""
    SELECT o.id, ogr.ad, ogr.telefon, ogr.tc, o.vade, o.tutar, o.durum
    FROM odemeler o
    JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id
    """, conn)
    
    # Tarih formatını düzenle
    if not df_plan.empty:
        df_plan["vade"] = pd.to_datetime(df_plan["vade"]).dt.date
    conn.close()
    return df_ogr, df_plan

df_ogr, df_plan = verileri_yukle()

# ----------------- ÖĞRENCİ + BORÇ EKLEME -----------------
with st.expander("👨‍🎓 Yeni Kayıt ve Borçlandırma", expanded=False):
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

    if st.button("Kaydı Tamamla ve Taksitlendir"):
        if ogrenci and toplam > 0:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Öğrenci var mı bak, yoksa ekle (Öğrenci ID burada sabitlenir)
            mevcut = df_ogr[df_ogr["ad"] == ogrenci]
            if not mevcut.empty:
                ogr_id = int(mevcut["id"].values[0])
            else:
                cursor.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)",
                               (ogrenci, veli, telefon, tc))
                ogr_id = cursor.lastrowid

            # Taksitleri oluştur (Her taksite benzersiz İşlem ID'si verilir)
            tutar = toplam / taksit
            for i in range(int(taksit)):
                vade = ilk_tarih + timedelta(days=30 * i)
                cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, ?)",
                               (ogr_id, vade, tutar, "Bekliyor"))
            
            conn.commit()
            conn.close()
            st.success(f"{ogrenci} için {taksit} taksit başarıyla oluşturuldu!")
            st.rerun()
        else:
            st.error("Lütfen öğrenci adı ve toplam borç giriniz.")

# ----------------- TAKİP PANELİ (BUGÜN / GECİKEN) -----------------
col_bugun, col_geciken = st.columns(2)
bugun = date.today()

with col_bugun:
    st.subheader("📅 Bugünün Ödemeleri")
    if not df_plan.empty:
        bugun_df = df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")]
        if not bugun_df.empty:
            st.dataframe(bugun_df, use_container_width=True)
        else:
            st.info("Bugün için ödeme yok.")

with col_geciken:
    st.subheader("⏰ Geciken Ödemeler")
    if not df_plan.empty:
        geciken_df = df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")]
        if not geciken_df.empty:
            st.warning(f"{len(geciken_df)} adet gecikmiş ödeme var!")
            st.dataframe(geciken_df, use_container_width=True)
        else:
            st.success("Harika! Gecikmiş ödeme bulunmuyor.")

# ----------------- TAHSİLAT YAPMA -----------------
st.divider()
st.subheader("💰 Elle Tahsilat Yap")

if not df_plan.empty:
    # Sadece bekleyenleri göster
    df_bekliyor = df_plan[df_plan["durum"] != "Ödendi"].copy()
    
    if not df_bekliyor.empty:
        # Kafa karıştıran "ID" metni "İşlem No" olarak değiştirildi
        df_bekliyor["liste_metni"] = df_bekliyor.apply(
            lambda x: f"İşlem No: {x['id']} ➔ {x['ad']} | Vade: {x['vade']} | Tutar: {x['tutar']} TL", axis=1
        )
        
        secilen_metin = st.selectbox("Tahsil edilecek taksiti seçin:", df_bekliyor["liste_metni"])
        
        # Seçilen İşlem No'yu arka planda ayıkla
        secilen_id = int(secilen_metin.split(" ➔ ")[0].replace("İşlem No: ", ""))
        
        # Seçilen satırın detayını göster
        sec_satir = df_bekliyor[df_bekliyor["id"] == secilen_id]
        st.info(f"Seçilen: **{sec_satir['ad'].values[0]}** - Tutar: **{sec_satir['tutar'].values[0]} TL**")

        if st.button("Ödemeyi Onayla (Tahsil Edildi)"):
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (secilen_id,))
            conn.commit()
            conn.close()
            st.success("Ödeme başarıyla tahsil edildi.")
            st.rerun()
    else:
        st.write("Tahsil edilecek bekleyen taksit kalmadı.")

# ----------------- LİSTELER (ARŞİV VE TÜMÜ) -----------------
st.divider()
tab1, tab2 = st.tabs(["📋 Tüm Taksitler", "📁 Arşiv (Ödenenler)"])

with tab1:
    if not df_plan.empty:
        st.dataframe(df_plan.sort_values(by="vade"), use_container_width=True)

with tab2:
    if not df_plan.empty:
        arsiv_df = df_plan[df_plan["durum"] == "Ödendi"]
        st.dataframe(arsiv_df, use_container_width=True)
