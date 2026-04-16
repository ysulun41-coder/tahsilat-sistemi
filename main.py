import streamlit as st
import pandas as pd
from datetime import date, timedelta
import os

st.set_page_config(page_title="Tahsilat Sistemi", layout="wide")

st.title("🎓 Tahsilat Sistemi")

# =========================
# DOSYALAR
# =========================
ogr_dosya = "ogrenciler.csv"
plan_dosya = "odeme_plani.csv"

# =========================
# ÖĞRENCİ YÜKLE
# =========================
if os.path.exists(ogr_dosya):
    df_ogr = pd.read_csv(ogr_dosya)
else:
    df_ogr = pd.DataFrame(columns=["Ogrenci", "Veli", "Telefon"])

# =========================
# PLAN YÜKLE
# =========================
if os.path.exists(plan_dosya):
    df_plan = pd.read_csv(plan_dosya)
else:
    df_plan = pd.DataFrame(columns=["Ogrenci", "Veli", "Vade", "Tutar", "Durum"])

# =========================
# TARİH FORMATI DÜZELT
# =========================
if not df_plan.empty:
    df_plan["Vade"] = pd.to_datetime(df_plan["Vade"], errors="coerce")

# =========================
# DASHBOARD
# =========================
st.subheader("📊 Genel Durum")

if not df_plan.empty:

    toplam_borc = df_plan["Tutar"].sum()
    tahsil_edilen = df_plan[df_plan["Durum"] == "Odendi"]["Tutar"].sum()
    kalan_borc = df_plan[df_plan["Durum"] != "Odendi"]["Tutar"].sum()

    geciken = df_plan[
        (df_plan["Durum"] != "Odendi") &
        (df_plan["Vade"] < pd.to_datetime(date.today()))
    ]["Tutar"].sum()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("💰 Toplam Borç", f"{toplam_borc:,.0f} TL")
    col2.metric("💵 Tahsil Edilen", f"{tahsil_edilen:,.0f} TL")
    col3.metric("📉 Kalan Borç", f"{kalan_borc:,.0f} TL")
    col4.metric("🔴 Geciken", f"{geciken:,.0f} TL")

# =========================
# ÖĞRENCİ EKLE
# =========================
st.subheader("👨‍🎓 Öğrenci Ekle")

ogrenci = st.text_input("Öğrenci Adı")
veli = st.text_input("Veli Adı")
telefon = st.text_input("Telefon")

if st.button("Öğrenci Kaydet"):
    if ogrenci != "":
        yeni = pd.DataFrame([[ogrenci, veli, telefon]], columns=df_ogr.columns)
        df_ogr = pd.concat([df_ogr, yeni], ignore_index=True)
        df_ogr.to_csv(ogr_dosya, index=False)
        st.success("Öğrenci eklendi!")
    else:
        st.warning("Öğrenci adı boş olamaz")

# =========================
# SÖZLEŞME OLUŞTUR
# =========================
st.subheader("📄 Sözleşme Oluştur")

if not df_ogr.empty:

    ogrenci_sec = st.selectbox("Öğrenci Seç", df_ogr["Ogrenci"])

    toplam = st.number_input("Toplam Borç", min_value=0)
    taksit = st.number_input("Taksit Sayısı", min_value=1)

    ilk_tarih = st.date_input("İlk Ödeme Tarihi", value=date.today())

    if st.button("Plan Oluştur"):

        tutar = toplam / taksit

        for i in range(int(taksit)):

            vade = ilk_tarih + timedelta(days=30 * i)

            yeni = pd.DataFrame(
                [[ogrenci_sec, "", vade, tutar, "Bekliyor"]],
                columns=df_plan.columns
            )

            df_plan = pd.concat([df_plan, yeni], ignore_index=True)

        df_plan.to_csv(plan_dosya, index=False)

        st.success("Taksit planı oluşturuldu!")

# =========================
# TAHSİLAT
# =========================
st.subheader("💰 Tahsilat")

if not df_ogr.empty:

    ogr_sec = st.selectbox("Tahsilat Öğrenci", df_ogr["Ogrenci"], key="tahsilat")

    ogr_borclar = df_plan[
        (df_plan["Ogrenci"] == ogr_sec) &
        (df_plan["Durum"] != "Odendi")
    ]

    st.write("📋 Bekleyen Taksitler")
    st.write(ogr_borclar)

    if not ogr_borclar.empty:

        sec_index = st.selectbox("Ödenecek Taksit", ogr_borclar.index)

        if st.button("Ödeme Al"):
            df_plan.loc[sec_index, "Durum"] = "Odendi"
            df_plan.to_csv(plan_dosya, index=False)
            st.success("Ödeme alındı!")

# =========================
# BUGÜN
# =========================
st.subheader("🟡 Bugün Tahsilat")

bugun = df_plan[
    (df_plan["Vade"] == pd.to_datetime(date.today())) &
    (df_plan["Durum"] != "Odendi")
]

st.write(bugun)

# =========================
# GECİKEN
# =========================
st.subheader("🔴 Gecikenler")

geciken = df_plan[
    (df_plan["Vade"] < pd.to_datetime(date.today())) &
    (df_plan["Durum"] != "Odendi")
]

st.write(geciken)

# =========================
# WHATSAPP MESAJ
# =========================
st.subheader("📲 WhatsApp Hatırlatma")

if not df_plan.empty:

    # sadece ödenmemişler
    bekleyen = df_plan[df_plan["Durum"] != "Odendi"]

    if not bekleyen.empty:

        sec_index = st.selectbox("Kişi Seç", bekleyen.index, key="wp")

        secilen = bekleyen.loc[sec_index]

        ogr = secilen["Ogrenci"]
        tutar = secilen["Tutar"]
        vade = secilen["Vade"]

        mesaj = f"""
Sayın veli,

{ogr} adına {tutar:,.0f} TL tutarındaki ödemenizin vadesi {vade.date()} tarihindedir.

Bilgilerinize sunarız.
"""

        st.text_area("Mesaj", mesaj, height=150)