import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime, date
import calendar
import time

# Sayfa Ayarları
st.set_page_config(page_title="Okul Tahsilat Sistemi", layout="wide")

# ----------------- VERİTABANI VE BAĞLANTI -----------------
@st.cache_resource(ttl=300)
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
            durum TEXT DEFAULT 'Bekliyor',
            odeme_yontemi TEXT,
            makbuz_no TEXT
        )
    """)
    conn.commit()
    cur.close()

init_db()

def ay_ekle(baslangic_tarihi, ay_sayisi):
    ay = baslangic_tarihi.month - 1 + ay_sayisi
    yil = baslangic_tarihi.year + ay // 12
    ay = ay % 12 + 1
    gun = min(baslangic_tarihi.day, calendar.monthrange(yil, ay)[1])
    return date(yil, ay, gun)

def veri_getir(query, params=None):
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        conn.commit()
        return df
    except Exception as e:
        conn.rollback()
        return pd.DataFrame()

sutun_ayarlar = {
    "tutar": st.column_config.NumberColumn("Tutar", format="₺ %.2f"),
    "vade": st.column_config.DateColumn("Vade Tarihi", format="DD.MM.YYYY")
}

st.title("🏫 Öğrenci Kayıt ve Tahsilat Paneli")

# ----------------- FİNANSAL KOKPİT -----------------
ozet_df = veri_getir("SELECT tutar, durum FROM odemeler")
if not ozet_df.empty:
    toplam_bekleyen = ozet_df[ozet_df['durum'] == 'Bekliyor']['tutar'].sum()
    toplam_odenen = ozet_df[ozet_df['durum'] == 'Ödendi']['tutar'].sum()
    genel_hedef = toplam_bekleyen + toplam_odenen
    
    st.markdown("### 📊 Genel Finans Durumu")
    g1, g2, g3 = st.columns(3)
    g1.metric("Eğitim Sözleşmeleri Toplamı", f"₺ {genel_hedef:,.2f}")
    g2.metric("Kasaya Giren (Tahsil Edilen)", f"₺ {toplam_odenen:,.2f}")
    g3.metric("Dışarıda Bekleyen Alacak", f"₺ {toplam_bekleyen:,.2f}")
st.divider()

# ----------------- 1. YENİ KAYIT -----------------
with st.expander("👨‍🎓 Yeni Öğrenci Kaydı ve Sözleşme Oluştur", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        y_ad = st.text_input("Öğrenci Adı Soyadı")
        y_veli = st.text_input("Veli Adı Soyadı")
        y_tc = st.text_input("TC Kimlik No", max_chars=11)
    with c2:
        y_tel = st.text_input("Telefon")
        y_toplam = st.number_input("Toplam Eğitim Bedeli", min_value=0.0, step=1000.0)
        y_taksit = st.number_input("Taksit Sayısı", min_value=1, value=10)
    
    y_tarih = st.date_input("İlk Ödeme Tarihi", value=date.today())
    if st.button("Kaydı Tamamla", type="primary"):
        if not y_ad or not y_tc:
            st.error("🚨 Ad Soyad ve TC alanlarını doldurun.")
        else:
            conn = get_connection()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (%s, %s, %s, %s) RETURNING id", 
                            (y_ad, y_veli, y_tel, y_tc))
                ogr_id = cur.fetchone()[0]
                taksit_tutari = y_toplam / y_taksit
                for i in range(int(y_taksit)):
                    vade = ay_ekle(y_tarih, i)
                    cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", 
                                (ogr_id, vade, taksit_tutari))
                conn.commit()
                st.success("Kayıt Başarılı!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                conn.rollback()
                st.error(f"Hata: {e}")
            finally:
                cur.close()

# ----------------- 2. DETAYLI TAHSİLAT VE ÖĞRENCİ KARTI -----------------
st.divider()
st.subheader("💰 Tahsilat İşlemi ve Öğrenci Kartı")
tum_ogrenciler = veri_getir("SELECT id, ad, tc FROM ogrenciler ORDER BY ad ASC")

if not tum_ogrenciler.empty:
    ogrenci_listesi = tum_ogrenciler.apply(lambda x: f"{x['ad']} | TC: {x['tc']} | ID:{x['id']}", axis=1).tolist()
    secilen_metin = st.selectbox("🔍 Öğrenci Bul:", ["-- Seçiniz --"] + ogrenci_listesi)

    if secilen_metin != "-- Seçiniz --":
        secilen_ogr_id = int(secilen_metin.split("ID:")[1])
        secilen_ogr_ad = secilen_metin.split(" |")[0]
        secilen_ogr_tc = secilen_metin.split("TC: ")[1].split(" |")[0]
        
        kart_df = veri_getir("SELECT id as islem_no, vade, tutar, durum, odeme_yontemi, makbuz_no FROM odemeler WHERE ogrenci_id = %s ORDER BY vade ASC", (secilen_ogr_id,))
        kart_df['odeme_yontemi'] = kart_df['odeme_yontemi'].fillna("-")
        kart_df['makbuz_no'] = kart_df['makbuz_no'].fillna("-")
        
        st.markdown(f"### 📋 {secilen_ogr_ad}")
        st.dataframe(kart_df, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

        # Ödeme Alma
        bekleyenler = kart_df[kart_df['durum'] == 'Bekliyor']
        if not bekleyenler.empty:
            with st.container(border=True):
                secim = st.selectbox("Taksit Seç:", bekleyenler.apply(lambda x: f"No: {x['islem_no']} | Vade: {x['vade']} | ₺{x['tutar']}", axis=1).tolist())
                is_id = int(secim.split("No: ")[1].split(" |")[0])
                asil_t = float(bekleyenler[bekleyenler['islem_no'] == is_id]['tutar'].values[0])
                
                c_y, c_t = st.columns(2)
                yontem = c_y.selectbox("Yöntem", ["Nakit", "Kredi Kartı", "EFT/Havale"])
                t_giris = c_t.number_input("Miktar", min_value=0.0, max_value=asil_t, value=asil_t)
                
                if st.button("Tahsilat Yap ve Makbuz Üret"):
                    m_no = f"MKBZ-{datetime.now().strftime('%Y%m%d')}-{is_id}"
                    conn = get_connection(); cur = conn.cursor()
                    try:
                        if t_giris < asil_t:
                            cur.execute("UPDATE odemeler SET durum='Ödendi', tutar=%s, odeme_yontemi=%s, makbuz_no=%s WHERE id=%s", (t_giris, yontem, m_no, is_id))
                            cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", (secilen_ogr_id, bekleyenler[bekleyenler['islem_no'] == is_id]['vade'].values[0], asil_t - t_giris))
                        else:
                            cur.execute("UPDATE odemeler SET durum='Ödendi', odeme_yontemi=%s, makbuz_no=%s WHERE id=%s", (yontem, m_no, is_id))
                        conn.commit(); st.session_state.goster_is_id = is_id; st.rerun()
                    except Exception as e: conn.rollback(); st.error(f"Hata: {e}")
                    finally: cur.close()

        # Makbuz Gösterimi
        odenmisler = kart_df[kart_df['durum'] == 'Ödendi']
        if not odenmisler.empty:
            st.write("#### 🖨️ Makbuz")
            m_sec = st.selectbox("İşlem Seç:", odenmisler.apply(lambda x: f"İşlem No: {x['islem_no']} | {x['makbuz_no']}", axis=1).tolist())
            m_id = int(m_sec.split("İşlem No: ")[1].split(" |")[0])
            m_detay = odenmisler[odenmisler['islem_no'] == m_id].iloc[0]
            st.markdown(f"""<div style="border:2px dashed #666; padding:20px; color:black; background:#fff; text-align:center;">
                <h3>TAHSİLAT MAKBUZU</h3><p>Makbuz No: {m_detay['makbuz_no']}</p><hr>
                <p>Öğrenci: {secilen_ogr_ad} | Tutar: ₺{m_detay['tutar']:,.2f} | Yöntem: {m_detay['odeme_yontemi']}</p>
                <p>Tarih: {m_detay['vade'].strftime('%d.%m.%Y')}</p></div>""", unsafe_allow_html=True)

# ----------------- 3. GÜNLÜK TAKİP (SADECE BUGÜN VE GEÇMİŞ) -----------------
st.divider()
st.subheader("📅 Günlük Ödeme Takip Ekranı")
df_takip = veri_getir("""
    SELECT o.vade, ogr.ad, o.tutar, o.durum FROM odemeler o 
    JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
    WHERE o.vade <= %s AND o.durum = 'Bekliyor' ORDER BY o.vade ASC
