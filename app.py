import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect - Gestion Totale", page_icon="🌿", layout="wide")

# Connexion Supabase
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
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    # Gestion si la date arrive sous forme de string ou d'objet date
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"

current_code = get_secret_code()

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
                with st.expander(f"📅 {format_date_fr(at['date_atelier'])} - {at['titre']}"):
                    st.write(f"🏠 **Lieu :** {at['lieux']['nom']} | ⏰ **Horaire :** {at['horaires']['libelle']}")
                    st.write(f"👥 **Places disponibles :** {at['capacite_max']}")
                    if st.button("Confirmer l'inscription", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("✅ Inscription validée !")
        else:
            st.info("Aucun atelier disponible.")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    
    col_pass, col_forget = st.columns([2, 1])
    with col_pass:
        password_input = st.text_input("Code secret de session", type="password")
    
    with col_forget:
        st.write(" ")
        if st.button("Code secret oublié ?"):
            @st.dialog("Récupération du code")
            def recover():
                rescue = st.text_input("Code de secours (0000)", type="password")
                new_c = st.text_input("Nouveau code secret", type="password")
                if st.button("Réinitialiser"):
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
            st.subheader("🚀 Générateur d'ateliers en série")
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            
            if l_data and h_data:
                with st.expander("🛠️ Configurer une série d'ateliers"):
                    c1, c2 = st.columns(2)
                    d_debut = c1.date_input("Du", datetime.now())
                    d_fin = c2.date_input("Au", datetime.now() + timedelta(days=14))
                    jours = st.multiselect("Jours de la semaine", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    
                    titre_at = st.text_input("Titre de l'atelier")
                    col_l, col_h = st.columns(2)
                    lieu_sel = col_l.selectbox("Lieu par défaut", l_data, format_func=lambda x: f"{x['nom']} (Cap: {x['capacite_accueil']})")
                    horaire_sel = col_h.selectbox("Horaire", h_data, format_func=lambda x: x['libelle'])
                    
                    if st.button("Préparer la liste"):
                        temp_list = []
                        curr = d_debut
                        js_map = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d_fin:
                            if js_map[curr.weekday()] in jours:
                                # CRITIQUE : On garde l'objet date ici, pas de string !
                                temp_list.append({
                                    "date_atelier": curr, 
                                    "titre": titre_at, 
                                    "lieu_id": lieu_sel['id'], 
                                    "horaire_id": horaire_sel['id'], 
                                    "capacite_max": lieu_sel['capacite_accueil'], 
                                    "est_actif": True
                                })
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = temp_list

                if 'at_list' in st.session_state:
                    st.write("### 📋 Modifier avant publication")
                    df_ed = pd.DataFrame(st.session_state['at_list'])
                    
                    # Le data_editor accepte maintenant les dates car elles sont au bon format
                    final_df = st.data_editor(df_ed, hide_index=True, column_config={
                        "date_atelier": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                        "titre": "Titre",
                        "capacite_max": st.column_config.NumberColumn("Capacité"),
                        "est_actif": "Actif ?",
                        "lieu_id": None, "horaire_id": None
                    })
                    
                    if st.button("✅ Enregistrer les ateliers"):
                        # Conversion des dates en texte juste avant l'envoi à Supabase
                        data_to_send = final_df.copy()
                        data_to_send['date_atelier'] = data_to_send['date_atelier'].astype(str)
                        
                        supabase.table("ateliers").insert(data_to_send.to_dict(orient='records')).execute()
                        del st.session_state['at_list']
                        st.success("Ateliers créés avec succès !")
                        st.rerun()
            else:
                st.warning("Créez d'abord des lieux et horaires actifs.")

        # --- ONGLET 2 : GESTION DES ADHÉRENTS ---
        with t2:
            st.subheader("👥 Répertoire")
            with st.expander("➕ Ajouter un adhérent"):
                with st.form("new_adh"):
                    n, p = st.text_input("Nom"), st.text_input("Prénom")
                    if st.form_submit_button("Créer"):
                        supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True, "est_admin": False}).execute()
                        st.rerun()
            
            f_adh = st.radio("Filtre :", ["Actifs", "Inactifs", "Tous"], horizontal=True)
            q = supabase.table("adherents").select("*")
            if f_adh == "Actifs": q = q.eq("est_actif", True)
            elif f_adh == "Inactifs": q = q.eq("est_actif", False)
            
            for u in q.execute().data:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 2, 1])
                    c1.write(f"**{u['nom']}** {u['prenom']}")
                    if c2.button("✅ Actif" if u['est_actif'] else "❌ Inactif", key=f"u_{u['id']}"):
                        supabase.table("adherents").update({"est_actif": not u['est_actif']}).eq("id", u['id']).execute()
                        st.rerun()
                    if c3.button("🗑️", key=f"du_{u['id']}"):
                        @st.dialog("Désactiver ?")
                        def conf_u(uid):
                            if st.button("Confirmer"):
                                supabase.table("adherents").update({"est_actif": False}).eq("id", uid).execute()
                                st.rerun()
                        conf_u(u['id'])

        # --- ONGLET 3 : LIEUX & HORAIRES ---
        with t3:
            at_ex = supabase.table("ateliers").select("lieu_id, horaire_id").execute().data
            l_used = {a['lieu_id'] for a in at_ex}
            h_used = {a['horaire_id'] for a in at_ex}

            col_l, col_h = st.columns(2)
            with col_l:
                st.subheader("📍 Lieux")
                with st.expander("➕ Nouveau"):
                    with st.form("fl"):
                        nl, cl = st.text_input("Nom"), st.number_input("Capacité", min_value=1, value=10)
                        if st.form_submit_button("Ajouter"):
                            supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cl, "est_actif": True}).execute()
                            st.rerun()
                for l in supabase.table("lieux").select("*").eq("est_actif", True).execute().data:
                    lock = l['id'] in l_used
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        nn = c1.text_input("Nom", value=l['nom'], key=f"ln_{l['id']}", disabled=lock)
                        nc = c1.number_input("Capacité", value=l['capacite_accueil'], key=f"lc_{l['id']}", disabled=lock)
                        if not lock and c2.button("💾", key=f"sl_{l['id']}"):
                            supabase.table("lieux").update({"nom": nn, "capacite_accueil": nc}).eq("id", l['id']).execute()
                            st.rerun()
                        if c2.button("🗑️", key=f"dll_{l['id']}"):
                            supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                            st.rerun()

            with col_h:
                st.subheader("⏰ Horaires")
                with st.expander("➕ Nouveau"):
                    with st.form("fh"):
                        nh = st.text_input("Libellé")
                        if st.form_submit_button("Ajouter"):
                            supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute()
                            st.rerun()
                for h in supabase.table("horaires").select("*").eq("est_actif", True).execute().data:
                    lock_h = h['id'] in h_used
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        nhl = c1.text_input("Horaire", value=h['libelle'], key=f"hn_{h['id']}", disabled=lock_h)
                        if not lock_h and c2.button("💾", key=f"sh_{h['id']}"):
                            supabase.table("horaires").update({"libelle": nhl}).eq("id", h['id']).execute()
                            st.rerun()
                        if c2.button("🗑️", key=f"dh_{h['id']}"):
                            supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                            st.rerun()

        # --- ONGLET 4 : SÉCURITÉ ---
        with t4:
            st.subheader("⚙️ Code secret")
            with st.form("sec"):
                old, new = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if old == current_code:
                        supabase.table("configuration").update({"secret_code": new}).eq("id", "main_config").execute()
                        st.success("Code modifié !")
                        st.rerun()
    else:
        st.info("Saisissez le code pour accéder à l'administration.")
