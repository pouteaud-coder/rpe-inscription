import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# 1. Configuration - Largeur maximale
st.set_page_config(page_title="RPE Connect - Gestion Master", page_icon="🌿", layout="wide")

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

# --- CONFIGURATION DES COLONNES (Standardisée pour les deux tableaux) ---
COL_CONFIG = {
    "Date": st.column_config.TextColumn("Date", width=220),       # ~28 car.
    "Titre": st.column_config.TextColumn("Titre", width=320),     # ~40 car.
    "Lieu": st.column_config.SelectboxColumn("Lieu", width=130),  # ~15 car.
    "Horaire": st.column_config.SelectboxColumn("Horaire", width=130), # ~15 car.
    "Capacité": st.column_config.NumberColumn("Cap.", width=60),  # ~6 car.
    "Actif": st.column_config.CheckboxColumn("Actif", width=60),  # ~6 car.
    "_raw_date": None, "ID": None
}

if 'at_list' not in st.session_state:
    st.session_state['at_list'] = []

current_code = get_secret_code()

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION 1 : INCRIPTION ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    choix_adh = st.selectbox("Votre nom", ["Choisir..."] + list(noms_adh.keys()))
    
    if choix_adh != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).order("date_atelier").execute()
        if res_at.data:
            for at in res_at.data:
                with st.expander(f"📅 {format_date_fr(at['date_atelier'])} - {at['titre']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    if st.button("S'inscrire", key=f"at_reg_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("✅ Inscrit !")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    password_input = st.text_input("Code secret d'accès", type="password")

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1:
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            liste_l = [l['nom'] for l in l_raw]; liste_h = [h['libelle'] for h in h_raw]
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_h_id = {h['libelle']: h['id'] for h in h_raw}

            sub_m = st.radio("Sous-menu :", ["Générateur d'ateliers", "Répertoire"], horizontal=True)

            if sub_m == "Générateur d'ateliers":
                st.subheader("🚀 Création de sessions")
                
                # Zone de contrôle hors tableau pour l'ajout
                c_gen, c_add = st.columns([2, 1])
                with c_gen.expander("🛠️ Générer une série"):
                    d_deb = st.date_input("Début", datetime.now(), format="DD/MM/YYYY")
                    d_fin = st.date_input("Fin", d_deb + timedelta(days=7), format="DD/MM/YYYY")
                    jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Lancer la génération"):
                        temp = []
                        curr = d_deb
                        while curr <= d_fin:
                            js = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                            if js[curr.weekday()] in jours:
                                temp.append({"Date": format_date_fr(curr), "Titre": "Atelier Éveil", "Lieu": liste_l[0], "Horaire": liste_h[0], "Capacité": map_capa[liste_l[0]], "Actif": True, "_raw_date": str(curr)})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = temp
                        st.rerun()

                with c_add:
                    st.write(" ")
                    if st.button("➕ Ajouter une ligne vierge au tableau"):
                        st.session_state['at_list'].append({"Date": format_date_fr(datetime.now()), "Titre": "", "Lieu": liste_l[0], "Horaire": liste_h[0], "Capacité": map_capa[liste_l[0]], "Actif": True, "_raw_date": str(datetime.now().date())})
                        st.rerun()

                if st.session_state['at_list']:
                    df_gen = pd.DataFrame(st.session_state['at_list'])
                    
                    # Application des colonnes avec Selectbox pour les lieux/horaires
                    COL_CONFIG["Lieu"] = st.column_config.SelectboxColumn("Lieu", options=liste_l, width=130)
                    COL_CONFIG["Horaire"] = st.column_config.SelectboxColumn("Horaire", options=liste_h, width=130)

                    res_gen = st.data_editor(df_gen, hide_index=True, use_container_width=False, num_rows="dynamic",
                        column_config=COL_CONFIG, key="editor_gen")

                    # Logique Auto-Capacité
                    if not res_gen.equals(df_gen):
                        for i, row in res_gen.iterrows():
                            if i < len(st.session_state['at_list']) and row['Lieu'] != st.session_state['at_list'][i]['Lieu']:
                                res_gen.at[i, 'Capacité'] = map_capa.get(row['Lieu'], 10)
                        st.session_state['at_list'] = res_gen.to_dict(orient='records')
                        st.rerun()

                    if st.button("✅ Enregistrer les nouveaux ateliers"):
                        to_db = [{"date_atelier": r.get('_raw_date', str(datetime.now().date())), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": r['Actif']} for _, r in res_gen.iterrows() if r['Titre']]
                        supabase.table("ateliers").insert(to_db).execute()
                        st.session_state['at_list'] = []; st.rerun()

            else:
                st.subheader("📚 Répertoire")
                f_radio = st.radio("Filtre :", ["Tous", "Actifs", "Inactifs"], horizontal=True)
                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)")
                if f_radio == "Actifs": query = query.eq("est_actif", True)
                elif f_radio == "Inactifs": query = query.eq("est_actif", False)
                db_data = query.order("date_atelier", desc=True).execute().data
                
                if db_data:
                    df_rep = pd.DataFrame([{"ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Capacité": a['capacite_max'], "Actif": a['est_actif']} for a in db_data])
                    
                    # On réutilise la configuration de colonnes fixe
                    COL_CONFIG["Lieu"] = st.column_config.SelectboxColumn("Lieu", options=liste_l, width=130)
                    COL_CONFIG["Horaire"] = st.column_config.SelectboxColumn("Horaire", options=liste_h, width=130)

                    res_rep = st.data_editor(df_rep, hide_index=True, use_container_width=False, disabled=["Date"], column_config=COL_CONFIG, key="editor_rep")
                    
                    if st.button("💾 Sauvegarder les modifications"):
                        for _, row in res_rep.iterrows():
                            supabase.table("ateliers").update({"titre": row['Titre'], "lieu_id": map_l_id[row['Lieu']], "horaire_id": map_h_id[row['Horaire']], "capacite_max": row['Capacité'], "est_actif": row['Actif']}).eq("id", row['ID']).execute()
                        st.rerun()

        # --- AUTRES ONGLETS (CONSERVÉS) ---
        with t2:
            st.subheader("👥 Adhérents")
            for u in supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute().data:
                st.write(f"👤 {u['nom']} {u['prenom']}")

        with t3:
            st.subheader("📍 Paramètres")
            st.write("Gérez vos lieux et horaires ici.")
            
        with t4:
            st.subheader("⚙️ Sécurité")
            st.write(f"Code actuel : `{current_code}`")

    else: st.info("Saisissez le code secret.")