""", (date.today(),))
if not df_takip.empty:
    st.dataframe(df_takip, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
else:
    st.success("Bugün bekleyen veya geciken ödeme yok.")

# ----------------- SİSTEM ARAÇLARI (EXCEL AKTARIM DÜZELTİLDİ) -----------------
st.divider()
with st.expander("⚙️ Sistem Yöneticisi Araçları", expanded=False):
    yuklenen_dosya = st.file_uploader("Excel Dosyanızı Yükleyin", type=["xlsx", "xls", "csv"])
    if st.button("🚀 Excel'den Veri Aktar"):
        if yuklenen_dosya is not None:
            conn = None
            try:
                if yuklenen_dosya.name.endswith('.csv'):
                    df_excel = pd.read_csv(yuklenen_dosya, sep=None, engine='python', dtype=str)
                else:
                    df_excel = pd.read_excel(yuklenen_dosya, dtype=str)
                df_excel.columns = df_excel.columns.str.strip()
                conn = get_connection(); cur = conn.cursor()
                for _, row in df_excel.iterrows():
                    tc = str(row.get('Öğr. TC Kimlik No', '')).strip().replace('.0', '')
                    ad = str(row.get('Öğrencinin Adı Soyadı', '')).strip()
                    if not tc or tc == 'nan': continue
                    vade_h = row.get('Vade Tarihi')
                    vade = pd.to_datetime(vade_h, errors='coerce').date() if pd.notna(pd.to_datetime(vade_h, errors='coerce')) else date.today()
                    tutar = float(str(row.get('Ödeme Tutarı', '0')).replace(',', '.').replace('₺', '').strip())
                    
                    # ÖDENDİ / ÖDENMEDİ MANTIĞI
                    durum_h = str(row.get('Ödeme Gerçekleşti mi?', '')).strip().upper()
                    if "ÖDEN" in durum_h and "ÖDENMEDİ" not in durum_h:
                        durum = 'Ödendi'; yontem = 'Aktarım'; mkbz = 'AKT-2026'
                    else:
                        durum = 'Bekliyor'; yontem = None; mkbz = None
                    
                    cur.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (%s, '-', '-', %s) ON CONFLICT (tc) DO UPDATE SET ad=EXCLUDED.ad RETURNING id", (ad, tc))
                    ogr_id = cur.fetchone()[0]
                    cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum, odeme_yontemi, makbuz_no) VALUES (%s, %s, %s, %s, %s, %s)", (ogr_id, vade, tutar, durum, yontem, mkbz))
                conn.commit(); st.success("Aktarım Tamamlandı!"); st.rerun()
            except Exception as e:
                if conn: conn.rollback()
                st.error(f"Hata: {e}")
            finally:
                if 'cur' in locals(): cur.close()

    if st.button("🚨 TÜM VERİTABANINI SIFIRLA"):
        conn = get_connection(); cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS odemeler CASCADE; DROP TABLE IF EXISTS ogrenciler CASCADE;")
        conn.commit(); st.success("Sıfırlandı. Sayfayı yenileyin."); cur.close()
