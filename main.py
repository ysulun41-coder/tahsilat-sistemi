import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date

# Sayfa Ayarları
st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

# ----------------- VERİTABANI FONKSİYONLARI -----------------
def get_connection():
    return sqlite3.connect("data.db", check_same_thread=False)

def fix_database():
    conn = get_connection()
    cursor = conn.cursor()
    # Tabloları oluştur
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
    
    # İYİLEŞTİRME 3: Sessiz hata yutmak yerine PRAGMA ile sütun kontrolü
    cursor.execute("PRAGMA table_info(ogrenciler)")
    columns = [col[1] for col in cursor.fetchall()]
    if "tc" not in columns:
        cursor.execute("ALTER TABLE ogrenciler ADD COLUMN tc TEXT")
        
    conn.commit()
    conn.close()

fix_database()

# İYİLEŞTİRME 2: Tüm veriyi RAM'e almak yerine sadece gerekeni çeken fonksiyonlar
def get_gunluk_odemeler(hedef_tarih, kosul="bugun"):
    conn = get_connection()
    if kosul == "bugun":
        query = "SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, ogr.telefon, ogr.tc, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id WHERE o.vade = ? AND o.durum != 'Ödendi'"
    else: # geciken
        query = "SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, ogr.telefon, ogr.tc, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id WHERE o.vade < ? AND o.durum != 'Ödendi'"
    
    df = pd.read_sql(query, conn, params=(hedef_tarih,))
    conn.close()
    if not df.empty:
        df["vade"] = pd.to_datetime(df["vade"]).dt.date
    return df

def arama_yap(aranan):
    conn = get_connection()
    aranan_param = f"%{aranan}%"
    query = """
        SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, ogr.telefon, ogr.tc, o.vade, o.tutar, o.durum 
        FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id 
        WHERE o.durum != 'Ödendi' AND (ogr.ad LIKE ? OR ogr.id = ?)
    """
    df = pd.read_sql(query, conn, params=(aranan_param, aranan))
    conn.close()
    if not df.empty:
        df["vade"] = pd.to_datetime(df["vade"]).dt.date
    return df

# --- PARA BİRİMİ VE TARİH GÖRÜNÜM AYARLARI ---
sutun_ayarlar = {
    "tutar": st.column_config.NumberColumn("Tutar", format="₺ %.2f"),
    "vade": st.column_config.DateColumn("Vade Tarihi", format="DD.MM.YYYY")
}

st.title("📊 Tahsilat Sistemi")

