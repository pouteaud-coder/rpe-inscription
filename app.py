import streamlit as st
from supabase import create_client, Client

# 1. Configuration de la page et Connexion
st.set_page_config(page_title="RPE Inscriptions", page_icon="🌿")

# Récupération des secrets Streamlit
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

st.title("🌿 Système d'Inscription RPE")

# 2. Création du Menu (C'est cette ligne qui définit 'menu')
menu = st.sidebar.radio("Navigation", ["Inscription", "Administration"])

# --- SECTION 1 : INSCRIPTION (Côté Assistantes Maternelles) ---
if menu == "Inscription":
    st.header("📝 Formulaire d'Inscription")
    
    # Récupérer la liste des adhérents
    try:
        res_adh = supabase.table("adherents").select("*").eq("est_actif", True).execute()
        noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
        
        choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + sorted(list(noms_adh.keys())))
        
        if choix_adh != "Choisir...":
            # Récupérer les ateliers actifs
            res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).execute()
            
            if res_at.data:
                st.subheader("Ateliers disponibles")
                for at in res_at.data:
                    with st.expander(f"📅 {at['titre']} - {at['date_atelier']}"):
                        st.write(f"🏠 **Lieu :** {at['lieux']['nom']}")
                        st.write(f"⏰ **Horaire :** {at['horaires']['libelle']}")
                        
                        if st.button("S'inscrire à cet atelier", key=f"btn_{at['id']}"):
                            supabase.table("inscriptions").insert({
                                "adherent_id": noms_adh[choix_adh],
                                "atelier_id": at['id']
                            }).execute()
                            st.success("✅ Votre inscription a bien été prise en compte !")
                            st.balloons()
            else:
                st.info("Il n'y a aucun atelier ouvert aux inscriptions pour le moment.")
    except Exception as e:
        st.error(f"Erreur de connexion : Vérifiez vos tables Supabase.")

# --- SECTION 2 : ADMINISTRATION (Votre espace de gestion) ---
elif menu == "Administration":
    st.header("🔐 Espace Gestion")
    
    # Le code est ici dans la zone principale pour plus de clarté
    password = st.text_input("Code secret administrateur", type="password")
    
    if password == "1234":
        st.success("Accès autorisé")
        
        # Onglets de gestion
        t1, t2, t3 = st.tabs(["🏗️ Créer un Atelier", "👥 Gérer les Adhérents", "📍 Lieux & Horaires"])
        
        with t3: # Configuration Lieux et Horaires
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Lieux")
                n_lieu = st.text_input("Nom du lieu")
                if st.button("Ajouter le Lieu"):
                    supabase.table("lieux").insert({"nom": n_lieu}).execute()
                    st.success("Lieu enregistré !")
            with col2:
                st.subheader("Horaires")
                n_horaire = st.text_input("Créneau (ex: 9h30-11h30)")
                if st.button("Ajouter l'Horaire"):
                    supabase.table("horaires").insert({"libelle": n_horaire}).execute()
                    st.success("Horaire enregistré !")

        with t2: # Gestion Adhérents
            st.subheader("Nouvelle inscription RPE")
            with st.form("form_adh"):
                nom = st.text_input("Nom de famille")
                prenom = st.text_input("Prénom")
                if st.form_submit_button("Ajouter l'adhérent"):
                    supabase.table("adherents").insert({
                        "nom": nom.upper(), 
                        "prenom": prenom.capitalize(), 
                        "est_actif": True
                    }).execute()
                    st.success("Adhérent ajouté avec succès !")

        with t1: # Création Ateliers
            st.subheader("Publier un atelier")
            # On récupère les listes pour les menus déroulants
            l_data = supabase.table("lieux").select("*").execute().data
            h_data = supabase.table("horaires").select("*").execute().data
            
            if l_data and h_data:
                with st.form("form_at"):
                    titre = st.text_input("Titre de l'atelier (ex: Éveil Corporel)")
                    date_at = st.date_input("Date")
                    choix_l = st.selectbox("Lieu", [l['nom'] for l in l_data])
                    choix_h = st.selectbox("Horaire", [h['libelle'] for h in h_data])
                    
                    if st.form_submit_button("Mettre en ligne"):
                        # Trouver les IDs correspondants
                        id_l = next(i['id'] for i in l_data if i['nom'] == choix_l)
                        id_h = next(i['id'] for i in h_data if i['libelle'] == choix_h)
                        
                        supabase.table("ateliers").insert({
                            "titre": titre, 
                            "date_atelier": str(date_at),
                            "lieu_id": id_l, 
                            "horaire_id": id_h, 
                            "est_actif": True
                        }).execute()
                        st.success("L'atelier est maintenant visible !")
            else:
                st.warning("⚠️ Avant de créer un atelier, configurez au moins un Lieu et un Horaire.")
    else:
        st.info("Veuillez saisir le code secret pour accéder aux formulaires de saisie.")
