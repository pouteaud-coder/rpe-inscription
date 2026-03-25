import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# 1. Configuration
st.set_page_config(page_title="RPE Connect - Planning", page_icon="🌿", layout="wide")
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

current_code = get_secret_code()

# Utilitaires
def format_date_fr(date_obj):
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION 1 : INSCRIPTION ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + sorted(list(noms_adh.keys())))
    
    if choix_adh != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).order("date_atelier").execute()
        if res_at.data:
            for at in res_at.data:
                d_obj = datetime.strptime(at['date_atelier'], '%Y-%m-%d')
                with st.expander(f"📅 {format_date_fr(d_obj)} - {at['titre']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    if st.button("Confirmer l'inscription", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("Inscription validée !")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    password_input = st.text_input("Code secret de session", type="password")

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Gestion des Ateliers", "👥 Gestion des Adhérents", "📍 Gestion Lieux et Horaires", "⚙️ Sécurité"])
        
        # --- ONGLET 1 : GESTION DES ATELIERS ---
        with t1:
            st.subheader("🚀 Générateur d'ateliers en série")
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            
            if l_data and h_data:
                with st.expander("🛠️ Configurer une série d'ateliers"):
                    col1, col2 = st.columns(2)
                    d_debut = col1.date_input("Date de début", datetime.now())
                    d_fin = col2.date_input("Date de fin", datetime.now() + timedelta(days=14))
                    jours_choisis = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    
                    titre_at = st.text_input("Titre")
                    c_l, c_h = st.columns(2)
                    lieu_obj = c_l.selectbox("Lieu", l_data, format_func=lambda x: f"{x['nom']} (Cap: {x['capacite_accueil']})")
                    horaire_obj = c_h.selectbox("Horaire", h_data, format_func=lambda x: x['libelle'])
                    
                    if st.button("Générer la liste"):
                        res = []
                        curr = d_debut
                        js = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d_fin:
                            if js[curr.weekday()] in jours_choisis:
                                res.append({"date_atelier": str(curr), "titre": titre_at, "lieu_id": lieu_obj['id'], "horaire_id": horaire_obj['id'], "capacite_max": lieu_obj['capacite_accueil'], "est_actif": True})
                            curr += timedelta(days=1)
                        st.session_state['temp_at'] = res

                if 'temp_at' in st.session_state:
                    df = pd.DataFrame(st.session_state['temp_at'])
                    ed = st.data_editor(df, hide_index=True)
                    if st.button("✅ Publier définitivement"):
                        supabase.table("ateliers").insert(ed.to_dict(orient='records')).execute()
                        del st.session_state['temp_at']
                        st.rerun()

        # --- ONGLET 3 : LIEUX & HORAIRES (MODIFIABLE SI NON UTILISÉS) ---
        with t3:
            # Pré-chargement des usages pour bloquer la modification
            ateliers_existants = supabase.table("ateliers").select("lieu_id, horaire_id").execute().data
            lieux_utilises = {a['lieu_id'] for a in ateliers_existants}
            horaires_utilises = {a['horaire_id'] for a in ateliers_existants}

            col_l, col_h = st.columns(2)
            
            # --- GESTION DES LIEUX ---
            with col_l:
                st.subheader("📍 Lieux")
                with st.expander("➕ Nouveau Lieu"):
                    with st.form("add_l"):
                        n_l = st.text_input("Nom")
                        c_l = st.number_input("Capacité", min_value=1, value=10)
                        if st.form_submit_button("Ajouter"):
                            supabase.table("lieux").insert({"nom": n_l, "capacite_accueil": c_l, "est_actif": True}).execute()
                            st.rerun()

                st.write("**Modifier les lieux existants :**")
                all_l = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
                for l in all_l:
                    est_verrouille = l['id'] in lieux_utilises
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        # Formulaire de modification
                        new_nom = c1.text_input("Nom", value=l['nom'], key=f"ln_{l['id']}", disabled=est_verrouille)
                        new_cap = c1.number_input("Capacité", value=l['capacite_accueil'], key=f"lc_{l['id']}", disabled=est_verrouille)
                        
                        if not est_verrouille:
                            if c2.button("💾", key=f"svl_{l['id']}", help="Enregistrer les modifications"):
                                supabase.table("lieux").update({"nom": new_nom, "capacite_accueil": new_cap}).eq("id", l['id']).execute()
                                st.rerun()
                        else:
                            c2.info("🔒 Utilisé")
                        
                        if c2.button("🗑️", key=f"dell_{l['id']}"):
                            supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                            st.rerun()

            # --- GESTION DES HORAIRES ---
            with col_h:
                st.subheader("⏰ Horaires")
                with st.expander("➕ Nouvel Horaire"):
                    with st.form("add_h"):
                        n_h = st.text_input("Libellé")
                        if st.form_submit_button("Ajouter"):
                            supabase.table("horaires").insert({"libelle": n_h, "est_actif": True}).execute()
                            st.rerun()

                st.write("**Modifier les horaires :**")
                all_h = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
                for h in all_h:
                    est_verrouille_h = h['id'] in horaires_utilises
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        new_lib = c1.text_input("Horaire", value=h['libelle'], key=f"hn_{h['id']}", disabled=est_verrouille_h)
                        
                        if not est_verrouille_h:
                            if c2.button("💾", key=f"svh_{h['id']}", help="Enregistrer"):
                                supabase.table("horaires").update({"libelle": new_lib}).eq("id", h['id']).execute()
                                st.rerun()
                        else:
                            c2.info("🔒 Utilisé")
                            
                        if c2.button("🗑️", key=f"delh_{h['id']}"):
                            supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                            st.rerun()
                            
        # Les onglets Adhérents et Sécurité restent inchangés
