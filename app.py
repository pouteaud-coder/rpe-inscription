import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# 1. Configuration - Interface large
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

current_code = get_secret_code()

# --- INITIALISATION SESSION ---
if 'at_list' not in st.session_state:
    st.session_state['at_list'] = []

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION 1 : INSCRIPTION ---
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
    
    # BLOC CONNEXION STABLE
    col_p, col_f = st.columns([2, 1])
    with col_p: password_input = st.text_input("Code secret d'accès", type="password")
    with col_f:
        st.write(" ")
        if st.button("Code oublié ?"):
            @st.dialog("Récupération")
            def recover():
                rescue = st.text_input("Code de secours (0000)", type="password")
                new_c = st.text_input("Nouveau code souhaité", type="password")
                if st.button("Réinitialiser"):
                    if rescue == "0000":
                        supabase.table("configuration").update({"secret_code": new_c}).eq("id", "main_config").execute()
                        st.rerun()
            recover()

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1:
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            liste_l = [l['nom'] for l in l_data]; liste_h = [h['libelle'] for h in h_data]
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_data}
            map_l_id = {l['nom']: l['id'] for l in l_data}
            map_h_id = {h['libelle']: h['id'] for h in h_data}

            # SOUS-NAVIGATION DANS ATELIERS
            mode_atelier = st.radio("Action :", ["Nouveaux Ateliers (Générateur)", "Répertoire (Voir & Modifier)"], horizontal=True)
            
            # --- MODE 1 : GÉNÉRATEUR ---
            if mode_atelier == "Nouveaux Ateliers (Générateur)":
                st.subheader("🚀 Création de sessions")
                with st.expander("🛠️ Paramètres de génération"):
                    c1, c2 = st.columns(2)
                    d_deb = c1.date_input("Début", datetime.now(), format="DD/MM/YYYY")
                    d_fin = c2.date_input("Fin", d_deb + timedelta(days=7), format="DD/MM/YYYY")
                    jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    
                    cg1, cg2 = st.columns(2)
                    if cg1.button("📊 Générer la série"):
                        temp = []
                        curr = d_deb
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d_fin:
                            if js_fr[curr.weekday()] in jours:
                                temp.append({"Date": format_date_fr(curr), "Titre": "Atelier Éveil", "Lieu": liste_l[0], "Horaire": liste_h[0], "Capacité": map_capa[liste_l[0]], "Actif": True, "_raw_date": str(curr)})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = temp
                        st.rerun()

                    if cg2.button("➕ Ajouter une ligne vierge"):
                        st.session_state['at_list'].append({"Date": format_date_fr(datetime.now()), "Titre": "", "Lieu": liste_l[0], "Horaire": liste_h[0], "Capacité": map_capa[liste_l[0]], "Actif": True, "_raw_date": str(datetime.now().date())})
                        st.rerun()

                if st.session_state['at_list']:
                    st.write("### 📋 Brouillon avant publication")
                    res_df = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, use_container_width=True, num_rows="dynamic",
                        column_config={
                            "Date": st.column_config.TextColumn("Date", width="medium"),
                            "Titre": st.column_config.TextColumn("Titre", width="large"),
                            "Lieu": st.column_config.SelectboxColumn("Lieu", options=liste_l, width="medium"),
                            "Horaire": st.column_config.SelectboxColumn("Horaire", options=liste_h, width="small"),
                            "Capacité": st.column_config.NumberColumn("Cap.", width="small"),
                            "Actif": st.column_config.CheckboxColumn("Actif", width="small"),
                            "_raw_date": None
                        }, key="gen_editor")

                    # Auto-capacité logic
                    if not res_df.equals(pd.DataFrame(st.session_state['at_list'])):
                        for i, row in res_df.iterrows():
                            if i < len(st.session_state['at_list']) and row['Lieu'] != st.session_state['at_list'][i]['Lieu']:
                                res_df.at[i, 'Capacité'] = map_capa.get(row['Lieu'], 10)
                        st.session_state['at_list'] = res_df.to_dict(orient='records')
                        st.rerun()

                    c_pub, c_ann = st.columns(2)
                    if c_pub.button("✅ Publier ces ateliers"):
                        to_db = [{"date_atelier": r.get('_raw_date', str(datetime.now().date())), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": r['Actif']} for _, r in res_df.iterrows() if r['Titre']]
                        supabase.table("ateliers").insert(to_db).execute()
                        st.session_state['at_list'] = []; st.success("Publié !"); st.rerun()
                    if c_ann.button("🗑️ Annuler tout"):
                        st.session_state['at_list'] = []; st.rerun()

            # --- MODE 2 : RÉPERTOIRE (VOIR & MODIFIER) ---
            else:
                st.subheader("📚 Répertoire des Ateliers existants")
                filtre = st.radio("Afficher :", ["Tous", "Actifs uniquement", "Inactifs uniquement"], horizontal=True)
                
                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)")
                if filtre == "Actifs uniquement": query = query.eq("est_actif", True)
                elif filtre == "Inactifs uniquement": query = query.eq("est_actif", False)
                
                data_db = query.order("date_atelier", desc=True).execute().data
                
                if data_db:
                    df_db = pd.DataFrame([{
                        "ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'],
                        "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'],
                        "Cap.": a['capacite_max'], "Actif": a['est_actif']
                    } for a in data_db])
                    
                    st.info("💡 Modifiez directement les cellules ci-dessous puis cliquez sur 'Enregistrer' en bas.")
                    df_mod = st.data_editor(df_db, hide_index=True, use_container_width=True, disabled=["ID", "Date"],
                        column_config={
                            "ID": None, "Titre": st.column_config.TextColumn("Titre", width="large"),
                            "Lieu": st.column_config.SelectboxColumn("Lieu", options=liste_l, width="medium"),
                            "Horaire": st.column_config.SelectboxColumn("Horaire", options=liste_h, width="small"),
                            "Cap.": st.column_config.NumberColumn("Cap.", width="small"),
                            "Actif": st.column_config.CheckboxColumn("Actif", width="small")
                        }, key="db_editor")
                    
                    if st.button("💾 Enregistrer les modifications du répertoire"):
                        for _, row in df_mod.iterrows():
                            # Mise à jour ligne par ligne dans Supabase
                            supabase.table("ateliers").update({
                                "titre": row['Titre'], "lieu_id": map_l_id[row['Lieu']],
                                "horaire_id": map_h_id[row['Horaire']], "capacite_max": row['Cap.'],
                                "est_actif": row['Actif']
                            }).eq("id", row['ID']).execute()
                        st.success("Base de données mise à jour !"); st.rerun()
                else: st.warning("Aucun atelier trouvé.")

        # --- ONGLET 2 : ADHÉRENTS ---
        with t2:
            st.subheader("👥 Adhérents")
            with st.expander("➕ Nouveau"):
                with st.form("adh_f"):
                    n, p = st.text_input("Nom"), st.text_input("Prénom")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute()
                        st.rerun()
            for u in supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute().data:
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    c1.write(f"{u['nom']} {u['prenom']}")
                    if c2.button("🗑️", key=f"u_{u['id']}"):
                        supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute()
                        st.rerun()

        # --- ONGLET 3 : LIEUX / HORAIRES ---
        with t3:
            col_l, col_h = st.columns(2)
            with col_l:
                st.subheader("📍 Lieux")
                with st.expander("➕ Nouveau Lieu"):
                    with st.form("l_f"):
                        nl, cl = st.text_input("Nom"), st.number_input("Capacité", min_value=1, value=10)
                        if st.form_submit_button("OK"):
                            supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cl, "est_actif": True}).execute()
                            st.rerun()
                for l in l_data:
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"{l['nom']} ({l['capacite_accueil']} pl.)")
                        if c2.button("🗑️", key=f"l_{l['id']}"):
                            supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                            st.rerun()
            with col_h:
                st.subheader("⏰ Horaires")
                with st.expander("➕"):
                    with st.form("h_f"):
                        nh = st.text_input("Libellé")
                        if st.form_submit_button("OK"):
                            supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute()
                            st.rerun()
                for h in h_data:
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        c1.write(h['libelle'])
                        if c2.button("🗑️", key=f"h_{h['id']}"):
                            supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                            st.rerun()

        # --- ONGLET 4 : SÉCURITÉ ---
        with t4:
            with st.form("sec"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.rerun()
    else: st.info("Veuillez saisir le code secret d'administration.")
