import streamlit as st
import pandas as pd
from supabase import create_client, Client

# 1. Configuration de la page et Connexion
st.set_page_config(page_title="RPE Connect - Gestion", page_icon="🌿", layout="wide")

url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- FONCTION DE RÉCUPÉRATION DU CODE SECRET ---
def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except:
        return "1234"

current_code = get_secret_code()

st.title("🌿 Système RPE Connect")

# 2. Menu de navigation
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# --- SECTION 1 : INSCRIPTION (CÔTÉ UTILISATEUR) ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    
    # Récupérer les adhérents actifs
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    
    choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + sorted(list(noms_adh.keys())))
    
    if choix_adh != "Choisir...":
        # Récupérer les ateliers actifs avec jointures lieux/horaires
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).execute()
        
        if res_at.data:
            for at in res_at.data:
                with st.expander(f"📅 {at['titre']} - {at['date_atelier']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    if st.button("S'inscrire à cet atelier", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({
                            "adherent_id": noms_adh[choix_adh], 
                            "atelier_id": at['id']
                        }).execute()
                        st.success("✅ Inscription validée !")
                        st.balloons()
        else:
            st.info("Aucun atelier n'est ouvert aux inscriptions pour le moment.")

# --- SECTION 2 : ADMINISTRATION (CÔTÉ GESTION) ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    
    col_pass, col_forget = st.columns([2, 1])
    with col_pass:
        password_input = st.text_input("Code secret de session", type="password")
    
    with col_forget:
        st.write(" ") # Espace pour aligner avec le champ texte
        if st.button("Code secret oublié ?"):
            @st.dialog("Récupération du code secret")
            def recover_code():
                st.warning("Utilisez le code de secours '0000' pour réinitialiser votre accès.")
                rescue = st.text_input("Code de secours", type="password")
                new_c = st.text_input("Définir le nouveau code secret", type="password")
                if st.button("Valider la réinitialisation"):
                    if rescue == "0000":
                        if len(new_c) > 0:
                            supabase.table("configuration").update({"secret_code": new_c}).eq("id", "main_config").execute()
                            st.success("Code réinitialisé ! Veuillez vous reconnecter.")
                            st.rerun()
                        else:
                            st.error("Le nouveau code ne peut pas être vide.")
                    else:
                        st.error("Code de secours incorrect.")
            recover_code()

    # Vérification de l'accès
    if password_input == current_code:
        st.success("Session Administrateur Active")
        
        # Création des onglets demandés
        t1, t2, t3, t4 = st.tabs([
            "🏗️ Gestion des Ateliers", 
            "👥 Gestion des Adhérents", 
            "📍 Gestion Lieux et Horaires", 
            "⚙️ Sécurité"
        ])
        
        # --- ONGLET 1 : GESTION DES ATELIERS ---
        with t1:
            st.subheader("Publier un nouvel atelier")
            l_data = supabase.table("lieux").select("*").execute().data
            h_data = supabase.table("horaires").select("*").execute().data
            
            if l_data and h_data:
                with st.form("at_form"):
                    titre = st.text_input("Titre de l'atelier")
                    dat = st.date_input("Date")
                    l_ch = st.selectbox("Lieu", [l['nom'] for l in l_data])
                    h_ch = st.selectbox("Horaire", [h['libelle'] for h in h_data])
                    if st.form_submit_button("Mettre en ligne"):
                        l_id = next(i['id'] for i in l_data if i['nom'] == l_ch)
                        h_id = next(i['id'] for i in h_data if i['libelle'] == h_ch)
                        supabase.table("ateliers").insert({
                            "titre": titre, "date_atelier": str(dat), 
                            "lieu_id": l_id, "horaire_id": h_id, "est_actif": True
                        }).execute()
                        st.success("Atelier publié !")
            else:
                st.warning("Veuillez d'abord configurer des Lieux et des Horaires.")

        # --- ONGLET 2 : GESTION DES ADHÉRENTS ---
        with t2:
            st.subheader("👥 Répertoire et Statuts")
            
            with st.expander("➕ Ajouter un nouvel adhérent"):
                with st.form("new_user"):
                    c_n, c_p = st.columns(2)
                    nom_n = c_n.text_input("Nom de famille")
                    pre_n = c_p.text_input("Prénom")
                    c_a, c_adm = st.columns(2)
                    is_act = c_a.checkbox("Compte actif", value=True)
                    is_adm = c_adm.checkbox("Accès Administrateur", value=False)
                    if st.form_submit_button("Enregistrer"):
                        if nom_n and pre_n:
                            supabase.table("adherents").insert({
                                "nom": nom_n.upper(), "prenom": pre_n.capitalize(), 
                                "est_actif": is_act, "est_admin": is_adm
                            }).execute()
                            st.success("Fiche créée !")
                            st.rerun()

            st.divider()
            filtre = st.radio("Filtrer la liste :", ["Tous", "Actifs", "Inactifs"], horizontal=True)
            
            query = supabase.table("adherents").select("*")
            if filtre == "Actifs": query = query.eq("est_actif", True)
            elif filtre == "Inactifs": query = query.eq("est_actif", False)
            
            utilisateurs = query.execute().data
            
            if utilisateurs:
                for row in utilisateurs:
                    with st.container():
                        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                        c1.write(f"**{row['nom']}** {row['prenom']}")
                        
                        # Bouton Actif/Inactif
                        st_lab = "✅ Actif" if row['est_actif'] else "❌ Inactif"
                        if c2.button(st_lab, key=f"act_{row['id']}"):
                            supabase.table("adherents").update({"est_actif": not row['est_actif']}).eq("id", row['id']).execute()
                            st.rerun()
                        
                        # Bouton Admin/Membre
                        ad_lab = "🔑 Admin" if row['est_admin'] else "👤 Membre"
                        if c3.button(ad_lab, key=f"adm_{row['id']}"):
                            supabase.table("adherents").update({"est_admin": not row['est_admin']}).eq("id", row['id']).execute()
                            st.rerun()

                        # Bouton Suppression
                        if c4.button("🗑️", key=f"del_req_{row['id']}"):
                            @st.dialog(f"Supprimer {row['prenom']} ?")
                            def confirm_del(aid, aname):
                                st.error(f"Suppression définitive de **{aname}**")
                                cd = st.text_input("Saisissez le code secret pour confirmer", type="password")
                                if st.button("Confirmer la suppression"):
                                    if cd == current_code:
                                        supabase.table("adherents").delete().eq("id", aid).execute()
                                        st.rerun()
                                    else:
                                        st.error("Code incorrect.")
                            confirm_del(row['id'], f"{row['prenom']} {row['nom']}")
            else:
                st.info("Aucun résultat.")

        # --- ONGLET 3 : GESTION LIEUX ET HORAIRES ---
        with t3:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Lieux")
                nl = st.text_input("Nom de la salle/lieu")
                if st.button("Enregistrer le Lieu"):
                    supabase.table("lieux").insert({"nom": nl}).execute()
                    st.success("Lieu ajouté.")
                    st.rerun()
            with col2:
                st.subheader("Horaires")
                nh = st.text_input("Libellé horaire (ex: 9h-11h)")
                if st.button("Enregistrer l'Horaire"):
                    supabase.table("horaires").insert({"libelle": nh}).execute()
                    st.success("Horaire ajouté.")
                    st.rerun()

        # --- ONGLET 4 : SÉCURITÉ ---
        with t4:
            st.subheader("⚙️ Modification du code d'accès")
            with st.form("security_form"):
                old_p = st.text_input("Ancien code secret", type="password")
                new_p = st.text_input("Nouveau code secret", type="password")
                conf_p = st.text_input("Confirmer le nouveau code", type="password")
                if st.form_submit_button("Mettre à jour le code secret"):
                    if old_p == current_code:
                        if new_p == conf_p and len(new_p) > 0:
                            supabase.table("configuration").update({"secret_code": new_p}).eq("id", "main_config").execute()
                            st.success("Code modifié avec succès !")
                            st.rerun()
                        else:
                            st.error("Les codes ne correspondent pas ou sont vides.")
                    else:
                        st.error("L'ancien code est incorrect.")
    else:
        if password_input:
            st.error("Code secret incorrect.")
        st.info("Veuillez saisir votre code pour accéder aux outils d'administration.")
