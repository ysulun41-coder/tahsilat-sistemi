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

# ----------------- FİNANSAL KOKPİT (İLK GİRİŞ EKRANI) -----------------
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
                if cur.fetchone():
                    st.error("🚨 HATA: Bu TC numarası zaten kayıtlı!")
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
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                conn.rollback()
                st.error(f"Sistemsel Hata: {e}")
            finally:
                cur.close()

# ----------------- 2. DETAYLI TAHSİLAT VE ÖĞRENCİ KARTI -----------------
st.divider()
st.subheader("💰 Tahsilat İşlemi ve Öğrenci Kartı")

# YENİ NESİL AKILLI ARAMA (Yazarken Filtreler)
tum_ogrenciler = veri_getir("SELECT id, ad, tc FROM ogrenciler ORDER BY ad ASC")

if not tum_ogrenciler.empty:
    # Öğrencileri listeye dönüştür (Örn: "Ahmet Yılmaz | TC: 123... | ID:5")
    ogrenci_listesi = tum_ogrenciler.apply(lambda x: f"{x['ad']} | TC: {x['tc']} | ID:{x['id']}", axis=1).tolist()
    
    secilen_metin = st.selectbox(
        "🔍 Öğrenci Bul (İsim veya TC yazarak arayabilirsiniz):", 
        ["-- Lütfen Öğrenci Seçin --"] + ogrenci_listesi
    )

    if secilen_metin != "-- Lütfen Öğrenci Seçin --":
        # Seçilen metinden gizli ID'yi çekiyoruz
        secilen_ogr_id = int(secilen_metin.split("ID:")[1])
        secilen_ogr_ad = secilen_metin.split(" |")[0]
        secilen_ogr_tc = secilen_metin.split("TC: ")[1].split(" |")[0]
        
        kart_df = veri_getir("""
            SELECT id as islem_no, vade, tutar, durum, odeme_yontemi, makbuz_no 
            FROM odemeler 
            WHERE ogrenci_id = %s 
            ORDER BY vade ASC
        """, (secilen_ogr_id,))
        
        kart_df['odeme_yontemi'] = kart_df['odeme_yontemi'].fillna("-")
        kart_df['makbuz_no'] = kart_df['makbuz_no'].fillna("-")
        
        t_borc = kart_df['tutar'].sum()
        t_odenen = kart_df[kart_df['durum'] == 'Ödendi']['tutar'].sum()
        t_kalan = t_borc - t_odenen
        
        st.markdown(f"### 📋 {secilen_ogr_ad} | TC: {secilen_ogr_tc}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Kişi Toplam Kayıt Bedeli", f"₺ {t_borc:,.2f}")
        m2.metric("Kişiden Tahsil Edilen", f"₺ {t_odenen:,.2f}", delta_color="normal")
        m3.metric("Kişinin Kalan Borcu", f"₺ {t_kalan:,.2f}", delta="-₺ "+str(t_odenen))

        st.write("**Tüm Taksit ve İşlem Geçmişi:**")
        st.dataframe(kart_df, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)

        # ÖDEME ALMA BÖLÜMÜ
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
                        st.session_state.goster_islem_id = islem_id
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

        # MAKBUZ GÖRÜNTÜLEME
        odenmisler = kart_df[kart_df['durum'] == 'Ödendi']
        if not odenmisler.empty:
            st.write("#### 🖨️ Makbuz Yazdır")
            makbuz_secim = st.selectbox(
                "Görüntülemek istediğiniz işlemi seçin:", 
                odenmisler.apply(lambda x: f"İşlem No: {x['islem_no']} | {x['makbuz_no']} - Vade: {x['vade']} - ₺{x['tutar']} ({x['odeme_yontemi']})", axis=1).tolist()
            )
            secilen_islem_no = int(makbuz_secim.split("İşlem No: ")[1].split(" |")[0])
            makbuz_detay = odenmisler[odenmisler['islem_no'] == secilen_islem_no].iloc[0]
            
            if "goster_islem_id" in st.session_state:
                makbuz_detay = odenmisler[odenmisler['islem_no'] == st.session_state.goster_islem_id].iloc[0]
                del st.session_state.goster_islem_id
                st.info("İşleminiz tamamlandı. Aşağıdan makbuzunuzu yazdırabilirsiniz.")

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
    st.info("Sistemde henüz kayıtlı öğrenci bulunmuyor. Yeni kayıt oluşturabilirsiniz.")

# ----------------- 3. GÜNLÜK TAKİP -----------------
# ----------------- 3. GÜNLÜK TAKİP -----------------
st.divider()
st.subheader("📅 Günlük Ödeme Takip Ekranı")
st.info("Bu liste sadece bugün ödemesi olanları ve ödemesi gecikenleri gösterir.")

# Sorguyu güncelledik: Sadece bugüne eşit veya bugünden küçük (vadesi geçmiş) olanlar
df_takip = veri_getir("""
    SELECT o.vade, ogr.ad, ogr.tc, o.tutar, o.durum 
    FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
    WHERE o.vade <= %s AND o.durum = 'Bekliyor' 
    ORDER BY o.vade ASC
""", (date.today(),))

