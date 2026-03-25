import streamlit as st
import pandas as pd
from supabase import create_client, Client

# 1. Configuration et Connexion
st.set_page_config(page_title="RPE Connect - Gestion", page_icon="🌿", layout="wide")

url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

st.title("🌿 Système RPE Connect")

# 2. Menu de navigation
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION 1 : INSCRIPTION ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    
    choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + sorted(list(noms_adh.keys())))
    
    if choix_adh != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).execute()
        if res_at.data:
            for at in res_at.data:
                with st.expander(f"📅 {at['titre']} - {at['date_atelier']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    if st.button("S'inscrire", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("Inscription validée !")
                        st.balloons()
        else:
            st.info("Aucun atelier disponible.")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    password = st.text_input("Code secret", type="password")
    
    if password == "1234":
        t1, t2, t3 = st.tabs(["🏗️ Ateliers", "👥 Gestion des Adhérents", "📍 Configuration"])
        
        # --- ONGLET ADHÉRENTS (MODIFIÉ) ---
        with t2:
            st.subheader("👥 Répertoire des Adhérents")
            
            # Formulaire d'ajout
            with st.expander("➕ Ajouter un nouvel adhérent"):
                with st.form("new_user"):
                    col_n, col_p = st.columns(2)
                    nom_n = col_n.text_input("Nom de famille")
                    pre_n = col_p.text_input("Prénom")
                    col_a, col_adm = st.columns(2)
                    is_act = col_a.checkbox("Compte actif", value=True)
                    is_adm = col_adm.checkbox("Est administrateur", value=False)
                    
                    if st.form_submit_button("Créer la fiche"):
                        if nom_n and pre_n:
                            supabase.table("adherents").insert({
                                "nom": nom_n.upper(), "prenom": pre_n.capitalize(),
                                "est_actif": is_act, "est_admin": is_adm
                            }).execute()
                            st.success("Adhérent ajouté !")
                            st.rerun()
            
            st.divider()

            # Liste et Filtres
            filtre = st.radio("Afficher :", ["Tous", "Actifs uniquement", "Inactifs uniquement"], horizontal=True)
            
            query = supabase.table("adherents").select("*")
            if filtre == "Actifs uniquement":
                query = query.eq("est_actif", True)
            elif filtre == "Inactifs uniquement":
                query = query.eq("est_actif", False)
            
            utilisateurs = query.execute().data
            
            if utilisateurs:
                df = pd.DataFrame(utilisateurs)
                # On réorganise les colonnes pour la lecture
                df = df[['id', 'nom', 'prenom', 'est_actif', 'est_admin']]
                
                for index, row in df.iterrows():
                    with st.container():
                        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                        c1.write(f"**{row['nom']}** {row['prenom']}")
                        
                        # Boutons de modification rapide
                        statut_label = "✅ Actif" if row['est_actif'] else "❌ Inactif"
                        if c2.button(statut_label, key=f"act_{row['id']}"):
                            supabase.table("adherents").update({"est_actif": not row['est_actif']}).eq("id", row['id']).execute()
                            st.rerun()
                            
                        admin_label = "🔑 Admin" if row['est_admin'] else "👤 Membre"
                        if c3.button(admin_label, key=f"adm_{row['id']}"):
                            supabase.table("adherents").update({"est_admin": not row['est_admin']}).eq("id", row['id']).execute()
                            st.rerun()
                            
                        if c4.button("🗑️", key=f"del_{row['id']}"):
                            supabase.table("adherents").delete().eq("id", row['id']).execute()
                            st.rerun()
            else:
                st.info("Aucun adhérent ne correspond à ce filtre.")

        # --- ONGLET ATELIERS ---
        with t1:
            st.subheader("Publier un atelier")
            l_data = supabase.table("lieux").select("*").execute().data
            h_data = supabase.table("horaires").select("*").execute().data
            if l_data and h_data:
                with st.form("at_form"):
                    titre = st.text_input("Titre")
                    dat = st.date_input("Date")
                    l_ch = st.selectbox("Lieu", [l['nom'] for l in l_data])
                    h_ch = st.selectbox("Horaire", [h['libelle'] for h in h_data])
                    if st.form_submit_button("Publier"):
                        l_id = next(i['id'] for i in l_data if i['nom'] == l_ch)
                        h_id = next(i['id'] for i in h_data if i['libelle'] == h_ch)
                        supabase.table("ateliers").insert({"titre": titre, "date_atelier": str(dat), "lieu_id": l_id, "horaire_id": h_id, "est_actif": True}).execute()
                        st.success("Atelier en ligne !")
            else:
                st.warning("Configurez d'abord les Lieux et Horaires.")

        # --- ONGLET CONFIGURATION ---
        with t3:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Lieux")
                nl = st.text_input("Nouveau lieu")
                if st.button("Ajouter Lieu"):
                    supabase.table("lieux").insert({"nom": nl}).execute()
                    st.rerun()
            with col2:
                st.subheader("Horaires")
                nh = st.text_input("Nouveau créneau")
                if st.button("Ajouter Horaire"):
                    supabase.table("horaires").insert({"libelle": nh}).execute()
                    st.rerun()
    else:
        st.info("Entrez le code pour accéder à la gestion.")
