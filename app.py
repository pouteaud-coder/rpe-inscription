import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib
import io

# --- IMPORTATIONS SÉCURISÉES POUR LES EXPORTS ---
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

# --- STYLE CSS (RESTAURÉ) ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .horaire-text { font-size: 0.9rem; color: #666; font-weight: 400; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-orange { background-color: #fff3e0 !important; color: #ef6c00 !important; border-color: #ffe0b2 !important; }
    .alerte-rouge { background-color: #d32f2f !important; color: white !important; border-color: #b71c1c !important; }
    .separateur-atelier { border: 0; border-top: 1px solid #eee; margin: 15px 0; }
    .liste-inscrits { font-size: 0.95rem !important; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
    .nb-enfants-focus { color: #2e7d32; font-weight: 600; }
    .stButton button { border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---
def get_color(nom_lieu):
    hash_obj = hashlib.md5(str(nom_lieu).upper().strip().encode())
    return f"#{hash_obj.hexdigest()[:6]}"

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    res = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{res}**" if gras else res

def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

# --- FONCTIONS EXPORT ---
def export_pdf(df, title):
    if not PDF_READY: return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", "B", 10)
    for col in df.columns: pdf.cell(45, 10, col.encode('latin-1', 'replace').decode('latin-1'), 1)
    pdf.ln()
    pdf.set_font("Arial", "", 9)
    for _, row in df.iterrows():
        for item in row: pdf.cell(45, 10, str(item).encode('latin-1', 'replace').decode('latin-1'), 1)
        pdf.ln()
    return pdf.output(dest="S").encode("latin-1")

# --- INITIALISATION ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())
res_lieux = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute()
dict_lieux = {l['nom']: l['id'] for l in res_lieux.data}
liste_lieux = list(dict_lieux.keys())

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_p = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    if user_p != "Choisir...":
        ats = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        for at in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + i['nb_enfants']) for i in ins.data])
            rest = at['capacite_max'] - total_occ
            statut = f"✅ {rest} pl. libres" if rest > 0 else "🚨 COMPLET"
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | {statut}"):
                for i in ins.data:
                    st.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} **({i['nb_enfants']} enf.)**")
                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                nbe = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c3.button("Valider", key=f"b_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at['id'], "nb_enfants": nbe}).execute()
                        st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation & Bilans")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    with t1:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom)), adherents(nom, prenom)").in_("adherent_id", ids).execute()
        export_adh = []
        for i in data.data:
            at = i['ateliers']
            st.write(f"**{i['adherents']['prenom']} {i['adherents']['nom']}** : {format_date_fr_complete(at['date_atelier'])} ({at['lieux']['nom']})")
            export_adh.append({"Adhérent": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": at['date_atelier'], "Atelier": at['titre'], "Lieu": at['lieux']['nom']})
        if export_adh and PDF_READY:
            st.download_button("📄 PDF Adhérents", export_pdf(pd.DataFrame(export_adh), "Récapitulatif Adhérents"), "Recap_Adherents.pdf")

    with t2:
        c1, c2, c3 = st.columns(3)
        d_s = c1.date_input("Du", date.today())
        d_e = c2.date_input("Au", d_s + timedelta(days=30))
        f_l = c3.multiselect("Lieux", liste_lieux)
        query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_s)).lte("date_atelier", str(d_e))
        if f_l: query = query.in_("lieu_id", [dict_lieux[name] for name in f_l])
        ats_r = query.order("date_atelier").execute()
        export_at = []
        for a in ats_r.data:
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            t_ad = len(ins_at.data); t_en = sum([p['nb_enfants'] for p in ins_at.data])
            rest = a['capacite_max'] - (t_ad + t_en)
            clr = "alerte-rouge" if rest <= 0 else ("alerte-orange" if rest <= 3 else "")
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | <span class='lieu-badge' style='background-color:{get_color(a['lieux']['nom'])}'>{a['lieux']['nom']}</span> <span class='compteur-badge {clr}'>🏁 {rest} libres</span>", unsafe_allow_html=True)
            for p in ins_at.data:
                n = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                st.markdown(f'<span class="liste-inscrits">• {n} ({p["nb_enfants"]} enf.)</span>', unsafe_allow_html=True)
                export_at.append({"Date": a['date_atelier'], "Lieu": a['lieux']['nom'], "Inscrit": n, "Enfants": p['nb_enfants']})
        if export_at:
            st.download_button("📥 Excel Bilan", pd.DataFrame(export_at).to_csv(index=False).encode('utf-8'), "Bilan.csv")

# ==========================================
# SECTION 🔐 ADMINISTRATION (RESTAURÉE)
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t_ad1, t_ad2, t_ad3 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Paramètres"])
        with t_ad1:
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                c1, c2 = st.columns(2)
                start = c1.date_input("Début", date.today())
                end = c2.date_input("Fin", start + timedelta(days=7))
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                if st.button("📊 Préparer la liste"):
                    tmp = []; curr = start; js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    while curr <= end:
                        if js_fr[curr.weekday()] in jours:
                            tmp.append({"Date": str(curr), "Titre": "Atelier Jeux", "Lieu": liste_lieux[0], "Capacité": 12})
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = tmp
                if st.session_state['at_list']:
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list']), use_container_width=True)
                    if st.button("💾 Enregistrer tout"):
                        for _, r in df_ed.iterrows():
                            l_id = dict_lieux[r['Lieu']]
                            supabase.table("ateliers").insert({"titre": r['Titre'], "date_atelier": r['Date'], "lieu_id": l_id, "capacite_max": r['Capacité'], "est_actif": True}).execute()
                        st.success("Ateliers créés !"); st.session_state['at_list'] = []; st.rerun()
        with t_ad2:
            with st.form("new_adh"):
                n = st.text_input("Nom"); p = st.text_input("Prénom")
                if st.form_submit_button("Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            for ad in res_adh.data: st.write(f"• {ad['prenom']} {ad['nom']}")
        with t_ad3:
            st.write("Gestion des lieux et horaires...")
    else: st.info("Saisissez le code secret.")
