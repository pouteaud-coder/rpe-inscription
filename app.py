import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib
import io

# TENTATIVE D'IMPORTATION SÉCURISÉE
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import xlsxwriter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- STYLE CSS ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; color: #31333F; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-orange { background-color: #fff3e0 !important; color: #ef6c00 !important; border-color: #ffe0b2 !important; }
    .alerte-rouge { background-color: #d32f2f !important; color: white !important; border-color: #b71c1c !important; }
    .liste-inscrits { font-size: 0.95rem !important; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- FONCTIONS UTILITAIRES ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    return f"#{hash_object.hexdigest()[:6]}"

def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

def format_date_fr_complete(date_obj):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str): date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
    return f"**{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}**"

# --- INITIALISATION ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())
res_lieux = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute()
liste_lieux = [l['nom'] for l in res_lieux.data]

# --- NAVIGATION ---
st.sidebar.title("Menu")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | {statut_p}"):
                for i in res_ins.data:
                    st.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} ({i['nb_enfants']} enf.)")
                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                    st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    if not PDF_AVAILABLE or not EXCEL_AVAILABLE:
        st.warning("⚠️ Les fonctions d'export (PDF/Excel) sont en cours d'installation sur le serveur. Revenez dans 2 minutes.")
    
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    with t1:
        st.info("Liste des inscriptions par personne.")
        # ... (Logique identique à la version précédente)
    with t2:
        st.info("Liste des ateliers et inscrits.")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    st.header("🔐 Espace Administrateur")
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        st.success("Accès autorisé")
        # ... (Logique de gestion des adhérents et lieux)
    else:
        st.info("Veuillez entrer le code secret pour accéder aux paramètres.")
