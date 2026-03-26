import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client
import re

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

def parse_date_flexible(date_str):
    """Convertit JJ/MM/AAAA ou format long vers YYYY-MM-DD pour la base de données"""
    date_str = str(date_str).strip()
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
    return str(datetime.now().date())

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
    
    col_in, col_ou = st.columns([3, 1])
    with col_in: password_input = st.text_input("Code secret d'accès", type="password")
    with col_ou:
        st.write(" ")
        if st.button("Code oublié ?"):
            @st.dialog("Récupération")
            def recover():
                r = st.text_input("Code de secours (0000)", type="password")
                n = st.text_input("Nouveau code")
                if st.button("Valider") and r == "0000":
                    supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                    st.rerun()
            recover()

    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1:
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list, h_list = [l['nom'] for l in l_raw], [h['libelle'] for h in h_raw]
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id, map_h_id = {l['nom']: l['id'] for l in l_raw}, {h['libelle']: h['id'] for h in h_raw}

            sub = st.radio("Sous-menu :", ["Générateur", "Répertoire"], horizontal=True)

            conf = {
                "Date": st.column_config.TextColumn("Date", width=220),
                "Titre": st.column_config.TextColumn("Titre", width=320),
                "Lieu": st.column_config.SelectboxColumn("Lieu", options=l_list, width=130),
                "Horaire": st.column_config.SelectboxColumn("Horaire", options=h_list, width=130),
                "Capacité": st.column_config.NumberColumn("Cap.", width=60),
                "Actif": st.column_config.CheckboxColumn("Actif", width=60),
                "_raw_date": None, "ID": None
            }

            if sub == "Générateur":
                c_gen, c_add = st.columns([2, 1])
                with c_gen.expander("🛠️ Générer série"):
                    d1 = st.date_input("Début", datetime.now()); d2 = st.date_input("Fin", d1 + timedelta(days=7))
                    jours_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Lancer la génération"):
                        tmp = []
                        curr = d1
                        while curr <= d2:
                            js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                            if js_fr[curr.weekday()] in jours_sel:
                                tmp.append({"Date": format_date_fr(curr), "Titre": "Atelier Éveil", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa[l_list[0]], "Actif": True, "_raw_date": str(curr)})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = tmp
                        st.rerun()

                with c_add:
                    st.write(" ")
                    if st.button("➕ Ajouter une ligne vierge"):
                        st.session_state['at_list'].append({"Date": datetime.now().strftime("%d/%m/%Y"), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa[l_list[0]], "Actif": True, "_raw_date": str(datetime.now().date())})
                        st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, use_container_width=False, num_rows="dynamic", column_config=conf, key="ed_gen")
                    if st.button("✅ Enregistrer les nouveaux ateliers"):
                        to_db = [{"date_atelier": parse_date_flexible(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": r['Capacité'], "est_actif": r['Actif']} for _, r in res_gen.iterrows() if r['Titre']]
                        supabase.table("ateliers").insert(to_db).execute()
                        st.session_state['at_list'] = []; st.success("Enregistré !"); st.rerun()

            else:
                st.subheader("📚 Répertoire")
                f_r = st.radio("Filtre :", ["Tous", "Actifs", "Inactifs"], horizontal=True)
                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)")
                if f_r == "Actifs": query = query.eq("est_actif", True)
                elif f_r == "Inactifs": query = query.eq("est_actif", False)
                db_d = query.order("date_atelier", desc=True).execute().data
                if db_d:
                    df_r = pd.DataFrame([{"ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Capacité": a['capacite_max'], "Actif": a['est_actif']} for a in db_d])
                    res_r = st.data_editor(df_r, hide_index=True, disabled=["Date"], column_config=conf, key="ed_rep")
                    if st.button("💾 Sauvegarder les modifications"):
                        for _, row in res_r.iterrows():
                            supabase.table("ateliers").update({"titre": row['Titre'], "lieu_id": map_l_id[row['Lieu']], "horaire_id": map_h_id[row['Horaire']], "capacite_max": row['Capacité'], "est_actif": row['Actif']}).eq("id", row['ID']).execute()
                        st.success("Mis à jour !"); st.rerun()

        with t2:
            st.subheader("👥 Gestion des Adhérents")
            with st.form("f_adh"):
                n, p = st.text_input("Nom"), st.text_input("Prénom")
                if st.form_submit_button("Ajouter l'adhérent"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute()
                    st.rerun()
            for u in supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute().data:
                c1, c2 = st.columns([5, 1])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"del_u_{u['id']}"):
                    supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute()
                    st.rerun()

        with t3:
            col_l, col_h = st.columns(2)
            with col_l:
                st.subheader("📍 Lieux")
                with st.form("f_l"):
                    nl, cl = st.text_input("Nom du lieu"), st.number_input("Capacité", min_value=1)
                    if st.form_submit_button("Ajouter le lieu"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cl, "est_actif": True}).execute()
                        st.rerun()
                for l in l_raw:
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"{l['nom']} ({l['capacite_accueil']} pl.)")
                    if c2.button("🗑️", key=f"del_l_{l['id']}"):
                        supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                        st.rerun()
            with col_h:
                st.subheader("⏰ Horaires")
                with st.form("f_h"):
                    nh = st.text_input("Libellé horaire")
                    if st.form_submit_button("Ajouter l'horaire"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute()
                        st.rerun()
                for h in h_raw:
                    c1, c2 = st.columns([3, 1])
                    c1.write(h['libelle'])
                    if c2.button("🗑️", key=f"del_h_{h['id']}"):
                        supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                        st.rerun()

        with t4:
            st.subheader("⚙️ Sécurité")
            with st.form("f_sec"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code mis à jour !"); st.rerun()

    else:
        st.info("Saisissez le code secret pour accéder à l'administration.")
