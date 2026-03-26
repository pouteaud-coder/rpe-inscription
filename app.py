import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration
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

def parse_date_fr_to_iso(date_str):
    """Convertit 'Jeudi 2 avril 2026' en '2026-04-02'"""
    date_str = str(date_str).lower()
    mois_map = {
        "janvier":"01", "février":"02", "mars":"03", "avril":"04", "mai":"05", "juin":"06", 
        "juillet":"07", "août":"08", "septembre":"09", "octobre":"10", "novembre":"11", "décembre":"12"
    }
    # Extraction propre du jour, mois et année peu importe le jour de la semaine devant
    match = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", date_str)
    if match:
        day, month_str, year = match.groups()
        month = mois_map.get(month_str, "01")
        return f"{year}-{month}-{day.zfill(2)}"
    return str(date.today())

# --- INITIALISATION SESSION ---
if 'at_list' not in st.session_state:
    st.session_state['at_list'] = []

current_code = get_secret_code()

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    choix_adh = st.selectbox("Sélectionnez votre nom", ["Choisir..."] + list(noms_adh.keys()))
    if choix_adh != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).order("date_atelier").execute()
        for at in res_at.data:
            with st.expander(f"📅 {format_date_fr(at['date_atelier'])} - {at['titre']}"):
                if st.button("Confirmer l'inscription", key=f"reg_{at['id']}"):
                    supabase.table("inscriptions").insert({"adherent_id": noms_adh[choix_adh], "atelier_id": at['id']}).execute()
                    st.success("✅ Inscription validée !")

