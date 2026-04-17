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
            durum TEXT DEFAULT 'Bekliyor'
        )
    """)
    
    try:
        cur.execute("ALTER TABLE odemeler ADD COLUMN IF NOT EXISTS odeme_yontemi TEXT")
        cur.execute("ALTER TABLE odemeler ADD COLUMN IF NOT EXISTS makbuz_no TEXT")
    except:
        pass
        
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

# ----------------- 1. YENİ KAYIT VE SÖZLEŞME -----------------
with st.expander("👨‍🎓 Yeni Öğrenci Kaydı ve Sözleşme Oluştur", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        y_ad = st.text_input("Öğrenci Adı Soyadı")
        y_veli = st.text_input("Veli Adı Soyadı")
        y_tc = st.text_input("TC Kimlik No", max_chars=11)
    with c2:
        y_tel = st.text_input("Telefon")
        y_toplam = st.number_input("Toplam Eğitim Bedeli", min_value=0.0, step=1000.0)
        st.markdown(f"**💰 Toplam Tutar:** <span style='color: green; font-size: 18px;'>₺ {y_toplam:,.2f}</span>", unsafe_allow_html=True)
        y_taksit = st.number_input("Taksit Sayısı", min_value=1, value=10)
    
    y_tarih = st.date_input("İlk Ödeme Tarihi", value=date.today())
    submit = st.button("Kaydı Tamamla", type="primary")

    if submit:
        if not y_ad or not y_tc:
            st.error("🚨 Lütfen Ad Soyad ve TC Kimlik numarası alanlarını doldurun.")
        elif len(y_tc) != 11 or not y_tc.isdigit():
            st.error("🚨 HATA: TC Kimlik Numarası tam 11 haneli olmalı ve sadece rakamlardan oluşmalıdır!")
        elif y_toplam <= 0:
            st.error("🚨 HATA: Lütfen geçerli bir eğitim bedeli giriniz.")
        else:
            conn = get_connection()
            cur = conn.cursor()
            try:
                cur.execute("SELECT ad FROM ogrenciler WHERE tc = %s", (y_tc,))
                mevcut_kisi = cur.fetchone()
                
                if mevcut_kisi:
                    st.error(f"🚨 HATA: {y_tc} TC numarası zaten '{mevcut_kisi[0]}' adına kayıtlı!")
                else:
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
            except Exception as e:
                conn.rollback()
                st.error(f"Sistemsel Hata: {e}")
            finally:
                cur.close()

# ----------------- 2. DETAYLI TAHSİLAT VE ÖĞRENCİ KARTI -----------------
st.divider()
st.subheader("💰 Tahsilat İşlemi ve Öğrenci Kartı")

arama = st.text_input("🔍 Öğrenci Bul (Ad veya TC giriniz)")

if arama:
    ogr_df = veri_getir("SELECT * FROM ogrenciler WHERE ad ILIKE %s OR tc LIKE %s", (f"%{arama}%", f"%{arama}%"))
    
    if not ogr_df.empty:
        secilen_ogr_id = int(ogr_df.iloc[0]['id'])
        secilen_ogr_ad = ogr_df.iloc[0]['ad']
        secilen_ogr_tc = ogr_df.iloc[0]['tc'] 
        
        kart_df = veri_getir("""
            SELECT id as islem_no, vade, tutar, durum, odeme_yontemi, makbuz_no 
            FROM odemeler 
            WHERE ogrenci_id = %s 
            ORDER BY vade ASC
        """, (secilen_ogr_id,))
        
        # ESKİ KAYITLAR İÇİN GÜVENLİK YAMASI (NaN Hatalarını Önler)
        kart_df['odeme_yontemi'] = kart_df['odeme_yontemi'].fillna("Belirtilmemiş")
        kart_df['makbuz_no'] = kart_df['makbuz_no'].fillna("Eski_Kayit")
        
        t_borc = kart_df['tutar'].sum()
        t_odenen = kart_df[kart_df['durum'] == 'Ödendi']['tutar'].sum()
        t_kalan = t_borc - t_odenen
        
        st.markdown(f"### 📋 {secilen_ogr_ad} | TC: {secilen_ogr_tc}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Toplam Kayıt Bedeli", f"₺ {t_borc:,.2f}")
        m2.metric("Tahsil Edilen", f"₺ {t_odenen:,.2f}", delta_color="normal")
        m3.metric("Kalan Borç", f"₺ {t_kalan:,.2f}", delta="-₺ "+str(t_odenen))

        st.write("**Tüm Taksit ve İşlem Geçmişi:**")
        st.dataframe(kart_df, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

        # ----------------- YENİ ÖDEME ALMA BÖLÜMÜ -----------------
        bekleyenler = kart_df[kart_df['durum'] == 'Bekliyor']
        if not bekleyenler.empty:
            with st.container(border=True):
                st.write("#### 💵 Yeni Tahsilat Girişi")
                secenekler = bekleyenler.apply(lambda x: f"İşlem No: {x['islem_no']} | Vade: {x['vade']} | Tutar: ₺{x['tutar']}", axis=1).tolist()
                secim = st.selectbox("Tahsil edilecek taksiti seçin:", secenekler)
                
                islem_id = int(secim.split("İşlem No: ")[1].split(" |")[0])
                asil_tutar = float(bekleyenler[bekleyenler['islem_no'] == islem_id]['tutar'].values[0])
                
                c_yontem, c_tutar = st.columns(2)
                with c_yontem:
                    yontem = st.selectbox("Ödeme Yöntemi", ["Nakit", "Kredi Kartı", "Banka / Havale / EFT"])
                with c_tutar:
                    tutar_giris = st.number_input("Kasaya Giren Miktar", min_value=0.0, max_value=asil_tutar, value=asil_tutar, step=500.0)
                    st.markdown(f"**💰 Net Tutar:** <span style='color: green; font-size: 16px;'>₺ {tutar_giris:,.2f}</span>", unsafe_allow_html=True)
                
                if st.button("Tahsilatı Kesinleştir ve Makbuz Üret", type="primary"):
                    yeni_makbuz_no = f"MKBZ-{datetime.now().strftime('%Y%m%d')}-{islem_id}"
                    
                    conn = get_connection()
                    cur = conn.cursor()
                    try:
                        if tutar_giris < asil_tutar:
                            cur.execute("UPDATE odemeler SET durum='Ödendi', tutar=%s, odeme_yontemi=%s, makbuz_no=%s WHERE id=%s", 
                                        (tutar_giris, yontem, yeni_makbuz_no, islem_id))
                            cur.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar) VALUES (%s, %s, %s)", 
                                        (secilen_ogr_id, bekleyenler[bekleyenler['islem_no'] == islem_id]['vade'].values[0], asil_tutar - tutar_giris))
                        else:
                            cur.execute("UPDATE odemeler SET durum='Ödendi', odeme_yontemi=%s, makbuz_no=%s WHERE id=%s", 
                                        (yontem, yeni_makbuz_no, islem_id))
                        
                        conn.commit()
                        st.session_state.goster_islem_id = islem_id # Makbuzu garantili bulmak için ID'yi hafızaya alıyoruz
                        st.success("Ödeme başarıyla işlendi!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Hata: {e}")
                    finally:
                        cur.close()
        else:
            st.success("Bu öğrencinin bekleyen borcu bulunmamaktadır.")

        # ----------------- GEÇMİŞ MAKBUZ GÖRÜNTÜLEME BÖLÜMÜ -----------------
        odenmisler = kart_df[kart_df['durum'] == 'Ödendi']
        if not odenmisler.empty:
            st.write("#### 🖨️ Makbuz Yazdır")
            
            # Seçim kutusu artık kırılmaz "İşlem No" tabanlı
            makbuz_secim = st.selectbox(
                "Görüntülemek istediğiniz işlemi seçin:", 
                odenmisler.apply(lambda x: f"İşlem No: {x['islem_no']} | {x['makbuz_no']} - Vade: {x['vade']} - ₺{x['tutar']} ({x['odeme_yontemi']})", axis=1).tolist()
            )
            
            # Seçilen işlemin ID'sini güvenli şekilde ayıkla
            secilen_islem_no = int(makbuz_secim.split("İşlem No: ")[1].split(" |")[0])
            makbuz_detay = odenmisler[odenmisler['islem_no'] == secilen_islem_no].iloc[0]
            
            # Yeni ödeme yapıldıysa otomatik o fişi göster
            if "goster_islem_id" in st.session_state:
                # Hafızadaki ID'yi kullanarak tam nokta atışı makbuzu bul
                makbuz_detay = odenmisler[odenmisler['islem_no'] == st.session_state.goster_islem_id].iloc[0]
                del st.session_state.goster_islem_id
                st.info("İşleminiz tamamlandı. Aşağıdan makbuzunuzu yazdırabilirsiniz.")

            # HTML Makbuz Şablonu
            st.markdown(f"""
            <div style="border: 2px dashed #666; padding: 30px; border-radius: 5px; background-color: #fafafa; color: black; max-width: 600px; margin: auto;">
                <h2 style="text-align: center; color: #333; margin-bottom: 5px;">TAHSİLAT MAKBUZU</h2>
                <p style="text-align: center; font-size: 14px; color: #777;">Makbuz No: {makbuz_detay['makbuz_no']}</p>
                <hr style="border: 1px solid #ccc;">
                <table style="width: 100%; margin-top: 15px;">
                    <tr><td style="padding: 5px;"><b>Öğrenci Adı:</b></td> <td>{secilen_ogr_ad}</td></tr>
                    <tr><td style="padding: 5px;"><b>TC Kimlik No:</b></td> <td>{secilen_ogr_tc}</td></tr>
                    <tr><td style="padding: 5px;"><b>İşlem Tarihi (Vade):</b></td> <td>{makbuz_detay['vade'].strftime('%d.%m.%Y')}</td></tr>
                    <tr><td style="padding: 5px;"><b>Ödeme Yöntemi:</b></td> <td>{makbuz_detay['odeme_yontemi']}</td></tr>
                </table>
                <div style="margin-top: 20px; padding: 15px; background-color: #e8f5e9; border-left: 5px solid #4caf50;">
                    <h3 style="margin: 0; color: #2e7d32;">Tahsil Edilen Tutar: ₺ {makbuz_detay['tutar']:,.2f}</h3>
                </div>
                <br>
                <table style="width: 100%;">
                    <tr>
                        <td style="text-align: left;">Teslim Eden<br><br>________________</td>
                        <td style="text-align: right;">Teslim Alan (Kasa)<br><br>________________</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)
            
    else:
        st.warning("Öğrenci bulunamadı. Lütfen ismi veya TC'yi doğru girdiğinizden emin olun.")

