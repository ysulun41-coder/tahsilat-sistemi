import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime, timedelta, date

# Sayfa Ayarları
st.set_page_config(page_title="Pro Tahsilat Sistemi", layout="wide")

# ----------------- HIZLANDIRILMIŞ BAĞLANTI (ÖNBELLEKLİ) -----------------
# ttl=300 (5 dakika) -> Bağlantı tünelini 5 dakika boyunca açık tutar!
@st.cache_resource(ttl=300)
def get_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # Öğrenciler Tablosu
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ogrenciler (
            id SERIAL PRIMARY KEY,
            ad TEXT NOT NULL,
            veli TEXT,
            telefon TEXT,
            tc TEXT UNIQUE
        )
    """)
    # Ödemeler Tablosu
    cur.execute("""
        CREATE TABLE IF NOT EXISTS odemeler (
            id SERIAL PRIMARY KEY,
            ogrenci_id INTEGER REFERENCES ogrenciler(id),
            vade DATE NOT NULL,
            tutar DECIMAL(10,2) NOT NULL,
            durum TEXT DEFAULT 'Bekliyor'
        )
    """)
    conn.commit()
    cur.close()
    # DİKKAT: conn.close() silindi, tünel artık kapanmayacak.

# Uygulama başladığında tabloları hazırla
init_db()

# --- PARA BİRİMİ VE TARİH GÖRÜNÜM AYARLARI ---
sutun_ayarlar = {
    "tutar": st.column_config.NumberColumn("Tutar", format="₺ %.2f"),
    "vade": st.column_config.DateColumn("Vade Tarihi", format="DD.MM.YYYY")
}

st.title("🚀 Güvenli & Hızlı Tahsilat Sistemi")

# ----------------- YENİ ÖĞRENCİ KAYIT -----------------
with st.expander("👨‍🎓 Yeni Kayıt ve Borçlandırma", expanded=False):
    with st.form("kayit_formu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            y_ad = st.text_input("Öğrenci Adı Soyadı")
            y_veli = st.text_input("Veli Adı")
            y_tc = st.text_input("TC Kimlik (Zorunlu)")
        with c2:
            y_tel = st.text_input("Telefon")
            y_borc = st.number_input("Toplam Borç (TL)", min_value=0.0, step=100.0)
            y_taksit = st.number_input("Taksit Sayısı", min_value=1, step=1, value=1)
        
        y_tarih = st.date_input("İlk Taksit Tarihi", value=date.today())
        submit = st.form_submit_button("Sisteme Kaydet")

    if submit and y_ad and y_tc and y_borc > 0:
        conn = get_connection()
        cur = conn.cursor()
        try:
            # Önce öğrenciyi ekle veya mevcut olanı bul
            cur.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (%s, %s, %s, %s) ON CONFLICT (tc) DO UPDATE SET ad=EXCLUDED.ad RETURNING id", 
                        (y_ad, y_veli, y_tel, y_tc))
            ogr_id = cur.fetchone()[0]
            
            # Taksitleri ekle
            taksit_tutari = y_borc / y_taksit
            for i in range(int(y_taksit)):
                vade = y_tarih + timedelta(days=30 * i)
                cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", 
                            (ogr_id, vade, taksit_tutari))
            
            conn.commit()
            st.success(f"{y_ad} ve {y_taksit} taksit başarıyla kaydedildi.")
        except Exception as e:
            conn.rollback()
            st.error(f"Hata oluştu: {e}")
        finally:
            cur.close()
            # conn.close() silindi
            st.rerun()

# ----------------- HIZLI VERİ ÇEKME FONKSİYONU -----------------
def veri_getir(query, params=None):
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        return df
    except Exception as e:
        conn.rollback() # Pandas hata verirse kilitlenmeyi önle
        st.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame()

# ----------------- TAKİP VE TAHSİLAT -----------------
bugun = date.today()
st.divider()
p1, p2 = st.columns(2)

with p1:
    st.subheader("📅 Bugünün Ödemeleri")
    df_bugun = veri_getir("""SELECT o.id, ogr.ad, o.vade, o.tutar FROM odemeler o 
                          JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
                          WHERE o.vade = %s AND o.durum = 'Bekliyor'""", (bugun,))
    st.dataframe(df_bugun, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

with p2:
    st.subheader("⏰ Geciken Ödemeler")
    df_geciken = veri_getir("""SELECT o.id, ogr.ad, o.vade, o.tutar FROM odemeler o 
                            JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
                            WHERE o.vade < %s AND o.durum = 'Bekliyor'""", (bugun,))
    st.dataframe(df_geciken, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

# ----------------- TAHSİLAT İŞLEMİ -----------------
st.subheader("💰 Tahsilat Girişi")
arama = st.text_input("🔍 Öğrenci İsmine Göre Ara")

if arama:
    df_arama = veri_getir("""SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, o.vade, o.tutar FROM odemeler o 
                          JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
                          WHERE ogr.ad ILIKE %s AND o.durum = 'Bekliyor'""", (f"%{arama}%",))
    
    if not df_arama.empty:
        df_arama["etiket"] = df_arama.apply(lambda x: f"{x['ad']} | Vade: {x['vade']} | {x['tutar']} TL", axis=1)
        secim = st.selectbox("Taksit Seçin", df_arama["etiket"].tolist())
        
        islem_id = int(df_arama[df_arama["etiket"] == secim]["islem_no"].values[0])
        asil_tutar = float(df_arama[df_arama["etiket"] == secim]["tutar"].values[0])
        ogr_id = int(df_arama[df_arama["etiket"] == secim]["ogr_id"].values[0])
        vade_tarihi = df_arama[df_arama["etiket"] == secim]["vade"].values[0]

        tutar_giris = st.number_input("Alınan Ödeme", min_value=0.0, max_value=asil_tutar, value=asil_tutar)
        
        if st.button("Tahsilatı Onayla"):
            conn = get_connection()
            cur = conn.cursor()
            try:
                if tutar_giris < asil_tutar:
                    cur.execute("UPDATE odemeler SET durum='Ödendi', tutar=%s WHERE id=%s", (tutar_giris, islem_id))
                    cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", 
                                (ogr_id, vade_tarihi, asil_tutar - tutar_giris))
                else:
                    cur.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=%s", (islem_id,))
                
                conn.commit()
                st.success("Tahsilat başarıyla işlendi.")
            except Exception as e:
                conn.rollback()
                st.error(f"Hata: {e}")
            finally:
                cur.close()
                st.rerun()

# ----------------- ARŞİV -----------------
st.divider()
tab1, tab2 = st.tabs(["📊 Tüm Hareketler", "📁 Ödenmiş Arşivi"])

with tab1:
    st.dataframe(veri_getir("SELECT ogr.ad, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id ORDER BY o.vade DESC"), 
                 use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

with tab2:
    st.dataframe(veri_getir("SELECT ogr.ad, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id WHERE o.durum='Ödendi' ORDER BY o.vade DESC"), 
                 use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
