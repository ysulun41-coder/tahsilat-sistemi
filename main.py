import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# Sayfa Genişliği ve Başlık
st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# --- YARDIMCI FONKSİYON: Türkçe Karakter Arama ---
def tr_upper(text):
    if pd.isna(text):
        return ""
    text = str(text)
    harfler = { "i": "İ", "ı": "I", "ğ": "Ğ", "ü": "Ü", "ş": "Ş", "ö": "Ö", "ç": "Ç" }
    for k, v in harfler.items():
        text = text.replace(k, v)
        text = text.replace(k.upper(), v)
    return text.upper()

# ----------------- VERİTABANI FONKSİYONLARI -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def fix_database():
    conn = get_connection()
    cursor = conn.cursor()
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

# ----------------- ÖĞRENCİ + BORÇ EKLEME -----------------
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

# ----------------- TAKİP PANELİ -----------------
col_bugun, col_geciken = st.columns(2)
bugun = date.today()

with col_bugun:
    st.subheader("📅 Bugünün Ödemeleri")
    if not df_plan.empty:
        bugun_df = df_plan[(df_plan["vade"] == bugun) & (df_plan["durum"] != "Ödendi")]
        # KISA DEVRE YAPMAYAN GÜVENLİ YAPI:
        if not bugun_df.empty:
            st.dataframe(bugun_df, use_container_width=True, hide_index=True) 
        else:
            st.info("Bugün ödeme yok.")

with col_geciken:
    st.subheader("⏰ Geciken Ödemeler")
    if not df_plan.empty:
        geciken_df = df_plan[(df_plan["vade"] < bugun) & (df_plan["durum"] != "Ödendi")]
        # KISA DEVRE YAPMAYAN GÜVENLİ YAPI:
        if not geciken_df.empty:
            st.dataframe(geciken_df, use_container_width=True, hide_index=True) 
        else:
            st.success("Gecikmiş ödeme yok.")

# ----------------- GELİŞMİŞ ARAMALI VE SERBEST TAHSİLAT -----------------
st.divider()
st.subheader("💰 Akıllı Tahsilat Ekranı")

arama = st.text_input("Öğrenci Ara (İsim veya Öğrenci ID giriniz)", placeholder="Örn: Oğuzhan veya 41")

if not df_plan.empty:
    df_bekliyor = df_plan[df_plan["durum"] != "Ödendi"].copy()
    
    if arama:
        arama_upper = tr_upper(arama)
        df_bekliyor = df_bekliyor[
            df_bekliyor['ad'].apply(tr_upper).str.contains(arama_upper, regex=False) | 
            (df_bekliyor['ogr_id'].astype(str) == arama)
        ]

    if not df_bekliyor.empty:
        df_bekliyor["secim_metni"] = df_bekliyor.apply(
            lambda x: f"{x['ad']} | Vade: {x['vade']} | Tutar: {x['tutar']} TL (İşlem No: {x['islem_no']})", axis=1
        )
        
        secenekler = ["--- Lütfen Seçim Yapınız ---"] + df_bekliyor["secim_metni"].tolist()
        secilen_metin = st.selectbox("Tahsil edilecek taksiti seçin:", secenekler)
        
        if secilen_metin != "--- Lütfen Seçim Yapınız ---":
            secilen_islem_no = int(secilen_metin.split("(İşlem No: ")[1].replace(")", ""))
            sec_satir = df_bekliyor[df_bekliyor["islem_no"] == secilen_islem_no].iloc[0]
            ogr_id_secilen = sec_satir['ogr_id']
            
            # --- ÖĞRENCİ BORÇ PANOSU ---
            ogr_tum_kayitlar = df_plan[df_plan['ogr_id'] == ogr_id_secilen]
            toplam_planlanan = ogr_tum_kayitlar['tutar'].sum()
            toplam_odenen = ogr_tum_kayitlar[ogr_tum_kayitlar['durum'] == 'Ödendi']['tutar'].sum()
            guncel_kalan = toplam_planlanan - toplam_odenen
            
            st.markdown(f"### 👤 {sec_satir['ad']} - Hesap Özeti")
            kutu1, kutu2, kutu3 = st.columns(3)
            kutu1.metric("Toplam Planlanan Borç", f"{toplam_planlanan:,.2f} TL")
            kutu2.metric("Bugüne Kadar Ödenen", f"{toplam_odenen:,.2f} TL")
            kutu3.metric("Kalan Net Borç", f"{guncel_kalan:,.2f} TL")
            
            st.info(f"Seçili Taksit Vadesi: **{sec_satir['vade']}** | Bekleyen Asıl Tutar: **{sec_satir['tutar']} TL**")
            
            # --- SERBEST MİKTAR GİRİŞİ ---
            orjinal_tutar = float(sec_satir['tutar'])
            alinan_tutar = st.number_input("Kasaya Girecek Tahsilat Miktarı (TL):", min_value=0.0, value=orjinal_tutar, step=50.0)
            
            if st.button("Ödemeyi Onayla ve Kasaya İşle"):
                conn = get_connection()
                cursor = conn.cursor()
                
                if alinan_tutar < orjinal_tutar:
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (alinan_tutar, secilen_islem_no))
                    kalan_fark = orjinal_tutar - alinan_tutar
                    cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')",
                                   (ogr_id_secilen, sec_satir['vade'], kalan_fark))
                    st.session_state.mesaj = f"Eksik tahsilat! {alinan_tutar} TL alındı, kalan {kalan_fark} TL listeye yeni taksit olarak eklendi."
                
                elif alinan_tutar == orjinal_tutar:
                    cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (secilen_islem_no,))
                    st.session_state.mesaj = "Tahsilat tam olarak yapıldı."
                
                else:
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (alinan_tutar, secilen_islem_no))
                    st.session_state.mesaj = f"Fazla tahsilat yapıldı! {alinan_tutar} TL kaydedildi."

                conn.commit()
                conn.close()
                st.rerun()

if "mesaj" in st.session_state:
    st.success(st.session_state.mesaj)
    del st.session_state.mesaj

# -----------------
