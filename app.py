import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect - Gestion", page_icon="🌿", layout="wide")

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
                    st.write(f"👥 **Places :** {at['capacite_max']}")
                    if st.button("S'inscrire", key=f"at_{at['id']}"):
                        supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                        st.success("✅ Inscription validée !")
        else:
            st.info("Aucun atelier disponible.")

# --- SECTION 2 : ADMINISTRATION ---
elif menu == "🔐 Administration":
    st.header("🔐 Espace de Gestion")
    password_input = st.text_input("Code secret de session", type="password")

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Gestion des Ateliers", "👥 Gestion des Adhérents", "📍 Lieux et Horaires", "⚙️ Sécurité"])
        
        # --- ONGLET 1 : GESTION DES ATELIERS ---
        with t1:
            st.subheader("🚀 Générateur d'ateliers en série")
            # Chargement des données pour les listes
            l_data = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_data = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            
            if l_data and h_data:
                with st.expander("🛠️ Configurer une série"):
                    c1, c2 = st.columns(2)
                    d_debut = c1.date_input("Du (jj/mm/aaaa)", datetime.now(), format="DD/MM/YYYY")
                    d_fin = c2.date_input("Au (jj/mm/aaaa)", datetime.now() + timedelta(days=14), format="DD/MM/YYYY")
                    
                    jours = st.multiselect("Jours de la semaine", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    titre_base = st.text_input("Titre de l'atelier")
                    
                    col_l, col_h = st.columns(2)
                    lieu_sel = col_l.selectbox("Lieu", l_data, format_func=lambda x: f"{x['nom']} (Cap: {x['capacite_accueil']})")
                    hor_sel = col_h.selectbox("Horaire", h_data, format_func=lambda x: x['libelle'])
                    
                    if st.button("Préparer la liste"):
                        temp = []
                        curr = d_debut
                        js_map = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d_fin:
                            if js_map[curr.weekday()] in jours:
                                temp.append({
                                    "Date": curr,
                                    "Titre": titre_base,
                                    "Lieu": lieu_sel['nom'],
                                    "Horaire": hor_sel['libelle'],
                                    "Capacité": lieu_sel['capacite_accueil'],
                                    "Actif": True,
                                    "_lieu_id": lieu_sel['id'],      # Caché
                                    "_horaire_id": hor_sel['id']     # Caché
                                })
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = temp

                if 'at_list' in st.session_state:
                    st.write("### 📋 Révision du tableau d'ateliers")
                    df_ed = pd.DataFrame(st.session_state['at_list'])
                    
                    final_df = st.data_editor(df_ed, hide_index=True, column_config={
                        "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                        "Titre": st.column_config.TextColumn("Titre"),
                        "Lieu": st.column_config.TextColumn("Lieu", disabled=True),
                        "Horaire": st.column_config.TextColumn("Horaire", disabled=True),
                        "Capacité": st.column_config.NumberColumn("Capacité", min_value=1),
                        "Actif": st.column_config.CheckboxColumn("Actif"),
                        "_lieu_id": None, "_horaire_id": None # On cache les IDs techniques
                    })
                    
                    if st.button("✅ Enregistrer tout le tableau"):
                        to_db = []
                        for _, row in final_df.iterrows():
                            to_db.append({
                                "date_atelier": str(row['Date']),
                                "titre": row['Titre'],
                                "lieu_id": row['_lieu_id'],
                                "horaire_id": row['_horaire_id'],
                                "capacite_max": row['Capacité'],
                                "est_actif": row['Actif']
                            })
                        supabase.table("ateliers").insert(to_db).execute()
                        del st.session_state['at_list']
                        st.success("Planning enregistré !")
                        st.rerun()

        # --- ONGLET 3 : LIEUX & HORAIRES ---
        with t3:
            at_ex = supabase.table("ateliers").select("lieu_id, horaire_id").execute().data
            l_used = {a['lieu_id'] for a in at_ex}
            h_used = {a['horaire_id'] for a in at_ex}

            cl_l, cl_h = st.columns(2)
            with cl_l:
                st.subheader("📍 Gestion des Lieux")
                with st.expander("➕ Ajouter"):
                    with st.form("fl"):
                        nl, cl = st.text_input("Nom"), st.number_input("Capacité", min_value=1, value=10)
                        if st.form_submit_button("Ajouter"):
                            supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cl, "est_actif": True}).execute()
                            st.rerun()
                
                # LISTE TRIÉE PAR ORDRE ALPHABÉTIQUE
                for l in supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data:
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

            with cl_h:
                st.subheader("⏰ Gestion des Horaires")
                # (Idem pour les horaires...)
                with st.expander("➕ Ajouter"):
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

        # --- ONGLET 2 (ADHÉRENTS) & 4 (SÉCURITÉ) ---
        with t2:
            st.subheader("👥 Répertoire des Adhérents")
            with st.expander("➕ Ajouter un adhérent"):
                with st.form("new_adh"):
                    n, p = st.text_input("Nom"), st.text_input("Prénom")
                    if st.form_submit_button("Créer"):
                        supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True, "est_admin": False}).execute()
                        st.rerun()
            for u in supabase.table("adherents").select("*").order("nom").execute().data:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 2, 1])
                    c1.write(f"**{u['nom']}** {u['prenom']}")
                    if c2.button("✅" if u['est_actif'] else "❌", key=f"u_{u['id']}"):
                        supabase.table("adherents").update({"est_actif": not u['est_actif']}).eq("id", u['id']).execute()
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
