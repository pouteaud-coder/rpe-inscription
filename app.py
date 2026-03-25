import streamlit as st
import pandas as pd
from supabase import create_client, Client

# 1. Configuration et Connexion
st.set_page_config(page_title="RPE Connect - Gestion", page_icon="🌿", layout="wide")

url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# Récupération sécurisée du code secret
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

# --- SECTION 1 : INSCRIPTION ---
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    
    # On ne montre que les adhérents actifs
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    
    choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + sorted(list(noms_adh.keys())))
    
    if choix_adh != "Choisir...":
        # On ne montre que les ateliers actifs
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).execute()
        if res_at.data:
            st.subheader("Ateliers disponibles")
            for at in res_at.data:
                with st.expander(f"📅 {at['titre']} - {at['date_atelier']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    if st.button("S'inscrire", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("✅ Inscription validée !")
        else:
            st.info("Aucun atelier disponible pour le moment.")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
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
                if st.button("Valider la réinitialisation"):
                    if rescue == "0000" and new_c:
                        supabase.table("configuration").update({"secret_code": new_c}).eq("id", "main_config").execute()
                        st.success("Code modifié ! Reconnectez-vous.")
                        st.rerun()
            recover()

    if password_input == current_code:
        st.success("Session Administrateur Active")
        t1, t2, t3, t4 = st.tabs(["🏗️ Gestion des Ateliers", "👥 Gestion des Adhérents", "📍 Gestion Lieux et Horaires", "⚙️ Sécurité"])
        
        # --- ONGLET 1 : GESTION DES ATELIERS ---
        with t1:
            st.subheader("Publier un nouvel atelier")
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            
            if l_data and h_data:
                with st.form("at_form"):
                    titre = st.text_input("Titre")
                    dat = st.date_input("Date")
                    l_ch = st.selectbox("Lieu", [l['nom'] for l in l_data])
                    h_ch = st.selectbox("Horaire", [h['libelle'] for h in h_data])
                    if st.form_submit_button("Mettre en ligne"):
                        l_id = next(i['id'] for i in l_data if i['nom'] == l_ch)
                        h_id = next(i['id'] for i in h_data if i['libelle'] == h_ch)
                        supabase.table("ateliers").insert({"titre": titre, "date_atelier": str(dat), "lieu_id": l_id, "horaire_id": h_id, "est_actif": True}).execute()
                        st.success("Atelier publié !")
            else:
                st.warning("⚠️ Aucun Lieu ou Horaire actif trouvé. Configurez-les d'abord.")

        # --- ONGLET 2 : GESTION DES ADHÉRENTS ---
        with t2:
            st.subheader("👥 Répertoire")
            with st.expander("➕ Ajouter un adhérent"):
                with st.form("new_u"):
                    n, p = st.text_input("Nom"), st.text_input("Prénom")
                    if st.form_submit_button("Enregistrer"):
                        supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True, "est_admin": False}).execute()
                        st.rerun()
            
            filtre_adh = st.radio("Afficher adhérents :", ["Actifs", "Inactifs", "Tous"], horizontal=True)
            q_adh = supabase.table("adherents").select("*")
            if filtre_adh == "Actifs": q_adh = q_adh.eq("est_actif", True)
            elif filtre_adh == "Inactifs": q_adh = q_adh.eq("est_actif", False)
            users = q_adh.execute().data
            
            for u in users:
                c1, c2, c3 = st.columns([4, 2, 1])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("✅ Actif" if u['est_actif'] else "❌ Inactif", key=f"u_{u['id']}"):
                    supabase.table("adherents").update({"est_actif": not u['est_actif']}).eq("id", u['id']).execute()
                    st.rerun()
                if c3.button("🗑️", key=f"udel_{u['id']}"):
                    @st.dialog(f"Désactiver {u['prenom']} ?")
                    def conf_u(uid):
                        st.warning("L'adhérent ne sera plus visible mais son historique sera conservé.")
                        if st.button("Confirmer"):
                            supabase.table("adherents").update({"est_actif": False}).eq("id", uid).execute()
                            st.rerun()
                    conf_u(u['id'])

        # --- ONGLET 3 : GESTION LIEUX ET HORAIRES (AFFICHAGE FILTRÉ) ---
        with t3:
            col_l, col_h = st.columns(2)
            
            with col_l:
                st.subheader("📍 Lieux")
                nl = st.text_input("Nouveau lieu")
                if st.button("Ajouter Lieu"):
                    supabase.table("lieux").insert({"nom": nl, "est_actif": True}).execute()
                    st.rerun()
                
                st.write("**Lieux actifs :**")
                # ON NE MONTRE QUE LES ACTIFS DANS LA LISTE
                active_l = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
                for l in active_l:
                    cl1, cl2 = st.columns([4, 1])
                    cl1.write(f"- {l['nom']}")
                    if cl2.button("🗑️", key=f"dell_{l['id']}"):
                        supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                        st.success("Lieu masqué.")
                        st.rerun()

            with col_h:
                st.subheader("⏰ Horaires")
                nh = st.text_input("Nouveau créneau")
                if st.button("Ajouter Horaire"):
                    supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute()
                    st.rerun()
                
                st.write("**Horaires actifs :**")
                # ON NE MONTRE QUE LES ACTIFS DANS LA LISTE
                active_h = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
                for h in active_h:
                    ch1, ch2 = st.columns([4, 1])
                    ch1.write(f"- {h['libelle']}")
                    if ch2.button("🗑️", key=f"delh_{h['id']}"):
                        supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                        st.success("Horaire masqué.")
                        st.rerun()

        # --- ONGLET 4 : SÉCURITÉ ---
        with t4:
            st.subheader("⚙️ Paramètres")
            with st.form("sec_f"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code secret"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.rerun()
    else:
        st.info("Saisissez le code pour gérer l'application.")
        
