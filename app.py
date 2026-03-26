import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import hashlib
import io
from fpdf import FPDF

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
    .liste-inscrits { font-size: 0.95rem; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
    .stButton button { border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    return f"#{hash_object.hexdigest()[:6]}"

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

# --- EXPORTS ---
def generate_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", "B", 9)
    col_width = 190 / len(df.columns)
    for col in df.columns: pdf.cell(col_width, 10, col.encode('latin-1', 'replace').decode('latin-1'), 1)
    pdf.ln()
    pdf.set_font("Arial", "", 8)
    for _, row in df.iterrows():
        for item in row: pdf.cell(col_width, 8, str(item).encode('latin-1', 'replace').decode('latin-1'), 1)
        pdf.ln()
    return pdf.output(dest="S").encode("latin-1")

def generate_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

# --- INITIALISATION DES DONNÉES ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
current_code = get_secret_code()

# Adhérents
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# Lieux
res_lieux = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute()
dict_lieux = {l['nom']: l['id'] for l in res_lieux.data}
liste_lieux = list(dict_lieux.keys())

# Horaires
res_h = supabase.table("horaires").select("*").eq("est_actif", True).order("libelle").execute()
dict_h = {h['libelle']: h['id'] for h in res_h.data}
liste_h = list(dict_h.keys())

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_p = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_p != "Choisir...":
        id_curr_adh = dict_adh[user_p]
        res_at = supabase.table("ateliers").select("*, lieux(*), horaires(*)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", at['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            rest = at['capacite_max'] - occ
            mon_ins = next((i for i in res_ins.data if i['adherent_id'] == id_curr_adh), None)
            
            h_lib = at['horaires']['libelle'] if at['horaires'] else "Heure non définie"
            statut = f"✅ {rest} pl. libres" if rest > 0 else "🚨 COMPLET"
            
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} ({h_lib}) — {at['titre']} | {statut}"):
                for i in sorted(res_ins.data, key=lambda x: x['adherents']['nom']):
                    c_txt, c_del = st.columns([0.85, 0.15])
                    c_txt.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} **({i['nb_enfants']} enf.)**")
                    if i['adherent_id'] == id_curr_adh:
                        if c_del.button("🗑️", key=f"del_{i['id']}"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()

                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                val_e = mon_ins['nb_enfants'] if mon_ins else 1
                c1.write(f"**{user_p}**")
                nb_e = c2.number_input("Enfants", 1, 10, val_e, key=f"e_{at['id']}")
                btn_txt = "Modifier" if mon_ins else "S'inscrire"
                
                if c3.button(btn_txt, key=f"btn_{at['id']}", type="primary"):
                    if mon_ins:
                        supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", mon_ins['id']).execute()
                    else:
                        if rest - (1 + nb_e) < 0: st.error("Plus de place")
                        else:
                            supabase.table("inscriptions").insert({"adherent_id": id_curr_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                    st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation & Bilans")
    t_a, t_b = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t_a:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).execute()
        df_adh = []
        for i in sorted(data.data, key=lambda x: (x['adherents']['nom'], x['ateliers']['date_atelier'])):
            nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            at = i['ateliers']
            st.write(f"**{nom}** : {format_date_fr_complete(at['date_atelier'])} ({at['horaires']['libelle'] if at['horaires'] else ''}) — {at['lieux']['nom']}")
            df_adh.append({"Adhérent": nom, "Date": at['date_atelier'], "Lieu": at['lieux']['nom'], "Enfants": i['nb_enfants']})
        if df_adh:
            st.download_button("📥 Excel", generate_excel(pd.DataFrame(df_adh)), "Recap.xlsx")

    with t_b:
        d1 = st.date_input("Du", date.today())
        d2 = st.date_input("Au", d1 + timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d1)).lte("date_atelier", str(d2)).order("date_atelier").execute()
        for a in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in ins.data]); rest = a['capacite_max'] - occ
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** ({a['horaires']['libelle'] if a['horaires'] else ''}) | {a['lieux']['nom']} | {rest} pl. libres")
            for p in ins.data: st.write(f" > {p['adherents']['prenom']} {p['adherents']['nom']} ({p['nb_enfants']} enf.)")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux & Horaires", "🛡️ Sécurité"])
        
        with t1: # GESTION ATELIERS
            sub = st.radio("Mode", ["Générateur", "Liste"], horizontal=True)
            if sub == "Générateur":
                c1, c2, c3 = st.columns(3)
                start = c1.date_input("Début", date.today())
                end = c2.date_input("Fin", start + timedelta(days=7))
                jours = c3.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                if st.button("📊 Préparer"):
                    js = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    tmp = []; curr = start
                    while curr <= end:
                        if js[curr.weekday()] in jours:
                            tmp.append({"Date": str(curr), "Titre": "Atelier Jeux", "Lieu": liste_lieux[0] if liste_lieux else "", "Horaire": liste_h[0] if liste_h else "", "Capacité": 12})
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = tmp
                if st.session_state['at_list']:
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list']), use_container_width=True)
                    if st.button("💾 Enregistrer"):
                        for _, r in df_ed.iterrows():
                            supabase.table("ateliers").insert({"titre": r['Titre'], "date_atelier": r['Date'], "lieu_id": dict_lieux[r['Lieu']], "horaire_id": dict_h[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": True}).execute()
                        st.session_state['at_list'] = []; st.rerun()

        with t2: # ADHÉRENTS
            with st.form("add_adh"):
                n = st.text_input("Nom"); p = st.text_input("Prénom")
                if st.form_submit_button("Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            for ad in res_adh.data: st.write(f"• {ad['prenom']} {ad['nom']}")

        with t3: # LIEUX & HORAIRES
            col_l, col_h = st.columns(2)
            with col_l:
                st.subheader("🏠 Lieux")
                for l in res_lieux.data: st.write(f"• {l['nom']} ({l['capacite_accueil']} pl.)")
            with col_h:
                st.subheader("⏰ Horaires")
                with st.form("add_h"):
                    new_h = st.text_input("Nouvel horaire (ex: 9h30 - 11h30)")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": new_h, "est_actif": True}).execute(); st.rerun()
                for h in res_h.data: st.write(f"• {h['libelle']}")

        with t4: # SÉCURITÉ
            new_p = st.text_input("Nouveau code", type="password")
            if st.button("Valider le changement"):
                supabase.table("configuration").update({"secret_code": new_p}).eq("id", "main_config").execute()
                st.success("Code modifié")
    else: st.info("Saisissez le code secret.")