# ----------------- YENİ ÖĞRENCİ KAYIT -----------------
with st.expander("👨‍🎓 Yeni Kayıt ve Borçlandırma", expanded=False):
    with st.form("kayit_formu", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            y_ad = st.text_input("Öğrenci Adı Soyadı")
            y_veli = st.text_input("Veli Adı")
            y_tc = st.text_input("TC Kimlik (Zorunlu)*") # TC Artık zorunlu
        with c2:
            y_tel = st.text_input("Telefon")
            y_borc = st.number_input("Toplam Borç (TL)", min_value=0.0, step=100.0, format="%.2f")
            y_taksit = st.number_input("Taksit Sayısı", min_value=1, step=1)
        
        y_tarih = st.date_input("İlk Taksit Tarihi", value=date.today())
        submit = st.form_submit_button("Kaydı Tamamla")

    if submit and y_ad and y_tc and y_borc > 0:
        conn = get_connection()
        cursor = conn.cursor()
        
        # İYİLEŞTİRME 1: İsim yerine TC ile mükerrer kayıt kontrolü
        cursor.execute("SELECT id FROM ogrenciler WHERE tc = ?", (y_tc.strip(),))
        mevcut = cursor.fetchone()
        
        if mevcut:
            ogr_id = mevcut[0]
        else:
            cursor.execute("INSERT INTO ogrenciler (ad, veli, telefon, tc) VALUES (?, ?, ?, ?)", (y_ad, y_veli, y_tel, y_tc))
            ogr_id = cursor.lastrowid
        
        taksit_tutari = y_borc / y_taksit
        for i in range(int(y_taksit)):
            vade = y_tarih + timedelta(days=30 * i)
            cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')", (ogr_id, vade, taksit_tutari))
        
        conn.commit()
        conn.close()
        st.success(f"{y_ad} başarıyla sisteme işlendi.")
        st.rerun()
    elif submit:
        st.error("Lütfen Öğrenci Adı, TC Kimlik ve geçerli bir Borç tutarı giriniz.")

# ----------------- GÜNLÜK VE GECİKEN TAKİP -----------------
p1, p2 = st.columns(2)
bugun = date.today()

with p1:
    st.subheader("📅 Bugünün Ödemeleri")
    b_liste = get_gunluk_odemeler(bugun, "bugun")
    if not b_liste.empty:
        st.dataframe(b_liste, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
    else:
        st.info("Bugün için ödeme yok.")

with p2:
    st.subheader("⏰ Geciken Ödemeler")
    g_liste = get_gunluk_odemeler(bugun, "geciken")
    if not g_liste.empty:
        st.dataframe(g_liste, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
    else:
        st.success("Gecikmiş ödeme bulunmuyor. Harika!")

# ----------------- TAHSİLAT GİRİŞİ -----------------
st.divider()
st.subheader("💰 Tahsilat Girişi")

if "arama_sayaci" not in st.session_state:
    st.session_state.arama_sayaci = 0

arama = st.text_input(
    "🔍 Öğrenci Ara (İsim veya Sabit Öğrenci ID giriniz)", 
    key=f"arama_kutusu_{st.session_state.arama_sayaci}", 
    placeholder="Örn: Oğuzhan veya 41"
)

# Aramaya göre SQL'den taze veri çekiyoruz
df_islem = arama_yap(arama.strip()) if arama else pd.DataFrame()

if not df_islem.empty:
    df_islem["etiket"] = df_islem.apply(lambda x: f"Öğr ID: {x['ogr_id']} | {x['ad']} | Vade: {x['vade']} | {x['tutar']:,.2f} TL (İşlem No: {x['islem_no']})", axis=1)
    secenekler = ["--- Lütfen Seçim Yapınız ---"] + df_islem["etiket"].tolist()
    secim = st.selectbox("Tahsil edilecek taksiti seçin:", secenekler)

    if secim != "--- Lütfen Seçim Yapınız ---":
        islem_id = int(secim.split("(İşlem No: ")[1].replace(")", ""))
        secilen_satir = df_islem[df_islem["islem_no"] == islem_id].iloc[0]
        secilen_ogr_id = int(secilen_satir["ogr_id"])

        # Seçilen kişinin finansal özetini anlık olarak SQL'den hesaplıyoruz
        conn = get_connection()
        kisi_ozet = pd.read_sql("SELECT tutar, durum FROM odemeler WHERE ogrenci_id = ?", conn, params=(secilen_ogr_id,))
        conn.close()
        
        t_planlanan = kisi_ozet["tutar"].sum()
        t_odenen = kisi_ozet[kisi_ozet["durum"] == "Ödendi"]["tutar"].sum()
        t_kalan = t_planlanan - t_odenen

        st.markdown(f"### 👤 {secilen_satir['ad']} - Finansal Durum")
        m1, m2, m3 = st.columns(3)
        m1.metric("Toplam Borç", f"₺ {t_planlanan:,.2f}")
        m2.metric("Toplam Tahsil Edilen", f"₺ {t_odenen:,.2f}")
        m3.metric("Kalan Net Borç", f"₺ {t_kalan:,.2f}")

        st.info(f"**Seçili Taksit Vadesi:** {secilen_satir['vade']} | **Asıl Tutar:** ₺ {secilen_satir['tutar']:,.2f}")
        
        asil_tutar = float(secilen_satir["tutar"])
        
        # İYİLEŞTİRME 4: Fazla Ödeme (Overpayment) engellendi. max_value asil_tutar olarak ayarlandı.
        tutar_giris = st.number_input(
            "Kasaya Girecek Miktar (TL)", 
            min_value=0.0, 
            max_value=asil_tutar, 
            value=asil_tutar, 
            step=50.0, 
            format="%.2f"
        )

        if st.button("Ödemeyi Onayla ve Kasaya İşle"):
            conn = get_connection()
            cursor = conn.cursor()
            
            # İYİLEŞTİRME 5: İşlem Bütünlüğü (Transaction ve Rollback) eklendi
            try:
                if tutar_giris < asil_tutar:
                    # Kısmi Ödeme
                    cursor.execute("UPDATE odemeler SET durum='Ödendi', tutar=? WHERE id=?", (tutar_giris, islem_id))
                    cursor.execute("INSERT INTO odemeler (ogrenci_id, vade, tutar, durum) VALUES (?, ?, ?, 'Bekliyor')", 
                                   (secilen_ogr_id, secilen_satir["vade"], asil_tutar - tutar_giris))
                    st.session_state.islem_mesaji = "Eksik tahsilat alındı, kalan tutar yeni taksit olarak eklendi."
                else:
                    # Tam Ödeme
                    cursor.execute("UPDATE odemeler SET durum='Ödendi' WHERE id=?", (islem_id,))
                    st.session_state.islem_mesaji = "Tahsilat başarıyla kaydedildi."
                
                conn.commit() # Her şey yolundaysa veritabanına kesin olarak yaz
                st.session_state.arama_sayaci += 1 
                
            except sqlite3.Error as e:
                conn.rollback() # Hata çıkarsa işlemleri geri al!
                st.session_state.islem_mesaji = f"🚨 İşlem sırasında kritik hata oluştu, işlem iptal edildi: {e}"
            finally:
                conn.close()
                st.rerun()

elif arama:
    st.info("Aramanıza uygun bekleyen taksit bulunamadı.")

if "islem_mesaji" in st.session_state:
    if "🚨" in st.session_state.islem_mesaji:
        st.error(st.session_state.islem_mesaji)
    else:
        st.success(st.session_state.islem_mesaji)
    del st.session_state.islem_mesaji

# ----------------- ARŞİV VE TÜM LİSTE -----------------
st.divider()

# Tabloları da anlık olarak SQL'den çekiyoruz
t1, t2 = st.tabs(["📋 Tüm Taksit Hareketleri", "📁 Ödenmiş Arşivi"])

with t1:
    conn = get_connection()
    df_tum = pd.read_sql("SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id ORDER BY o.vade", conn)
    if not df_tum.empty:
        df_tum["vade"] = pd.to_datetime(df_tum["vade"]).dt.date
        st.dataframe(df_tum, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
    conn.close()

with t2:
    conn = get_connection()
    df_arsiv = pd.read_sql("SELECT o.id as islem_no, ogr.id as ogr_id, ogr.ad, o.vade, o.tutar, o.durum FROM odemeler o JOIN ogrenciler ogr ON o.ogrenci_id = ogr.id WHERE o.durum = 'Ödendi' ORDER BY o.vade DESC", conn)
    if not df_arsiv.empty:
        df_arsiv["vade"] = pd.to_datetime(df_arsiv["vade"]).dt.date
        st.dataframe(df_arsiv, use_container_width=True, hide_index=True, column_config=sutun_ayarlar)
    else:
        st.write("Henüz ödeme kaydı yok.")
    conn.close()
