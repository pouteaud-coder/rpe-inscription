import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# Style CSS épuré et fin
st.markdown("""
    <style>
    .suivi-ligne {
        padding: 6px 0px;
        border-bottom: 1px solid #eee;
        display: flex;
        align-items: center;
        font-size: 0.9rem;
    }
    .date-info {
        font-weight: 600;
        color: #444;
        width: 140px;
    }
    .titre-info {
        flex-grow: 1;
        color: #222;
    }
    .badge-fin {
        font-size: 0.75rem;
        padding: 1px 6px;
        border: 1px solid #ccc;
        border-radius: 4px;
        color: #666;
        margin-left: 10px;
    }
    .nb-enfants {
        font-weight: bold;
        color: #2e7d32;
        margin-left: 15px;
        min-width: 80px;
    }
    .nom-header {
        color: #1b5e20;
        border-bottom: 2px solid #1b5e20;
        padding-top: 20px;
        margin-bottom: 10px;
        font-size: 1.1rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- FONCTIONS ---
def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

def format_date_fr(date_obj):
    jours = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]}"

# --- CHARGEMENT DATA ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- INTERFACE ---
st.title("🌿 Suivi RPE")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Admin"])

# ==========================================
# SECTION 📝 INSCRIPTIONS (Gardée intacte)
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            
            label = f"{format_date_fr(at['date_atelier'])} - {at['titre']} | {at['lieux']['nom']} ({restantes} pl.)"
            with st.expander(label):
                if res_ins.data:
                    for i in res_ins.data:
                        c1, c2, c3 = st.columns([3, 2, 1])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c1.write(f"• {n_f}")
                        c2.write(f"{i['nb_enfants']} enfant(s)")
                        if c3.button("🗑️", key=f"del_{at['id']}_{i['id']}"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()
                
                st.markdown("---")
                c_q, c_e, c_v = st.columns([2, 2, 1])
                target = c_q.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"s_{at['id']}")
                nb_e = c_e.number_input("Enfants", 1, 10, 1, key=f"n_{at['id']}")
                if c_v.button("Valider", key=f"b_{at['id']}", type="primary"):
                    if target != "Choisir...":
                        id_t = dict_adh[target]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_t), None)
                        if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                        else: supabase.table("inscriptions").insert({"adherent_id": id_t, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                        st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP (Design Épuré)
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer les personnes :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        
        # Jointure pour récupérer tout le nécessaire
        data = supabase.table("inscriptions").select("*, ateliers(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).order("adherent_id").execute()
        
        curr_u = ""
        for i in data.data:
            nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom_u != curr_u:
                st.markdown(f"<div class='nom-header'>{nom_u}</div>", unsafe_allow_html=True)
                curr_u = nom_u
            
            # Ligne de suivi fine
            at = i['ateliers']
            st.markdown(f"""
            <div class='suivi-ligne'>
                <span class='date-info'>{format_date_fr(at['date_atelier'])}</span>
                <span class='titre-info'>{at['titre']} 
                    <span class='badge-fin'>{at['lieux']['nom']}</span>
                    <span class='badge-fin'>{at['horaires']['libelle']}</span>
                </span>
                <span class='nb-enfants'>👶 {i['nb_enfants']} enf.</span>
            </div>
            """, unsafe_allow_html=True)

    with t2:
        today = str(date.today())
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today).order("date_atelier").execute()
        dict_at = {f"{format_date_fr(a['date_atelier'])} - {a['titre']}": a['id'] for a in ats_raw.data}
        
        sel_at = st.multiselect("Filtrer les ateliers :", list(dict_at.keys()))
        at_ids = [dict_at[n] for n in sel_at] if sel_at else [a['id'] for a in ats_raw.data]

        for a_id in at_ids:
            a_info = next(at for at in ats_raw.data if at['id'] == a_id)
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a_id).execute()
            
            st.markdown(f"**{format_date_fr(a_info['date_atelier'])} — {a_info['titre']}** <small>({a_info['lieux']['nom']} | {a_info['horaires']['libelle']})</small>", unsafe_allow_html=True)
            
            if not ins_at.data:
                st.write("<small style='color:gray; padding-left:20px;'>Aucun inscrit</small>", unsafe_allow_html=True)
            else:
                for p in ins_at.data:
                    nom_p = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                    st.markdown(f"""
                    <div style='display:flex; justify-content:space-between; max-width:400px; padding-left:20px; font-size:0.85rem; border-left:1px solid #ddd; margin:2px 0;'>
                        <span>{nom_p}</span>
                        <span style='color:#2e7d32; font-weight:bold;'>{p['nb_enfants']} enf.</span>
                    </div>
                    """, unsafe_allow_html=True)
            st.write("")

# ==========================================
# SECTION 🔐 ADMIN
# ==========================================
elif menu == "🔐 Admin":
    pw = st.text_input("Code", type="password")
    if pw == current_code:
        st.success("Accès autorisé")
        # Logique simplifiée ici pour la démo, le reste de votre code Admin s'insère ici.
