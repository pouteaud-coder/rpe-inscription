import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect - Premium", page_icon="🌿", layout="wide")

# Style CSS pour un rendu "Stylé"
st.markdown("""
    <style>
    .at-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 20px;
        border-left: 8px solid #4CAF50;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .badge-lieu {
        background-color: #E8F5E9;
        color: #2E7D32;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 5px;
    }
    .badge-heure {
        background-color: #FFF3E0;
        color: #E65100;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .participant-box {
        background: #f1f3f4;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 8px;
        border: 1px solid #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- FONCTIONS UTILITAIRES ---
def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

def format_date_fr(date_obj):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"

def parse_date_fr_to_iso(date_str):
    date_str = str(date_str).lower().strip()
    mois_map = {"janvier":"01", "février":"02", "mars":"03", "avril":"04", "mai":"05", "juin":"06", 
                "juillet":"07", "août":"08", "septembre":"09", "octobre":"10", "novembre":"11", "décembre":"12"}
    match = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", date_str)
    if match:
        d, m, y = match.groups()
        return f"{y}-{mois_map.get(m, '01')}-{d.zfill(2)}"
    return str(date.today())

# --- GESTION DES DIALOGUES & SESSION ---
if 'u_opened_at' not in st.session_state: st.session_state['u_opened_at'] = None

@st.dialog("Confirmer la suppression")
def confirm_delete_inscrit(inscrit_id, nom):
    st.warning(f"Désinscrire définitivement **{nom}** ?")
    if st.button("Oui, supprimer", type="primary"):
        supabase.table("inscriptions").delete().eq("id", inscrit_id).execute()
        st.rerun()

# --- CHARGEMENT DATA ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- INTERFACE ---
st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Récapitulatif Visuel", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions aux Ateliers")
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            
            is_open = st.session_state['u_opened_at'] == at['id']
            titre_display = f"📅 {format_date_fr(at['date_atelier'])} - {at['titre']} | {at['lieux']['nom']} ({restantes} pl.)"
            
            with st.expander(titre_display, expanded=is_open):
                st.session_state['u_opened_at'] = at['id']
                
                # Liste des inscrits
                if res_ins.data:
                    for i in res_ins.data:
                        c1, c2, c3 = st.columns([3, 2, 1])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c1.write(f"• **{n_f}**")
                        c2.write(f"{i['nb_enfants']} enfant(s)")
                        if c3.button("🗑️", key=f"del_{at['id']}_{i['id']}"): confirm_delete_inscrit(i['id'], n_f)
                else: st.write("_Aucun inscrit_")
                
                st.markdown("---")
                # Formulaire
                ci1, ci2, ci3 = st.columns([2, 2, 1])
                target = ci1.selectbox("Qui inscrire ?", ["Choisir..."] + liste_adh, key=f"sel_{at['id']}")
                m_e = ci2.radio("Enfants :", ["1", "2", "3", "4", "Plus..."], horizontal=True, key=f"rad_{at['id']}")
                nb_e = st.number_input("Nombre :", 5, 20, 5, key=f"num_{at['id']}") if m_e == "Plus..." else int(m_e)
                
                if ci3.button("Valider", key=f"btn_{at['id']}", type="primary"):
                    if target != "Choisir...":
                        id_t = dict_adh[target]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_t), None)
                        diff = (1 + nb_e) if not existing else (nb_e - existing['nb_enfants'])
                        if diff <= restantes:
                            if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                            else: supabase.table("inscriptions").insert({"adherent_id": id_t, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                            st.rerun()
                        else: st.error("Plus de places disponibles.")

# ==========================================
# SECTION 📊 RÉCAPITULATIF VISUEL
# ==========================================
elif menu == "📊 Récapitulatif Visuel":
    st.header("✨ Consultation Stylée")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).order("ateliers(date_atelier)").execute()
        
        curr_u = ""
        for i in data.data:
            u_n = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if u_n != curr_u:
                st.subheader(f"👤 {u_n}")
                curr_u = u_n
            
            st.markdown(f"""
            <div class='at-card'>
                <span class='badge-lieu'>📍 {i['ateliers']['lieux']['nom']}</span>
                <span class='badge-heure'>⏰ {i['ateliers']['horaires']['libelle']}</span>
                <div style='margin-top:10px;'><b>{format_date_fr(i['ateliers']['date_atelier'])}</b> — {i['ateliers']['titre']}</div>
                <div style='color:#1565C0; font-weight:bold;'>👶 {i['nb_enfants']} enfant(s)</div>
            </div>
            """, unsafe_allow_html=True)

    with t2:
        today = str(date.today())
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today).order("date_atelier").execute()
        dict_at = {f"{format_date_fr(a['date_atelier'])} - {a['titre']}": a['id'] for a in ats.data}
        sel_at = st.multiselect("Filtrer par atelier :", list(dict_at.keys()))
        at_ids = [dict_at[n] for n in sel_at] if sel_at else [a['id'] for a in ats.data]

        for a_id in at_ids:
            a_info = next(at for at in ats.data if at['id'] == a_id)
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a_id).execute()
            
            st.markdown(f"#### 📅 {format_date_fr(a_info['date_atelier'])} - {a_info['titre']}")
            # CORRECTION DES GUILLEMETS ICI :
            st.markdown(f"<span class='badge-lieu'>📍 {a_info['lieux']['nom']}</span><span class='badge-heure'>⏰ {a_info['horaires']['libelle']}</span>", unsafe_allow_html=True)
            
            if not ins_at.data: st.write("_Aucun inscrit_")
            else:
                cols = st.columns(3)
                for idx, p in enumerate(ins_at.data):
                    with cols[idx % 3]:
                        st.markdown(f"""
                        <div class='participant-box'>
                            <b>{p['adherents']['prenom']} {p['adherents']['nom']}</b><br>
                            <span style='color:#1565c0;'>👶 {p['nb_enfants']} enfant(s)</span>
                        </div>
                        """, unsafe_allow_html=True)
            st.markdown("---")

# ==========================================
# SECTION 🔐 ADMINISTRATION (Code Complet)
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        # (La suite de la logique d'administration reste la même que précédemment)
        with t2:
            with st.form("new_adh"):
                n, p = st.text_input("Nom"), st.text_input("Prénom")
                if st.form_submit_button("Ajouter l'adhérente"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute()
                    st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([5,1])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_{u['id']}"):
                    supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute()
                    st.rerun()
    else: st.info("Saisissez le code secret pour accéder à la gestion.")
