import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib
import io

# --- IMPORTATIONS SÉCURISÉES ---
try:
    from fpdf import FPDF
    PDF_READY = True
except:
    PDF_READY = False

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- CONNEXION SUPABASE ---
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- STYLE CSS ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-orange { background-color: #fff3e0 !important; color: #ef6c00 !important; }
    .alerte-rouge { background-color: #d32f2f !important; color: white !important; }
    .liste-inscrits { font-size: 0.95rem; color: #555; margin-left: 20px; display: block; }
    .stButton button { border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FONCTIONS UTILES ---
def get_color(nom_lieu):
    hash_obj = hashlib.md5(str(nom_lieu).upper().strip().encode())
    return f"#{hash_obj.hexdigest()[:6]}"

def format_date_fr(d):
    js = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    ms = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(d, str): d = datetime.strptime(d, '%Y-%m-%d')
    return f"**{js[d.weekday()]} {d.day} {ms[d.month-1]} {d.year}**"

def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

# --- EXPORTS ---
def export_excel(df):
    output = io.BytesIO()
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()
    except: return None

def export_pdf(df, title):
    if not PDF_READY: return None
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
        pdf.ln(5)
        pdf.set_font("Arial", "", 9)
        for _, row in df.iterrows():
            line = " | ".join([str(v) for v in row])
            pdf.cell(0, 8, line.encode('latin-1', 'replace').decode('latin-1'), ln=True)
        return pdf.output(dest="S").encode("latin-1")
    except: return None

# --- INITIALISATION DES DONNÉES ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())
res_lieux = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute()
liste_lieux = [l['nom'] for l in res_lieux.data]

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS (Restaurée)
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_p = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    if user_p != "Choisir...":
        ats = supabase.table("ateliers").select("*, lieux(nom)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        for at in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in ins.data])
            rest = at['capacite_max'] - occ
            status = "alerte-rouge" if rest <= 0 else ("alerte-orange" if rest <= 3 else "")
            
            with st.expander(f"{format_date_fr(at['date_atelier'])} — {at['titre']} ({rest} pl. libres)"):
                for i in ins.data:
                    st.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} ({i['nb_enfants']} enf.)")
                st.markdown("---")
                c1, c2, c3 = st.columns([2,1,1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                nbe = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c3.button("Valider", key=f"b_{at['id']}", type="primary"):
                    supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at['id'], "nb_enfants": nbe}).execute()
                    st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP (Restaurée)
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation & Bilans")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data_u = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom)), adherents(nom, prenom)").in_("adherent_id", ids).execute()
        df_adh = []
        for i in data_u.data:
            st.write(f"**{i['adherents']['prenom']} {i['adherents']['nom']}** : {format_date_fr(i['ateliers']['date_atelier'])} ({i['nb_enfants']} enf.)")
            df_adh.append({"Adhérent": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Lieu": i['ateliers']['lieux']['nom'], "Enfants": i['nb_enfants']})
        
        if df_adh:
            st.write("---")
            c1, c2 = st.columns(2)
            xlsx = export_excel(pd.DataFrame(df_adh))
            if xlsx: c1.download_button("📥 Excel", xlsx, "Suivi_Adherents.xlsx")
            pdf = export_pdf(pd.DataFrame(df_adh), "Récapitulatif Adhérents")
            if pdf: c2.download_button("📄 PDF", pdf, "Suivi_Adherents.pdf")

    with t2:
        c_d1, c_d2 = st.columns(2)
        d_start = c_d1.date_input("Du", date.today())
        d_end = c_d2.date_input("Au", d_start + timedelta(days=30))
        ats_r = supabase.table("ateliers").select("*, lieux(nom)").gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end)).execute()
        df_at = []
        for a in ats_r.data:
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in ins_at.data])
            st.markdown(f"**{format_date_fr(a['date_atelier'])}** | {a['lieux']['nom']} | Libres: {a['capacite_max'] - occ}")
            for p in ins_at.data:
                n = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                st.write(f" > {n} ({p['nb_enfants']} enf.)")
                df_at.append({"Date": a['date_atelier'], "Lieu": a['lieux']['nom'], "Inscrit": n, "Enfants": p['nb_enfants']})
        
        if df_at:
            st.write("---")
            xlsx_at = export_excel(pd.DataFrame(df_at))
            if xlsx_at: st.download_button("📥 Télécharger le bilan (Excel)", xlsx_at, "Bilan_Ateliers.xlsx")

# ==========================================
# SECTION 🔐 ADMINISTRATION (Restaurée)
# ==========================================
elif menu == "🔐 Administration":
    st.header("🔐 Espace Administration")
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t_ad1, t_ad2, t_ad3 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux"])
        
        with t_ad1:
            st.subheader("Générateur d'ateliers")
            c1, c2 = st.columns(2)
            d_gen = c1.date_input("Date de l'atelier", date.today())
            l_gen = c2.selectbox("Lieu", liste_lieux)
            titre = st.text_input("Nom de l'atelier", "Atelier Jeux")
            capa = st.number_input("Capacité max (Adul+Enf)", 1, 30, 12)
            if st.button("➕ Créer l'atelier"):
                supabase.table("ateliers").insert({"titre": titre, "date_atelier": str(d_gen), "lieu_id": [l['id'] for l in res_lieux.data if l['nom']==l_gen][0], "capacite_max": capa, "est_actif": True}).execute()
                st.success("Atelier créé !"); st.rerun()

        with t_ad2:
            st.subheader("Nouveau membre")
            with st.form("new_u"):
                n = st.text_input("Nom"); p = st.text_input("Prénom")
                if st.form_submit_button("Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute()
                    st.rerun()
            st.write("---")
            for ad in res_adh.data:
                st.write(f"• {ad['prenom']} {ad['nom']}")

        with t_ad3:
            st.subheader("Gestion des Lieux")
            for l in res_lieux.data:
                st.write(f"🏠 {l['nom']} (Capacité par défaut : {l.get('capacite_accueil', 'N/A')})")
    else:
        st.info("Veuillez saisir le code secret administrateur.")
