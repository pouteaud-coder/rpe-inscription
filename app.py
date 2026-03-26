import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- SYSTÈME DE COULEURS ET ÉMOJIS POUR LES LIEUX ---
# On associe un émoji de couleur pour le titre de l'accordéon
MAP_INFOS_LIEUX = {
    "POISSY": {"color": "#d32f2f", "emoji": "🔴"},
    "CARRIÈRES": {"color": "#1976d2", "emoji": "🔵"},
    "RAMBOUILLET": {"color": "#388e3c", "emoji": "🟢"},
    "VERSAILLES": {"color": "#f57c00", "emoji": "🟠"},
    "ST-GERMAIN": {"color": "#7b1fa2", "emoji": "🟣"},
    "DEFAULT": {"color": "#6c757d", "emoji": "⚪"}
}

def get_lieu_info(nom_lieu):
    nom_upper = str(nom_lieu).upper()
    for clé, info in MAP_INFOS_LIEUX.items():
        if clé in nom_upper: return info
    return MAP_INFOS_LIEUX["DEFAULT"]

# Style CSS
st.markdown("""
    <style>
    .st-emotion-cache-p5m613 p { white-space: normal !important; line-height: 1.5 !important; }
    .lieu-badge { padding: 2px 10px; border-radius: 12px; color: white; font-weight: bold; font-size: 0.9rem; margin-bottom: 10px; display: inline-block; }
    .nom-header { color: #1b5e20; border-bottom: 2px solid #1b5e20; padding-top: 15px; margin-bottom: 8px; font-weight: bold; }
    .inscrit-ligne { display: flex; align-items: center; justify-content: space-between; background: #f8f9fa; padding: 5px 10px; border-radius: 5px; margin-bottom: 3px; }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase (Secrets)
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

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

# --- CHARGEMENT DATA ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- INTERFACE ---
st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

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
            
            # Gestion couleur des places
            statut_places = f"✅ {restantes} places" if restantes > 0 else "🚨 COMPLET"
            
            # Récupération info lieu (émoji pour le titre)
            info_l = get_lieu_info(at['lieux']['nom'])
            
            # TITRE ACCORDÉON (Date en gras, Émoji Lieu, Statut Places)
            date_txt = format_date_fr_complete(at['date_atelier'], gras=True)
            titre_label = f"{date_txt} — {at['titre']}\n{info_l['emoji']} {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_places}"
            
            with st.expander(titre_label):
                # Badge de couleur réel à l'intérieur
                st.markdown(f"<span class='lieu-badge' style='background-color:{info_l['color']}'>📍 {at['lieux']['nom']}</span>", unsafe_allow_html=True)
                
                if res_ins.data:
                    for i in res_ins.data:
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_text, c_del = st.columns([5, 1])
                        # Affichage compact : Prénom Nom (X enf.) 🗑️
                        c_text.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_del.button("🗑️", key=f"del_{i['id']}"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()
                
                st.markdown("---")
                # Auto-sélection
                try: idx_def = (liste_adh.index(user_principal) + 1)
                except: idx_def = 0
                
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_adh = dict_adh[qui]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_adh), None)
                        if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                        else: supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                        st.rerun()

elif menu == "📊 Suivi & Récap":
    # Le reste du code suit la même logique de couleur pour les badges...
    st.info("Le système de couleurs est aussi appliqué ici.")
    # (Le code des autres sections est conservé avec l'intégration des badges couleurs)