# ----------------- 3. GÜNLÜK TAKİP -----------------
st.divider()
st.subheader("📅 Günlük Ödeme Takip Ekranı")
df_takip = veri_getir("""
    SELECT o.vade, ogr.ad, ogr.tc, o.tutar, o.durum 
    FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
    WHERE o.vade <= %s AND o.durum = 'Bekliyor' ORDER BY o.vade ASC
""", (date.today(),))

if not df_takip.empty:
    st.dataframe(df_takip, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
else:
    st.success("Harika! Günü gelen veya geciken bekleyen ödeme yok.")
    # ----------------- TEHLİKELİ BÖLGE: SIFIRLAMA BUTONU -----------------
st.divider()
st.error("⚠️ SİSTEM SIFIRLAMA (SADECE TEST İÇİN)")
if st.button("🚨 TÜM VERİTABANINI SİLK BAŞTAN SIFIRLA"):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # CASCADE komutu, birbirine bağlı tabloları (öğrenci silinince taksitlerini de) kökten temizler
        cur.execute("DROP TABLE IF EXISTS odemeler CASCADE;")
        cur.execute("DROP TABLE IF EXISTS ogrenciler CASCADE;")
        conn.commit()
        st.success("Tebrikler! Veritabanı fabrikadan ilk çıktığı güne döndü. Lütfen sayfayı yenileyin (F5).")
    except Exception as e:
        st.error(f"Hata: {e}")
    finally:
        cur.close()
