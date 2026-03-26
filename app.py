import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib
import io
from fpdf import FPDF

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- CONNEXION SUPABASE ---
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- STYLE CSS COMPLET (RESTAURÉ) ---
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

# --- FONCTIONS EXPORTS ---
def generate_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", "B", 9)
    # Header
    col_width = 190 / len(df.columns)
    for col in df.columns:
        pdf.cell(col_width, 10, col.encode('latin-1', 'replace').decode('latin-1'), 1)
    pdf.ln()
    # Data
    pdf.set_font("Arial", "", 8)
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(col_width, 8, str(item).encode('latin-1', 'replace').decode('latin-1'), 1)
        pdf.ln()
    return pdf.output(dest="S").encode("latin-1")

def generate_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Récapitulatif')
    return output.getvalue()

# --- DIALOGUE SUPPRESSION SÉCURISÉE ---
@st.dialog("⚠️ Confirmation requise")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Êtes-vous sûr de vouloir désactiver : **{label}** ?")
    pw = st.text_input("Code administrateur", type="password")
    if st.button("Confirmer la suppression", type="primary"):
        if pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Supprimé avec succès")
            st.rerun()
        else:
            st.error("Code incorrect")

# --- INITIALISATION ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
current_code = get_secret_code()

# Chargement données globales
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
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            date_f = format_date_fr_complete(at['date_atelier'])
            
            with st.expander(f"{date_f} — {at['titre']} | {at['lieux']['nom']} | {statut_p}"):
                if res_ins.data:
                    for i in sorted(res_ins.data, key=lambda x: x['adherents']['nom']):
                        st.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} **({i['nb_enfants']} enf.)**")
                
                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                try: idx_def = (liste_adh.index(user_principal) + 1)
                except: idx_def = 0
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_adh = dict_adh[qui]
                        diff = (1 + nb_e)
                        if restantes - diff < 0:
                            st.error(f"Plus que {restantes} places.")
                        else:
                            supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
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
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom)), adherents(nom, prenom)").in_("adherent_id", ids).order("adherent_id").execute()
        
        export_adh_data = []
        curr_u = ""
        for i in data.data:
            nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom_u != curr_u:
                st.markdown(f'<div style="color:#1b5e20; border-bottom:2px solid #1b5e20; padding-top:15px; margin-bottom:8px; font-weight:bold; font-size:1.2rem;">{nom_u}</div>', unsafe_allow_html=True)
                curr_u = nom_u
            
            at = i['ateliers']
            date_aff = format_date_fr_complete(at['date_atelier'])
            st.write(f"{date_aff} — {at['titre']} ({at['lieux']['nom']}) **({i['nb_enfants']} enfants)**")
            export_adh_data.append({"Adhérent": nom_u, "Date": at['date_atelier'], "Atelier": at['titre'], "Lieu": at['lieux']['nom'], "Enfants": i['nb_enfants']})
        
        if export_adh_data:
            st.write("---")
            df_adh = pd.DataFrame(export_adh_data)
            col_ex1, col_ex2 = st.columns(2)
            col_ex1.download_button("📥 Excel (Adhérents)", generate_excel(df_adh), "Recap_Adherents.xlsx")
            col_ex2.download_button("📄 PDF (Adhérents)", generate_pdf(df_adh, "Récapitulatif par Adhérent"), "Recap_Adherents.pdf")

    with t2:
        c_f1, c_f2, c_f3 = st.columns([1, 1, 1])
        d_start = c_f1.date_input("Du", date.today(), format="DD/MM/YYYY")
        d_end = c_f2.date_input("Au", d_start + timedelta(days=30), format="DD/MM/YYYY")
        f_lieu = c_f3.multiselect("Filtrer par Lieu", liste_lieux)
        
        query = supabase.table("ateliers").select("*, lieux(nom)").eq("est_actif", True).gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end))
        if f_lieu:
            ids_l = [dict_lieux[name] for name in f_lieu]
            query = query.in_("lieu_id", ids_l)
        
        ats_raw = query.order("date_atelier").execute()
        export_at_data = []
            
        for index, a in enumerate(ats_raw.data):
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            t_ad = len(ins_at.data); t_en = sum([p['nb_enfants'] for p in ins_at.data])
            t_occ = t_ad + t_en; rest = a['capacite_max'] - t_occ
            
            # Alertes visuelles
            cl_alerte = "alerte-rouge" if rest <= 0 else ("alerte-orange" if rest <= 3 else "")
            
            st.markdown(f"""
                **{format_date_fr_complete(a['date_atelier'])}** | <span class='lieu-badge' style='background-color:{get_color(a['lieux']['nom'])}'>{a['lieux']['nom']}</span> | <span class='compteur-badge {cl_alerte}'>🏁 {rest} pl. libres</span>
            """, unsafe_allow_html=True)
            
            for p in sorted(ins_at.data, key=lambda x: x['adherents']['nom']):
                n_f = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                st.markdown(f'<span class="liste-inscrits">• {n_f} <span class="nb-enfants-focus">({p["nb_enfants"]} enfants)</span></span>', unsafe_allow_html=True)
                export_at_data.append({"Date": a['date_atelier'], "Lieu": a['lieux']['nom'], "Atelier": a['titre'], "Inscrit": n_f, "Enfants": p['nb_enfants']})
            
            if index < len(ats_raw.data) - 1: st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)

        if export_at_data:
            st.write("---")
            df_at = pd.DataFrame(export_at_data)
            col_ex3, col_ex4 = st.columns(2)
            col_ex3.download_button("📥 Excel (Ateliers)", generate_excel(df_at), "Recap_Ateliers.xlsx")
            col_ex4.download_button("📄 PDF (Ateliers)", generate_pdf(df_at, "Liste des Inscriptions par Atelier"), "Recap_Ateliers.pdf")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t_ad1, t_ad2, t_ad3 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Sécurité"])
        
        with t_ad1:
            sub = st.radio("Mode", ["Générateur", "Liste complète"], horizontal=True)
            if sub == "Générateur":
                st.subheader("Générer des ateliers en masse")
                c_g1, c_g2, c_g3 = st.columns(3)
                d1 = c_g1.date_input("Début", date.today())
                d2 = c_g2.date_input("Fin", d1 + timedelta(days=7))
                jours_sel = c_g3.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Préparer la liste"):
                    js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    tmp = []; curr = d1
                    while curr <= d2:
                        if js_fr[curr.weekday()] in jours_sel:
                            tmp.append({"Date": str(curr), "Titre": "Atelier Jeux", "Lieu": liste_lieux[0], "Capacité": 12})
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = tmp
                
                if st.session_state['at_list']:
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list']), use_container_width=True, hide_index=True)
                    if st.button("💾 Enregistrer dans la base"):
                        for _, row in df_ed.iterrows():
                            l_id = dict_lieux[row['Lieu']]
                            supabase.table("ateliers").insert({"titre": row['Titre'], "date_atelier": row['Date'], "lieu_id": l_id, "capacite_max": row['Capacité'], "est_actif": True}).execute()
                        st.success("Ateliers créés !"); st.session_state['at_list'] = []; st.rerun()
            else:
                # Affichage simple de tous les ateliers actifs pour suppression
                ats_full = supabase.table("ateliers").select("*, lieux(nom)").eq("est_actif", True).order("date_atelier", desc=True).execute()
                for a in ats_full.data:
                    c1, c2 = st.columns([0.85, 0.15])
                    c1.write(f"**{a['date_atelier']}** - {a['titre']} ({a['lieux']['nom']})")
                    if c2.button("🗑️", key=f"at_del_{a['id']}"):
                        secure_delete_dialog("ateliers", a['id'], f"Atelier du {a['date_atelier']}", current_code)

        with t_ad2:
            st.subheader("Ajouter une adhérente")
            with st.form("new_adh"):
                n = st.text_input("Nom"); p = st.text_input("Prénom")
                if st.form_submit_button("➕ Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute()
                    st.rerun()
            st.write("---")
            for u in res_adh.data:
                c1, c2 = st.columns([0.85, 0.15])
                c1.write(f"• **{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_del_{u['id']}"):
                    secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t_ad3:
            st.subheader("Lieux")
            for l in res_lieux.data:
                st.write(f"🏠 {l['nom']} (Capacité par défaut : {l['capacite_accueil']})")
            
            st.write("---")
            st.subheader("Sécurité")
            new_pw = st.text_input("Nouveau code secret", type="password")
            if st.button("Modifier le code"):
                supabase.table("configuration").update({"secret_code": new_pw}).eq("id", "main_config").execute()
                st.success("Code secret mis à jour !")
    else:
        st.info("Veuillez entrer le code secret pour accéder à l'administration.")
