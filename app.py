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

# Fonction pour formater la date en français (ex: lundi 2 janvier 2026)
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
                    st.write(f"👥 **Places max :** {at['capacite_max']}")
                    if st.button("Confirmer l'inscription", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("Inscription validée !")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    password_input = st.text_input("Code secret de session", type="password")

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Gestion des Ateliers", "👥 Gestion des Adhérents", "📍 Gestion Lieux et Horaires", "⚙️ Sécurité"])
        
        # --- ONGLET 1 : GESTION DES ATELIERS (GÉNÉRATEUR RAPIDE) ---
        with t1:
            st.subheader("🚀 Générateur d'ateliers en série")
            
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            
            if l_data and h_data:
                with st.expander("🛠️ Configurer une série d'ateliers"):
                    col1, col2 = st.columns(2)
                    d_debut = col1.date_input("Date de début", datetime.now())
                    d_fin = col2.date_input("Date de fin", datetime.now() + timedelta(days=14))
                    
                    jours_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    jours_choisis = st.multiselect("Jours de la semaine concernés", jours_semaine, default=["Lundi", "Jeudi"])
                    
                    c3, c4, c5 = st.columns(3)
                    titre_at = c3.text_input("Titre de l'atelier")
                    lieu_obj = c4.selectbox("Lieu par défaut", l_data, format_func=lambda x: f"{x['nom']} (Cap: {x['capacite_accueil']})")
                    horaire_obj = c5.selectbox("Horaire", h_data, format_func=lambda x: x['libelle'])
                    
                    if st.button("Générer la liste pour vérification"):
                        ateliers_a_creer = []
                        curr = d_debut
                        while curr <= d_fin:
                            if jours_semaine[curr.weekday()] in jours_choisis:
                                ateliers_a_creer.append({
                                    "date_atelier": str(curr),
                                    "titre": titre_at,
                                    "lieu_id": lieu_obj['id'],
                                    "horaire_id": horaire_obj['id'],
                                    "capacite_max": lieu_obj['capacite_accueil'],
                                    "est_actif": True
                                })
                            curr += timedelta(days=1)
                        st.session_state['temp_ateliers'] = ateliers_a_creer

                # Affichage sous forme de TABLEAU pour modification avant enregistrement
                if 'temp_ateliers' in st.session_state and st.session_state['temp_ateliers']:
                    st.write("### 📋 Révision avant publication")
                    df_temp = pd.DataFrame(st.session_state['temp_ateliers'])
                    
                    # Interface de type tableau éditable
                    edited_df = st.data_editor(
                        df_temp,
                        column_config={
                            "date_atelier": st.column_config.DateColumn("Date", required=True),
                            "titre": "Titre de l'Atelier",
                            "capacite_max": st.column_config.NumberColumn("Capacité", min_value=1, step=1),
                            "est_actif": st.column_config.CheckboxColumn("Actif ?", default=True),
                            "lieu_id": None, "horaire_id": None # Masqués car ID techniques
                        },
                        hide_index=True
                    )
                    
                    if st.button("✅ Enregistrer tous ces ateliers en base"):
                        supabase.table("ateliers").insert(edited_df.to_dict(orient='records')).execute()
                        st.success(f"{len(edited_df)} ateliers créés !")
                        del st.session_state['temp_ateliers']
                        st.rerun()
            else:
                st.warning("Veuillez créer des lieux et horaires d'abord.")

        # --- ONGLET 3 : LIEUX & HORAIRES (AVEC CAPACITÉ) ---
        with t3:
            col_l, col_h = st.columns(2)
            with col_l:
                st.subheader("📍 Lieux & Capacités")
                with st.form("add_l"):
                    nl = st.text_input("Nom du lieu")
                    cap = st.number_input("Capacité d'accueil par défaut", min_value=1, value=10)
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cap, "est_actif": True}).execute()
                        st.rerun()
                
                for l in supabase.table("lieux").select("*").eq("est_actif", True).execute().data:
                    cl1, cl2 = st.columns([4, 1])
                    cl1.write(f"🏠 **{l['nom']}** (Capacité : {l['capacite_accueil']})")
                    if cl2.button("🗑️", key=f"dl_{l['id']}"):
                        supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                        st.rerun()

            with col_h:
                st.subheader("⏰ Horaires")
                nh = st.text_input("Nouveau créneau")
                if st.button("Ajouter Horaire"):
                    supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute()
                    st.rerun()
                for h in supabase.table("horaires").select("*").eq("est_actif", True).execute().data:
                    ch1, ch2 = st.columns([4, 1])
                    ch1.write(f"⏰ {h['libelle']}")
                    if ch2.button("🗑️", key=f"dh_{h['id']}"):
                        supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                        st.rerun()
        
        # (Les onglets Adhérents et Sécurité restent identiques au code précédent)
