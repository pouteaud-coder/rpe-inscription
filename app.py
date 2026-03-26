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

# --- INITIALISATION SESSION ---
if 'at_list' not in st.session_state:
    st.session_state['at_list'] = []

current_code = get_secret_code()

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION 1 : INSCRIPTION ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + list(noms_adh.keys()))
    
    if choix_adh != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).order("date_atelier").execute()
        if res_at.data:
            for at in res_at.data:
                with st.expander(f"📅 {format_date_fr(at['date_atelier'])} - {at['titre']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    if st.button("Confirmer l'inscription", key=f"reg_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("✅ Inscription validée !")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    password_input = st.text_input("Code secret d'accès", type="password")

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        # --- ONGLET 1 : ATELIERS ---
        with t1:
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            liste_l = [l['nom'] for l in l_raw]; liste_h = [h['libelle'] for h in h_raw]
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_h_id = {h['libelle']: h['id'] for h in h_raw}

            sub_m = st.radio("Sous-menu :", ["Générateur d'ateliers", "Répertoire"], horizontal=True)

            # Dimensions demandées (px)
            conf = {
                "Date": st.column_config.TextColumn("Date", width=220),
                "Titre": st.column_config.TextColumn("Titre", width=320),
                "Lieu": st.column_config.SelectboxColumn("Lieu", options=liste_l, width=130),
                "Horaire": st.column_config.SelectboxColumn("Horaire", options=liste_h, width=130),
                "Capacité": st.column_config.NumberColumn("Cap.", width=60),
                "Actif": st.column_config.CheckboxColumn("Actif", width=60),
                "_raw_date": None, "ID": None
            }

            if sub_m == "Générateur d'ateliers":
                st.subheader("🚀 Création de sessions")
                c_gen, c_add = st.columns([2, 1])
                with c_gen.expander("🛠️ Générer une série"):
                    d_deb = st.date_input("Début", datetime.now(), format="DD/MM/YYYY")
                    d_fin = st.date_input("Fin", d_deb + timedelta(days=7), format="DD/MM/YYYY")
                    jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Lancer la génération"):
                        temp = []
                        curr = d_deb
                        js_f = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d_fin:
                            if js_f[curr.weekday()] in jours:
                                temp.append({"Date": format_date_fr(curr), "Titre": "Atelier Éveil", "Lieu": liste_l[0], "Horaire": liste_h[0], "Capacité": map_capa[liste_l[0]], "Actif": True, "_raw_date": str(curr)})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = temp
                        st.rerun()

                with c_add:
                    st.write(" ")
                    if st.button("➕ Ajouter une ligne vierge"):
                        st.session_state['at_list'].append({"Date": format_date_fr(datetime.now()), "Titre": "", "Lieu": liste_l[0], "Horaire": liste_h[0], "Capacité": map_capa[liste_l[0]], "Actif": True, "_raw_date": str(datetime.now().date())})
                        st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, use_container_width=False, num_rows="dynamic", column_config=conf, key="ed_gen")
                    if not res_gen.equals(pd.DataFrame(st.session_state['at_list'])):
                        for i, row in res_gen.iterrows():
                            if i < len(st.session_state['at_list']) and row['Lieu'] != st.session_state['at_list'][i]['Lieu']:
                                res_gen.at[i, 'Capacité'] = map_capa.get(row['Lieu'], 10)
                        st.session_state['at_list'] = res_gen.to_dict(orient='records')
                        st.rerun()
                    if st.button("✅ Enregistrer les nouveaux ateliers"):
                        to_db = [{"date_atelier": r.get('_raw_date', str(datetime.now().date())), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": r['Actif']} for _, r in res_gen.iterrows() if r['Titre']]
                        supabase.table("ateliers").insert(to_db).execute()
                        st.session_state['at_list'] = []; st.success("Enregistré !"); st.rerun()

            else:
                st.subheader("📚 Répertoire")
                f_r = st.radio("Filtre :", ["Tous", "Actifs", "Inactifs"], horizontal=True)
                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)")
                if f_r == "Actifs": query = query.eq("est_actif", True)
                elif f_r == "Inactifs": query = query.eq("est_