if not df_takip.empty:
    st.dataframe(df_takip, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
else:
    st.success("Harika! Bugünün tüm tahsilatları tamamlanmış veya bekleyen gecikmiş ödeme yok.")


# ----------------- SİSTEM YÖNETİCİSİ ARAÇLARI (GEÇİCİ) -----------------
st.divider()
with st.expander("⚙️ Sistem Yöneticisi Araçları (Hata Korumalı Aktarım)", expanded=False):
    st.write("#### 📂 'Hiloş Tahsilat' Şablonu ile Toplu Veri Aktarımı")
    
    yuklenen_dosya = st.file_uploader("Orijinal Excel veya CSV Dosyanızı Yükleyin", type=["xlsx", "xls", "csv"])
    
    if st.button("🚀 Excel Verilerini Sisteme Aktar"):
        if yuklenen_dosya is not None:
            conn = None
            try:
                # 1. DOSYA OKUMA
                if yuklenen_dosya.name.endswith('.csv'):
                    try:
                        df_excel = pd.read_csv(yuklenen_dosya, dtype=str)
                        if len(df_excel.columns) == 1: 
                            yuklenen_dosya.seek(0)
                            df_excel = pd.read_csv(yuklenen_dosya, sep=';', dtype=str) 
                    except:
                        yuklenen_dosya.seek(0)
                        df_excel = pd.read_csv(yuklenen_dosya, sep=';', dtype=str)
                else:
                    df_excel = pd.read_excel(yuklenen_dosya, dtype=str)
                
                df_excel.columns = df_excel.columns.str.strip()
                aranan_sutun = 'Öğr. TC Kimlik No'
                
                if aranan_sutun not in df_excel.columns:
                    st.error(f"🚨 HATA: Dosyada '{aranan_sutun}' sütunu bulunamadı!")
                    st.stop()
                
                # Boş satırları temizle
                df_excel = df_excel.dropna(subset=[aranan_sutun, 'Öğrencinin Adı Soyadı'])
                
                conn = get_connection()
                cur = conn.cursor()
                islem_sayisi = 0
                
                progress_bar = st.progress(0)
                total_rows = len(df_excel)
                
                for index, row in df_excel.iterrows():
                    # --- Veri Temizliği ---
                    tc_no = str(row[aranan_sutun]).strip().replace('.0', '')
                    ad = str(row['Öğrencinin Adı Soyadı']).strip()
                    
                    # TARİH KONTROLÜ (NaT Hatasını Önler)
                    vade_ham = row.get('Vade Tarihi')
                    vade_tarihi = pd.to_datetime(vade_ham, errors='coerce')
                    
                    if pd.isna(vade_tarihi):
                        # Eğer tarih boşsa bugün olarak ata veya o satırı atlamak isterseniz 'continue' kullanın
                        vade_tarihi = date.today()
                    else:
                        vade_tarihi = vade_tarihi.date()
                        
                    # TUTAR KONTROLÜ (NaN Hatasını Önler)
                    tutar_ham = str(row.get('Ödeme Tutarı', '0')).replace(',', '.').replace('₺', '').strip()
                    try:
                        tutar = float(tutar_ham)
                        if pd.isna(tutar): tutar = 0.0
                    except:
                        tutar = 0.0
                    
                    durum_ham = str(row.get('Ödeme Gerçekleşti mi?', '')).strip().lower()
                    durum = 'Ödendi' if durum_ham in ['evet', 'ödendi', 'e', 'true', '1', 'var'] else 'Bekliyor'
                    
                    # --- Veritabanı İşlemi ---
                    cur.execute("""
                        INSERT INTO ogrenciler (ad, veli, telefon, tc) 
                        VALUES (%s, '-', '-', %s) 
                        ON CONFLICT (tc) DO UPDATE SET ad=EXCLUDED.ad 
                        RETURNING id
                    """, (ad, tc_no))
                    ogr_id = cur.fetchone()[0]
                    
                    cur.execute("""
                        INSERT INTO odemeler (ogrenci_id, vade, tutar, durum, odeme_yontemi, makbuz_no) 
                        VALUES (%s, %s, %s, %s, 'Aktarım', 'Excel_Aktarim')
                    """, (ogr_id, vade_tarihi, tutar, durum))
                    
                    islem_sayisi += 1
                    progress_bar.progress(int((islem_sayisi / total_rows) * 100))
                
                conn.commit()
                st.success(f"🎉 {islem_sayisi} adet işlem başarıyla aktarıldı!")
                st.rerun()
                
            except Exception as e:
                if conn is not None: conn.rollback()
                st.error(f"🚨 Aktarım Hatası: {e}")
            finally:
                if 'cur' in locals(): cur.close()

st.write("---")
    st.write("#### ⚠️ Sistemi Sıfırla")
    if st.button("🚨 TÜM VERİTABANINI SİLK BAŞTAN SIFIRLA"):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS odemeler CASCADE;")
            cur.execute("DROP TABLE IF EXISTS ogrenciler CASCADE;")
            conn.commit()
            st.success("Veritabanı sıfırlandı. Lütfen sayfayı yenileyin (F5).")
        except Exception as e:
            if conn is not None:
                conn.rollback()
            st.error(f"Hata: {e}")
        finally:
            if 'cur' in locals():
                cur.close()


