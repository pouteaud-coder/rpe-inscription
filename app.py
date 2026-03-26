import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect - Gestion Master", page_icon="🌿", layout="wide")

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
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"

def parse_date_fr_to_iso(date_str):
    date_str = str(date_str).lower().strip()
    mois_map = {"janvier":"01", "février":"02", "mars":"03", "avril":"04", "mai":"05", "juin":"06", 
                "juillet":"07", "août":"08", "septembre":"09", "octobre":"10", "novembre":"11", "décembre":"12"}
    match_txt = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", date_str)
    if match_txt:
        d, m, y = match_txt.groups()
        return f"{y}-{mois_map.get(m, '01')}-{d.zfill(2)}"
    match_num = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_str)
    if match_num:
        d, m, y = match_num.groups()
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return str(date.today())

# --- INITIALISATION SESSION ---
if 'at_list' not in st.session_state:
    st.session_state['at_list'] = []

current_code = get_secret_code()

st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS (Côté Utilisateur)
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
    noms_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    
    choix_adh = st.selectbox("👤 Sélectionnez votre nom", ["Choisir..."] + list(noms_adh.keys()))
    
    if choix_adh != "Choisir...":
        id_adh = noms_adh[choix_adh]
        today_str = str(date.today())
        
        # Récupération des ateliers futurs
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        # Récupération des inscriptions de l'utilisateur
        mes_inscriptions = supabase.table("inscriptions").select("atelier_id, nb_enfants").eq("adherent_id", id_adh).execute()
        deja_inscrit_dict = {i['atelier_id']: i['nb_enfants'] for i in mes_inscriptions.data}

        if not res_at.data:
            st.info("Aucun atelier n'est programmé pour le moment.")
        else:
            st.subheader("📅 Ateliers disponibles")
            for at in res_at.data:
                # Calcul des places : on somme (1 adulte + nb_enfants) pour chaque ligne d'inscription
                res_count = supabase.table("inscriptions").select("nb_enfants").eq("atelier_id", at['id']).execute()
                # Chaque ligne d'inscription = 1 adulte + X enfants
                total_occupé = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_count.data])
                restantes = at['capacite_max'] - total_occupé
                
                date_txt = format_date_fr(at['date_atelier'])
                lieu_h = f"{at['lieux']['nom']} | {at['horaires']['libelle']}"
                statut = f"({restantes} places)" if restantes > 0 else "(COMPLET)"
                
                with st.expander(f"📅 {date_txt} - {at['titre']} | {lieu_h} {statut}"):
                    if at['id'] in deja_inscrit_dict:
                        nb_e_deja = deja_inscrit_dict[at['id']]
                        st.success(f"✅ Inscrit avec {nb_e_deja} enfant(s).")
                        if st.button("Se désister", key=f"unreg_{at['id']}"):
                            supabase.table("inscriptions").delete().eq("adherent_id", id_adh).eq("atelier_id", at['id']).execute()
                            st.rerun()
                    elif restantes <= 0:
                        st.error("Désolé, cet atelier est complet (jauge maximale atteinte).")
                    else:
                        st.write("---")
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            mode_enfant = st.radio("Nombre d'enfants :", ["1", "2", "3", "4", "Plus..."], horizontal=True, key=f"mode_{at['id']}")
                        with col2:
                            if mode_enfant == "Plus...":
                                nb_enfants = st.number_input("Précisez :", min_value=5, max_value=20, value=5, key=f"num_{at['id']}")
                            else:
                                nb_enfants = int(mode_enfant)
                        
                        total_demande = 1 + nb_enfants
                        if total_demande > restantes:
                            st.warning(f"⚠️ Pas assez de places (il reste {restantes} places, vous en demandez {total_demande}).")
                        else:
                            if st.button("Confirmer l'inscription", key=f"reg_{at['id']}", type="primary"):
                                supabase.table("inscriptions").insert({
                                    "adherent_id": id_adh, 
                                    "atelier_id": at['id'],
                                    "nb_enfants": nb_enfants
                                }).execute()
                                st.balloons()
                                st.rerun()

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    password_input = st.text_input("Code secret d'accès", type="password")
    
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
                "Date": st.column_config.TextColumn("Date", width=200),
                "Titre": st.column_config.TextColumn("Titre (Obligatoire)", width=300),
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
                                tmp.append({"Select": False, "Date": format_date_fr(curr), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa.get(l_list[0], 10), "Actif": True})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = tmp
                        st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, num_rows="dynamic", column_config=conf, key="ed_gen")
                    c_up, c_plus, c_save, c_del = st.columns([1.5, 1.5, 1.5, 1.5])
                    
                    if c_up.button("🔄 Rafraîchir données"):
                        updated = []
                        for _, r in res_gen.iterrows():
                            r['Capacité'] = map_capa.get(r['Lieu'], 10)
                            r['Date'] = format_date_fr(parse_date_fr_to_iso(r['Date']))
                            updated.append(r.to_dict())
                        st.session_state['at_list'] = updated
                        st.rerun()

                    if c_plus.button("➕ Ligne vide"):
                        current_rows = res_gen.to_dict(orient='records')
                        current_rows.append({"Select": False, "Date": "01/04/2026", "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa.get(l_list[0], 10), "Actif": True})
                        st.session_state['at_list'] = current_rows
                        st.rerun()

                    if c_save.button("✅ Créer Ateliers"):
                        to_db = []
                        for _, r in res_gen.iterrows():
                            if str(r['Titre']).strip() != "" and not r['Select']:
                                to_db.append({"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": bool(r['Actif'])})
                        if to_db:
                            supabase.table("ateliers").insert(to_db).execute()
                            st.session_state['at_list'] = []
                            st.success("Ateliers créés !"); st.rerun()

                    if not res_gen[res_gen['Select'] == True].empty and c_del.button("🗑️ Retirer"):
                        st.session_state['at_list'] = res_gen[res_gen['Select'] == False].to_dict(orient='records')
                        st.rerun()

            else:
                # RÉPERTOIRE
                today = date.today()
                m_min_2 = (today.replace(day=1) - timedelta(days=45)).replace(day=1) 
                m_min_2 = (m_min_2 - timedelta(days=1)).replace(day=1) 
                m_max_2 = (today.replace(day=1) + timedelta(days=95)).replace(day=1)
                m_max_2 = m_max_2 - timedelta(days=1)

                st.subheader("🔍 Filtres Répertoire")
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
                            supabase.table("ateliers").update({"titre": str(row['Titre']), "lieu_id": map_l_id[row['Lieu']], "horaire_id": map_h_id[row['Horaire']], "capacite_max": int(row['Capacité']), "est_actif": bool(row['Actif'])}).eq("id", int(row['ID'])).execute()
                        st.success("Mis à jour !"); st.rerun()
                    
                    if not res_r[res_r['Select'] == True].empty and c2.button("🗑️ Supprimer sélection"):
                        @st.dialog("Confirmation")
                        def confirm_del_rep(rows):
                            ids = rows['ID'].tolist()
                            total_inscrit = 0
                            for at_id in ids:
                                check = supabase.table("inscriptions").select("id", count="exact").eq("atelier_id", at_id).execute()
                                total_inscrit += check.count if check.count else 0
                            if total_inscrit > 0:
                                st.error(f"⚠️ {total_inscrit} inscription(s) en cours !")
                                code = st.text_input("Code secret pour confirmer :", type="password")
                                if st.button("Supprimer quand même"):
                                    if code == current_code:
                                        supabase.table("inscriptions").delete().in_("atelier_id", ids).execute()
                                        supabase.table("ateliers").delete().in_("id", ids).execute()
                                        st.rerun()
                            else:
                                if st.button("Confirmer la suppression"):
                                    supabase.table("ateliers").delete().in_("id", ids).execute()
                                    st.rerun()
                        confirm_del_rep(res_r[res_r['Select'] == True])

        # --- ONGLETS ADHÉRENTS / LIEUX / SÉCURITÉ ---
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
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp, "est_actif": True}).execute(); st.rerun()
                for l in l_raw: st.write(f"📍 {l['nom']} ({l['capacite_accueil']} pl.)")
            with cl2:
                with st.form("fh"):
                    nh = st.text_input("Horaire")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()
                for h in h_raw: st.write(f"⏰ {h['libelle']}")

        with t4:
            with st.form("f_sec"):
                o, n = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.rerun()
    else: st.info("Saisissez le code secret.")
