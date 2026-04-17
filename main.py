import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime, timedelta, date
import calendar

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
            durum TEXT DEFAULT 'Bekliyor'
        )
    """)
    conn.commit()
    cur.close()

init_db()

# Tarih yardımcı fonksiyonu
def ay_ekle(baslangic_tarihi, ay_sayisi):
    ay = baslangic_tarihi.month - 1 + ay_sayisi
    yil = baslangic_tarihi.year + ay // 12
    ay = ay % 12 + 1
    gun = min(baslangic_tarihi.day, calendar.monthrange(yil, ay)[1])
    return date(yil, ay, gun)

# HIZ VE GÜNCELLEME DÜZELTMESİ (Bekliyor hatası için commit eklendi)
def veri_getir(query, params=None):
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        conn.commit()  # Veritabanı önbelleğini temizler, en taze veriyi okur
        return df
    except Exception as e:
        conn.rollback()
        return pd.DataFrame()

# Görünüm Ayarları
sutun_ayarlar = {
    "tutar": st.column_config.NumberColumn("Tutar", format="₺ %.2f"),
    "vade": st.column_config.DateColumn("Vade Tarihi", format="DD.MM.YYYY")
}

st.title("🏫 Öğrenci Kayıt ve Tahsilat Paneli")

# ----------------- 1. YENİ KAYIT VE MAKBUZ -----------------
with st.expander("👨‍🎓 Yeni Öğrenci Kaydı ve Sözleşme Oluştur", expanded=False):
    with st.form("kayit_formu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            y_ad = st.text_input("Öğrenci Adı Soyadı")
            y_veli = st.text_input("Veli Adı Soyadı")
            y_tc = st.text_input("TC Kimlik No")
        with c2:
            y_tel = st.text_input("Telefon")
            y_toplam = st.number_input("Toplam Eğitim Bedeli", min_value=0.0, step=1000.0)
            # PARA OKUNUŞU İÇİN YARDIMCI EKRAN
            st.caption(f"**Girilen Tutarın Okunuşu:** :blue[₺ {y_toplam:,.2f}]")
            
            y_taksit = st.number_input("Taksit Sayısı", min_value=1, value=10)
        
        y_tarih = st.date_input("İlk Ödeme Tarihi", value=date.today())
        submit = st.form_submit_button("Kaydı Tamamla ve Makbuz Oluştur")

    if submit and y_ad and y_tc:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (%s, %s, %s, %s) ON CONFLICT (tc) DO UPDATE SET ad=EXCLUDED.ad RETURNING id", 
                        (y_ad, y_veli, y_tel, y_tc))
            ogr_id = cur.fetchone()[0]
            
            taksit_tutari = y_toplam / y_taksit
            for i in range(int(y_taksit)):
                vade = ay_ekle(y_tarih, i)
                cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", 
                            (ogr_id, vade, taksit_tutari))
            conn.commit()
            
            st.success(f"Kayıt Başarılı! Aşağıdaki dökümü yazdırıp veliye verebilirsiniz.")
            
            # Yazdırılabilir Alan
            st.markdown(f"""
            <div style="border: 2px solid #ccc; padding: 20px; border-radius: 10px; background-color: white; color: black;">
                <h2 style="text-align: center;">ÖĞRENCİ KAYIT VE ÖDEME PLANI</h2>
                <hr>
                <p><b>Öğrenci:</b> {y_ad} &nbsp;&nbsp; <b>TC:</b> {y_tc}</p>
                <p><b>Veli:</b> {y_veli} &nbsp;&nbsp; <b>Tel:</b> {y_tel}</p>
                <p><b>Toplam Tutar:</b> ₺ {y_toplam:,.2f} &nbsp;&nbsp; <b>Taksit Sayısı:</b> {y_taksit}</p>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background-color: #f2f2f2;">
                        <th style="border: 1px solid #ddd; padding: 8px;">Taksit</th>
                        <th style="border: 1px solid #ddd; padding: 8px;">Vade</th>
                        <th style="border: 1px solid #ddd; padding: 8px;">Tutar</th>
                    </tr>
                    {" ".join([f"<tr><td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{j+1}</td><td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{ay_ekle(y_tarih, j).strftime('%d.%m.%Y')}</td><td style='border: 1px solid #ddd; padding: 8px; text-align: right;'>₺ {taksit_tutari:,.2f}</td></tr>" for j in range(int(y_taksit))])}
                </table>
                <br>
                <p style="text-align: right;">İmza<br><br>________________</p>
            </div>
            """, unsafe_allow_html=True)
            
        except Exception as e:
            conn.rollback()
            st.error(f"Hata: {e}")
        finally:
            cur.close()

# ----------------- 2. DETAYLI TAHSİLAT VE ÖĞRENCİ KARTI -----------------
st.divider()
st.subheader("💰 Tahsilat İşlemi ve Öğrenci Kartı")

arama = st.text_input("🔍 Öğrenci Bul (Ad veya TC giriniz)")

if arama:
    ogr_df = veri_getir("SELECT * FROM ogrenciler WHERE ad ILIKE %s OR tc LIKE %s", (f"%{arama}%", f"%{arama}%"))
    
    if not ogr_df.empty:
        secilen_ogr_id = ogr_df.iloc[0]['id']
        secilen_ogr_ad = ogr_df.iloc[0]['ad']
        secilen_ogr_tc = ogr_df.iloc[0]['tc'] # TC EKLENDİ
        
        kart_df = veri_getir("""
            SELECT id as islem_no, vade, tutar, durum 
            FROM odemeler 
            WHERE ogrenci_id = %s 
            ORDER BY vade ASC
        """, (int(secilen_ogr_id),))
        
        t_borc = kart_df['tutar'].sum()
        t_odenen = kart_df[kart_df['durum'] == 'Ödendi']['tutar'].sum()
        t_kalan = t_borc - t_odenen
        
        # TC KİMLİK KART BAŞLIĞINA EKLENDİ
        st.markdown(f"### 📋 {secilen_ogr_ad} | TC: {secilen_ogr_tc}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Toplam Kayıt Bedeli", f"₺ {t_borc:,.2f}")
        m2.metric("Tahsil Edilen", f"₺ {t_odenen:,.2f}", delta_color="normal")
        m3.metric("Kalan Borç", f"₺ {t_kalan:,.2f}", delta="-₺ "+str(t_odenen))

        st.write("**Tüm Taksit Geçmişi:**")
        st.dataframe(kart_df, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

        bekleyenler = kart_df[kart_df['durum'] == 'Bekliyor']
        if not bekleyenler.empty:
            st.divider()
            st.write("#### Ödeme Al")
            secenekler = bekleyenler.apply(lambda x: f"İşlem: {x['islem_no']} | Vade: {x['vade']} | Tutar: {x['tutar']} TL", axis=1).tolist()
            secim = st.selectbox("Tahsil edilecek taksiti seçin:", secenekler)
            
            islem_id = int(secim.split("İşlem: ")[1].split(" |")[0])
            asil_tutar = float(bekleyenler[bekleyenler['islem_no'] == islem_id]['tutar'].values[0])
            vade_tarihi = bekleyenler[bekleyenler['islem_no'] == islem_id]['vade'].values[0]

            tutar_giris = st.number_input("Kasaya Giren Miktar", min_value=0.0, max_value=asil_tutar, value=asil_tutar, step=500.0)
            # PARA OKUNUŞU İÇİN YARDIMCI EKRAN
            st.caption(f"**Kasaya İşlenecek Net Tutar:** :green[₺ {tutar_giris:,.2f}]")
            
            if st.button("Tahsilatı Kesinleştir"):
                conn = get_connection()
                cur = conn.cursor()
                try:
                    if tutar_giris < asil_tutar:
                        cur.execute("UPDATE odemeler SET durum='Ödendi', tutar=%s WHERE id=%s", (tutar_giris, islem_id))
                        cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", 
                                    (int(secilen_ogr_id), vade_tarihi, asil_tutar - tutar_giris))
                    else:
                        cur.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=%s", (islem_id,))
                    conn.commit()
                    st.success("Ödeme kartına başarıyla işlendi!")
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(f"Hata: {e}")
                finally:
                    cur.close()
        else:
            st.success("Bu öğrencinin bekleyen borcu bulunmamaktadır.")
    else:
        st.warning("Öğrenci bulunamadı.")

# ----------------- 3. GENEL DURUM -----------------
st.divider()
t1, t2 = st.tabs(["📅 Günlük Takip", "🗄️ Genel Arşiv"])

with t1:
    st.subheader("Bugün ve Gecikenler")
    df_takip = veri_getir("""
        SELECT o.vade, ogr.ad, o.tutar, o.durum 
        FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
        WHERE o.vade <= %s AND o.durum = 'Bekliyor' ORDER BY o.vade ASC
    """, (date.today(),))
    st.dataframe(df_takip, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

with t2:
    st.subheader("Sistemdeki Tüm Hareketler")
    df_arsiv = veri_getir("""
        SELECT o.vade, ogr.ad, o.tutar, o.durum 
        FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
        ORDER BY o.vade DESC
    """)
    st.dataframe(df_arsiv, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
