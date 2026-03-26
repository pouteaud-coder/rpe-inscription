import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib
import io
from fpdf import FPDF # Nouvelle bibliothèque pour le PDF

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- SYSTÈME DE COULEURS DYNAMIQUES PAR LIEU ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    hex_hash = hash_object.hexdigest()
    return f"#{hex_hash[:6]}"

# --- STYLE CSS ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .horaire-text { font-size: 0.9rem; color: #666; font-weight: 400; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; color: #31333F; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-orange { background-color: #fff3e0 !important; color: #ef6c00 !important; border-color: #ffe0b2 !important; }
    .alerte-rouge { background-color: #d32f2f !important; color: white !important; border-color: #b71c1c !important; }
    .separateur-atelier { border: 0; border-top: 1px solid #eee; margin: 15px 0; }
    .container-inscrits { margin-top: -8px; padding-top: 0; margin-bottom: 5px; }
    .liste-inscrits { font-size: 0.95rem !important; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
    .nb-enfants-focus { color: #2e7d32; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- FONCTIONS GÉNÉRATION EXPORT ---

def generate_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, title, ln=True, align='C')
    pdf.ln(10)
    
    # En-têtes
    pdf.set_font("Arial", "B", 10)
    cols = df.columns.tolist()
    for col in cols:
        pdf.cell(38, 10, col, 1)
    pdf.ln()
    
    # Données
    pdf.set_font("Arial", "", 9)
    for _, row in df.iterrows():
        for val in row:
            pdf.cell(38, 10, str(val), 1)
        pdf.ln()
    return pdf.output(dest="S").encode("latin-1")

def get_excel_download(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Export')
    return output.getvalue()

# --- FONCTIONS UTILITAIRES ---
def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    res = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{res}**" if gras else res

# --- INITIALISATION ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

res_lieux = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute()
liste_lieux = [l['nom'] for l in res_lieux.data]

# --- NAVIGATION ---
st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
if menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation & Bilans")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data_u = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        
        export_adh = []
        curr_u = ""
        for i in data_u.data:
            nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom_u != curr_u:
                st.markdown(f'<div style="color:#1b5e20; border-bottom:2px solid #1b5e20; padding-top:15px; margin-bottom:8px; font-weight:bold; font-size:1.2rem;">{nom_u}</div>', unsafe_allow_html=True)
                curr_u = nom_u
            at = i['ateliers']
            st.write(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} ({at['lieux']['nom']}) **({i['nb_enfants']} enf.)**")
            export_adh.append({"Adhérent": nom_u, "Date": at['date_atelier'], "Atelier": at['titre'], "Lieu": at['lieux']['nom'], "Enfants": i['nb_enfants']})

        if export_adh:
            df_a = pd.DataFrame(export_adh)
            c1, c2 = st.columns(2)
            c1.download_button("📥 Excel (Par Adhérent)", get_excel_download(df_a), "RPE_Adherents.xlsx")
            c2.download_button("📄 PDF (Par Adhérent)", generate_pdf(df_a, "Récapitulatif par Adhérent"), "RPE_Adherents.pdf")

    with t2:
        c_f1, c_f2, c_f3 = st.columns([1, 1, 1])
        d_start = c_f1.date_input("Du", date.today(), format="DD/MM/YYYY")
        d_end = c_f2.date_input("Au", d_start + timedelta(days=30), format="DD/MM/YYYY")
        f_lieu = c_f3.multiselect("Lieu(x)", liste_lieux)
        
        query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end))
        if f_lieu:
            ids_l = [l['id'] for l in res_lieux.data if l['nom'] in f_lieu]
            query = query.in_("lieu_id", ids_l)
        
        ats_raw = query.order("date_atelier").execute()
        export_at = []
            
        for index, a in enumerate(ats_raw.data):
            c_l = get_color(a['lieux']['nom'])
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            t_ad = len(ins_at.data); t_en = sum([p['nb_enfants'] for p in ins_at.data])
            t_occ = t_ad + t_en; rest = a['capacite_max'] - t_occ
            
            classe_alerte = "alerte-rouge" if rest <= 0 else ("alerte-orange" if rest <= 3 else "")
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> | <span class='compteur-badge {classe_alerte}'>🏁 {rest} pl. libres</span>", unsafe_allow_html=True)
            
            for p in sorted(ins_at.data, key=lambda x: (x['adherents']['nom'])):
                n_f = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                st.markdown(f'<span class="liste-inscrits">• {n_f} ({p["nb_enfants"]} enf.)</span>', unsafe_allow_html=True)
                export_at.append({"Date": a['date_atelier'], "Lieu": a['lieux']['nom'], "Adhérent": n_f, "Enfants": p['nb_enfants']})
            if index < len(ats_raw.data) - 1: st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)

        if export_at:
            df_at = pd.DataFrame(export_at)
            st.write("---")
            c1, c2 = st.columns(2)
            c1.download_button("📥 Excel (Par Atelier)", get_excel_download(df_at), "RPE_Ateliers.xlsx")
            c2.download_button("📄 PDF (Par Atelier)", generate_pdf(df_at, "Liste des Inscriptions par Atelier"), "RPE_Ateliers.pdf")

# (Les autres sections restent identiques)
