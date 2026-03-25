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
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"

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
                    if st.button("S'inscrire", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("✅ Inscription validée !")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    
    # --- BLOC DE CONNEXION AVEC SECOURS ---
    col_pass, col_forget = st.columns([2, 1])
    with col_pass:
        password_input = st.text_input("Code secret de session", type="password")
    
    with col_forget:
        st.write(" ") # Alignement visuel
        if st.button("Code secret oublié ?"):
            @st.dialog("Récupération du code")
            def recover():
                st.info("Utilisez le code de secours par défaut : 0000")
                rescue = st.text_input("Code de secours", type="password")
                new_c = st.text_input("Nouveau code secret souhaité", type="password")
                if st.button("Réinitialiser le code"):
                    if rescue == "0000" and new_c:
                        supabase.table("configuration").update({"secret_code": new_c}).eq("id", "main_config").execute()
                        st.success("Code modifié ! Veuillez vous reconnecter.")
                        st.rerun()
                    else:
                        st.error("Code de secours invalide.")
            recover()

    if password_input == current_code:
        st.success("Session Administrateur Active")
        t1, t2, t3, t4 = st.tabs(["🏗️ Gestion", "👥 Adhérents", "📍 Lieux & Horaires", "⚙️ Sécurité"])
        
        with t1:
            st.subheader("🚀 Générateur d'ateliers")
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            
            liste_lieux = [l['nom'] for l in l_data]
            liste_horaires = [h['libelle'] for h in h_data]

            if l_data and h_data:
                with st.expander("🛠️ Configurer une série"):
                    c1, c2 = st.columns(2)
                    d_debut = c1.date_input("Du", datetime.now(), format="DD/MM/YYYY")
                    d_fin = c2.date_input("Au", datetime.now() + timedelta(days=14), format="DD/MM/YYYY")
                    jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    titre_base = st.text_input("Titre", value="Atelier Éveil")
                    
                    cl, ch = st.columns(2)
                    lieu_init = cl.selectbox("Lieu par défaut", l_data, format_func=lambda x: x['nom'])
                    hor_init = ch.selectbox("Horaire par défaut", h_data, format_func=lambda x: x['libelle'])
                    
                    if st.button("Générer la liste"):
                        temp = []
                        curr = d_debut
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d_fin:
                            if js_fr[curr.weekday()] in jours:
                                temp.append({
                                    "Date": format_date_fr(curr),
                                    "Titre": titre_base,
                                    "Lieu": lieu_init['nom'],
                                    "Horaire": hor_init['libelle'],
                                    "Capacité": lieu_init['capacite_accueil'],
                                    "Actif": True,
                                    "_raw_date": str(curr)
                                })
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = temp

                if 'at_list' in st.session_state:
                    st.write("### 📋 Révision du tableau")
                    df_ed = pd.DataFrame(st.session_state['at_list'])
                    
                    final_df = st.data_editor(df_ed, hide_index=True, use_container_width=True, column_config={
                        "Date": st.column_config.TextColumn("Date", width="small", disabled=True),
                        "Titre": st.column_config.TextColumn("Titre", width="large"),
                        "Lieu": st.column_config.SelectboxColumn("Lieu", options=liste_lieux, width="medium"),
                        "Horaire": st.column_config.SelectboxColumn("Horaire", options=liste_horaires, width="medium"),
                        "Capacité": st.column_config.NumberColumn("Cap.", width="small", min_value=1),
                        "Actif": st.column_config.CheckboxColumn("Actif", width="small"),
                        "_raw_date": None
                    })
                    
                    c_ok, c_cancel = st.columns(2)
                    if c_ok.button("✅ Valider et Enregistrer"):
                        map_l = {l['nom']: l['id'] for l in l_data}
                        map_h = {h['libelle']: h['id'] for h in h_data}
                        to_db = [{"date_atelier": r['_raw_date'], "titre": r['Titre'], "lieu_id": map_l[r['Lieu']], 
                                  "horaire_id": map_h[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": r['Actif']} 
                                 for _, r in final_df.iterrows()]
                        supabase.table("ateliers").insert(to_db).execute()
                        del st.session_state['at_list']
                        st.success("Planning enregistré !")
                        st.rerun()
                    
                    if c_cancel.button("🗑️ Tout annuler"):
                        del st.session_state['at_list']
                        st.rerun()

        # --- ONGLET 3 : LIEUX & HORAIRES ---
        with t3:
            at_ex = supabase.table("ateliers").select("lieu_id, horaire_id").execute().data
            l_used = {a['lieu_id'] for a in at_ex}
            h_used = {a['horaire_id'] for a in at_ex}
            col_l, col_h = st.columns(2)
            with col_l:
                st.subheader("📍 Lieux")
                with st.expander("➕ Ajouter"):
                    with st.form("fl"):
                        nl, cl = st.text_input("Nom"), st.number_input("Capacité", min_value=1, value=10)
                        if st.form_submit_button("Ajouter"):
                            supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cl, "est_actif": True}).execute()
                            st.rerun()
                for l in l_data:
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
                for h in h_data:
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

        # --- ONGLET 2 : ADHÉRENTS ---
        with t2:
            st.subheader("👥 Répertoire")
            with st.expander("➕ Ajouter"):
                with st.form("new_adh"):
                    n, p = st.text_input("Nom"), st.text_input("Prénom")
                    if st.form_submit_button("Créer"):
                        supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute()
                        st.rerun()
            for u in supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute().data:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 2, 1])
                    c1.write(f"**{u['nom']}** {u['prenom']}")
                    if c2.button("Inactif", key=f"u_{u['id']}"):
                        supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute()
                        st.rerun()
                    if c3.button("🗑️", key=f"du_{u['id']}"):
                        supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute()
                        st.rerun()
        
        with t4:
            st.subheader("⚙️ Code secret")
            with st.form("sec"):
                old, new = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if old == current_code:
                        supabase.table("configuration").update({"secret_code": new}).eq("id", "main_config").execute()
                        st.rerun()
    else:
        st.info("Saisissez le code pour accéder à l'administration.")
