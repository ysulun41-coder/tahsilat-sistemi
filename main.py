# ----------------- SİSTEM YÖNETİCİSİ ARAÇLARI (GEÇİCİ) -----------------
st.divider()
with st.expander("⚙️ Sistem Yöneticisi Araçları (Özel Excel Yükleme & Sıfırlama)", expanded=False):
    st.write("#### 📂 'Hiloş Tahsilat' Şablonu ile Toplu Veri Aktarımı")
    
    yuklenen_dosya = st.file_uploader("Orijinal Excel veya CSV Dosyanızı Yükleyin", type=["xlsx", "xls", "csv"])
    
    if st.button("🚀 Excel Verilerini Sisteme Aktar"):
        if yuklenen_dosya is not None:
            conn = None # BAĞLANTIYI GÜVENLİ BAŞLAT (NameError hatasını çözer)
            try:
                # 1. DOSYA OKUMA GÜVENLİK ZIRHI
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
                
                # Başlıkları temizle
                df_excel.columns = df_excel.columns.str.strip()
                
                # GÜVENLİK KONTROLÜ
                aranan_sutun = 'Öğr. TC Kimlik No'
                if aranan_sutun not in df_excel.columns:
                    st.error(f"🚨 HATA: Dosyada '{aranan_sutun}' sütunu bulunamadı! Bulunan sütunlar şunlar: {', '.join(df_excel.columns)}")
                    st.stop()
                
                df_excel = df_excel.dropna(subset=[aranan_sutun])
                
                conn = get_connection()
                cur = conn.cursor()
                islem_sayisi = 0
                
                progress_bar = st.progress(0)
                total_rows = len(df_excel)
                
                for index, row in df_excel.iterrows():
                    tc_no = str(row[aranan_sutun]).strip().replace('.0', '')
                    ad = str(row['Öğrencinin Adı Soyadı']).strip()
                    veli = "-" 
                    telefon = "-"
                    
                    try:
                        vade_tarihi = pd.to_datetime(row['Vade Tarihi']).date()
                    except:
                        vade_tarihi = date.today()
                        
                    tutar_str = str(row['Ödeme Tutarı']).replace(',', '.').replace('₺', '').strip()
                    try:
                        tutar = float(tutar_str)
                    except:
                        tutar = 0.0
                    
                    durum_ham = str(row['Ödeme Gerçekleşti mi?']).strip().lower()
                    if durum_ham in ['evet', 'ödendi', 'e', 'true', '1', 'var']:
                        durum = 'Ödendi'
                    else:
                        durum = 'Bekliyor'
                    
                    cur.execute("""
                        INSERT INTO ogrenciler (ad, veli, telefon, tc) 
                        VALUES (%s, %s, %s, %s) 
                        ON CONFLICT (tc) DO UPDATE SET ad=EXCLUDED.ad 
                        RETURNING id
                    """, (ad, veli, telefon, tc_no))
                    ogr_id = cur.fetchone()[0]
                    
                    cur.execute("""
                        INSERT INTO odemeler (ogrenci_id, vade, tutar, durum, odeme_yontemi, makbuz_no) 
                        VALUES (%s, %s, %s, %s, 'Aktarım', 'Excel_Aktarim')
                    """, (ogr_id, vade_tarihi, tutar, durum))
                    
                    islem_sayisi += 1
                    progress_bar.progress(int((islem_sayisi / total_rows) * 100))
                
                conn.commit()
                st.success(f"🎉 MUHTEŞEM! {islem_sayisi} adet taksit işlemi sisteme hatasız aktarıldı.")
                st.info("Lütfen verilerin yüklenmesi için sayfayı yenileyin (F5).")
                
            except Exception as e:
                # EĞER BAĞLANTI VARSA İPTAL ET (NameError almamak için kalkanımız)
                if conn is not None:
                    conn.rollback()
                st.error(f"🚨 Aktarım Hatası: {e}")
            finally:
                if 'cur' in locals():
                    cur.close()
        else:
            st.warning("Lütfen önce dosya seçin.")

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