elif menu == "🔐 Administration":
    col_in, col_ou = st.columns([3, 1])
    with col_in: password_input = st.text_input("Code secret d'accès", type="password")
    if password_input == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1:
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]
            h_list = [h['libelle'] for h in h_raw]
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}
            map_h_id = {h['libelle']: h['id'] for h in h_raw}

            sub = st.radio("Sous-menu :", ["Générateur", "Répertoire"], horizontal=True)

            # Configuration des colonnes SANS le paramètre 'placeholder'
            conf = {
                "Date": st.column_config.TextColumn("Date", width=200),
                "Titre": st.column_config.TextColumn("Titre (obligatoire)", width=300),
                "Lieu": st.column_config.SelectboxColumn("Lieu", options=l_list, width=120),
                "Horaire": st.column_config.SelectboxColumn("Horaire", options=h_list, width=120),
                "Capacité": st.column_config.NumberColumn("Cap.", width=60),
                "Actif": st.column_config.CheckboxColumn("Actif", width=60),
                "Select": st.column_config.CheckboxColumn("Sél.", width=50),
                "ID": None
            }

            if sub == "Générateur":
                with st.expander("🛠️ Paramétrer une série"):
                    d1 = st.date_input("Début", date.today(), format="DD/MM/YYYY")
                    d2 = st.date_input("Fin", d1 + timedelta(days=7), format="DD/MM/YYYY")
                    js_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Générer"):
                        tmp = []
                        curr = d1
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d2:
                            if js_fr[curr.weekday()] in js_sel:
                                tmp.append({"Select": False, "Date": format_date_fr(curr), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa[l_list[0]], "Actif": True})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = tmp
                        st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, num_rows="dynamic", column_config=conf, key="ed_gen")
                    
                    # Logique de mise à jour de capacité si le lieu change
                    for i, row in res_gen.iterrows():
                        if i < len(st.session_state['at_list']) and row['Lieu'] != st.session_state['at_list'][i]['Lieu']:
                            res_gen.at[i, 'Capacité'] = map_capa.get(row['Lieu'], 10)
                            st.session_state['at_list'] = res_gen.to_dict(orient='records')
                            st.rerun()

                    c_save, c_plus, c_del = st.columns([1, 1.5, 2])
                    if c_save.button("✅ Enregistrer"):
                        to_db = []
                        for _, r in res_gen.iterrows():
                            if r['Titre'] and not r['Select']: # On n'enregistre que si le titre est rempli
                                to_db.append({
                                    "date_atelier": parse_date_fr_to_iso(r['Date']), 
                                    "titre": r['Titre'], 
                                    "lieu_id": map_l_id[r['Lieu']], 
                                    "horaire_id": map_h_id[r['Horaire']], 
                                    "capacite_max": r['Capacité'], 
                                    "est_actif": r['Actif']
                                })
                        if to_db:
                            supabase.table("ateliers").insert(to_db).execute()
                            st.session_state['at_list'] = []; st.success("Enregistré !"); st.rerun()

                    if c_plus.button("➕ Ligne vide"):
                        st.session_state['at_list'].append({"Select": False, "Date": format_date_fr(date.today()), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa[l_list[0]], "Actif": True})
                        st.rerun()

                    selected_indices = res_gen[res_gen['Select'] == True].index.tolist()
                    if selected_indices and c_del.button(f"🗑️ Retirer ({len(selected_indices)})", type="primary"):
                        new_list = res_gen[res_gen['Select'] == False].to_dict(orient='records')
                        st.session_state['at_list'] = new_list; st.rerun()

            else:
                # RÉPERTOIRE M-2 / M+2
                today = date.today()
                m_min_2 = (today.replace(day=1) - timedelta(days=45)).replace(day=1) # M-1
                m_min_2 = (m_min_2 - timedelta(days=1)).replace(day=1) # M-2
                m_max_2 = (today.replace(day=1) + timedelta(days=95)).replace(day=1) # M+3
                m_max_2 = m_max_2 - timedelta(days=1) # Fin M+2

                st.subheader("🔍 Filtres")
                cf1, cf2, cf3 = st.columns([2, 1.5, 1.5])
                with cf1: f_statut = st.radio("Statut :", ["Tous", "Actifs", "Inactifs"], horizontal=True)
                with cf2: f_du = st.date_input("Du :", m_min_2, format="DD/MM/YYYY")
                with cf3: f_au = st.date_input("Au :", m_max_2, format="DD/MM/YYYY")

                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)")
                if f_statut == "Actifs": query = query.eq("est_actif", True)
                elif f_statut == "Inactifs": query = query.eq("est_actif", False)
                query = query.gte("date_atelier", str(f_du)).lte("date_atelier", str(f_au))
                db_data = query.order("date_atelier", desc=False).execute().data
                
                if db_data:
                    df_r = pd.DataFrame([{"Select": False, "ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Capacité": a['capacite_max'], "Actif": a['est_actif']} for a in db_data])
                    res_r = st.data_editor(df_r, hide_index=True, disabled=["Date"], column_config=conf, key="ed_rep")
                    
                    c1, c2 = st.columns([1, 4])
                    if c1.button("💾 Sauvegarder"):
                        for _, row in res_r[res_r['Select'] == False].iterrows():
                            try:
                                supabase.table("ateliers").update({
                                    "titre": row['Titre'], "lieu_id": map_l_id[row['Lieu']], "horaire_id": map_h_id[row['Horaire']], 
                                    "capacite_max": row['Capacité'], "est_actif": row['Actif']
                                }).eq("id", int(row['ID'])).execute()
                            except: pass
                        st.success("Mis à jour !"); st.rerun()
                    
                    sel_r = res_r[res_r['Select'] == True]
                    if not sel_r.empty and c2.button(f"🗑️ Supprimer ({len(sel_r)})", type="primary"):
                        ids = sel_r['ID'].tolist()
                        supabase.table("inscriptions").delete().in_("atelier_id", ids).execute()
                        supabase.table("ateliers").delete().in_("id", ids).execute()
                        st.rerun()

        # --- AUTRES ONGLETS ---
        with t2:
            with st.form("f_adh"):
                n, p = st.text_input("Nom"), st.text_input("Prénom")
                if st.form_submit_button("Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            for u in supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute().data:
                c1, c2 = st.columns([5, 1]); c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_{u['id']}"):
                    supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute(); st.rerun()

        with t3:
            cl1, cl2 = st.columns(2)
            with cl1:
                with st.form("fl"):
                    nl, cp = st.text_input("Lieu"), st.number_input("Capa", 1)
                    if st.form_submit_button("Ajouter Lieu"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp, "est_actif": True}).execute(); st.rerun()
                for l in l_raw:
                    st.write(f"{l['nom']} ({l['capacite_accueil']} pl.)")
            with cl2:
                with st.form("fh"):
                    nh = st.text_input("Horaire")
                    if st.form_submit_button("Ajouter Horaire"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()
                for h in h_raw: st.write(h['libelle'])

        with t4:
            with st.form("f_sec"):
                o, n = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.rerun()
    else: st.info("Saisissez le code secret.")
