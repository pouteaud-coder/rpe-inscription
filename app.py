import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# 1. Configuration
st.set_page_config(page_title="RPE Connect - Gestion", page_icon="🌿", layout="wide")

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

current_code = get_secret_code()

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION ADMINISTRATION ---
if menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    
    col_pass, col_forget = st.columns([2, 1])
    with col_pass:
        password_input = st.text_input("Code secret de session", type="password")
    
    with col_forget:
        st.write(" ")
        if st.button("Code secret oublié ?"):
            @st.dialog("Récupération")
            def recover():
                rescue = st.text_input("Code de secours (0000)", type="password")
                new_c = st.text_input("Nouveau code", type="password")
                if st.button("Valider"):
                    if rescue == "0000" and new_c:
                        supabase.table("configuration").update({"secret_code": new_c}).eq("id", "main_config").execute()
                        st.rerun()
            recover()

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Gestion Ateliers", "👥 Adhérents", "📍 Lieux & Horaires", "⚙️ Sécurité"])
        
        with t1:
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            liste_lieux = [l['nom'] for l in l_data]
            liste_horaires = [h['libelle'] for h in h_data]
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_data}

            st.subheader("🚀 Création des Ateliers")
            
            c_btn1, c_btn2 = st.columns(2)
            
            # OPTION 1 : GÉNÉRER UNE SÉRIE
            with st.expander("🛠️ Générer une série d'ateliers"):
                c1, c2 = st.columns(2)
                d_debut = c1.date_input("Date de début", datetime.now(), format="DD/MM/YYYY")
                d_fin = c2.date_input("Date de fin", d_debut + timedelta(days=14), format="DD/MM/YYYY")
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                titre_s = st.text_input("Titre de la série", value="Atelier Éveil")
                
                if st.button("Générer la série dans le tableau"):
                    temp = []
                    curr = d_debut
                    js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    while curr <= d_fin:
                        if js_fr[curr.weekday()] in jours:
                            temp.append({
                                "Date": format_date_fr(curr), "Titre": titre_s, "Lieu": liste_lieux[0],
                                "Horaire": liste_horaires[0], "Capacité": map_capa[liste_lieux[0]],
                                "Actif": True, "_raw_date": str(curr)
                            })
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = temp

            # OPTION 2 : AJOUTER UN SEUL ATELIER
            if st.button("➕ Ajouter un seul atelier (ligne vide)"):
                new_row = {
                    "Date": format_date_fr(datetime.now()), "Titre": "Nouvel Atelier", "Lieu": liste_lieux[0],
                    "Horaire": liste_horaires[0], "Capacité": map_capa[liste_lieux[0]], "Actif": True, "_raw_date": str(datetime.now().date())
                }
                if 'at_list' not in st.session_state: st.session_state['at_list'] = []
                st.session_state['at_list'].append(new_row)

            # AFFICHAGE DU TABLEAU DE RÉVISION
            if 'at_list' in st.session_state and st.session_state['at_list']:
                st.write("### 📋 Révision et Ajustements")
                st.caption("Vous pouvez ajouter des lignes (+), les supprimer ou modifier les lieux.")
                
                df_ed = pd.DataFrame(st.session_state['at_list'])
                
                final_df = st.data_editor(
                    df_ed, 
                    hide_index=True, 
                    use_container_width=True,
                    num_rows="dynamic",
                    column_config={
                        "Date": st.column_config.TextColumn("Date (Lecture seule)", disabled=True),
                        "Titre": st.column_config.TextColumn("Titre de l'atelier", width="large"),
                        "Lieu": st.column_config.SelectboxColumn("Lieu", options=liste_lieux, width="medium"),
                        "Horaire": st.column_config.SelectboxColumn("Horaire", options=liste_horaires, width="medium", help="Centré"),
                        "Capacité": st.column_config.NumberColumn("Capacité", width="medium", help="Centré"),
                        "Actif": st.column_config.CheckboxColumn("Actif"),
                        "_raw_date": None
                    }
                )

                # BOUTON POUR FORCER LA MISE À JOUR DES CAPACITÉS SELON LES LIEUX
                if st.button("🔄 Actualiser les capacités selon les lieux choisis"):
                    for i, row in final_df.iterrows():
                        final_df.at[i, 'Capacité'] = map_capa.get(row['Lieu'], 10)
                    st.session_state['at_list'] = final_df.to_dict(orient='records')
                    st.rerun()

                c_save, c_del = st.columns(2)
                if c_save.button("✅ Enregistrer définitivement"):
                    map_l = {l['nom']: l['id'] for l in l_data}
                    map_h = {h['libelle']: h['id'] for h in h_data}
                    to_db = [{"date_atelier": r['_raw_date'], "titre": r['Titre'], "lieu_id": map_l[r['Lieu']], 
                              "horaire_id": map_h[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": r['Actif']} 
                             for _, r in final_df.iterrows()]
                    supabase.table("ateliers").insert(to_db).execute()
                    del st.session_state['at_list']
                    st.success("Ateliers publiés !")
                    st.rerun()
                
                if c_del.button("❌ Tout effacer"):
                    del st.session_state['at_list']
                    st.rerun()

        # --- RESTE DU CODE (ADHÉRENTS, LIEUX...) ---
        with t3:
            st.subheader("📍 Lieux & Horaires")
            # (Conservation de la logique précédente triée A-Z)
            l_list = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            for l in l_list:
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**{l['nom']}** (Capacité: {l['capacite_accueil']})")
                    if c2.button("Désactiver", key=f"dl_{l['id']}"):
                        supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                        st.rerun()

        with t2:
            st.subheader("👥 Répertoire Adhérents")
            for u in supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute().data:
                st.write(f"👤 {u['nom']} {u['prenom']}")

# --- SECTION INSCRIPTION ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription")
    # (Conservation de la logique de sélection de nom et expanders par date)
    st.info("Sélectionnez votre nom pour voir les ateliers disponibles.")
