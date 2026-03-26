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
    """Convertit 'Jeudi 2 avril 2026' ou '02/04/2026' en '2026-04-02'"""
    date_str = str(date_str).lower()
    mois_map = {"janvier":"01", "février":"02", "mars":"03", "avril":"04", "mai":"05", "juin":"06", 
                "juillet":"07", "août":"08", "septembre":"09", "octobre":"10", "novembre":"11", "décembre":"12"}
    
    # Tentative format textuel : "jeudi 2 avril 2026"
    match_txt = re.search(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", date_str)
    if match_txt:
        day, month_str, year = match_txt.groups()
        month = mois_map.get(month_str, "01")
        return f"{year}-{month}-{day.zfill(2)}"
    
    # Tentative format numérique : "02/04/2026"
    match_num = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", date_str)
    if match_num:
        day, month, year = match_num.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
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
    with col_ou:
        st.write(" ")
        if st.button("Code oublié ?"):
            @st.dialog("Récupération")
            def recover():
                r, n = st.text_input("Secours (0000)", type="password"), st.text_input("Nouveau code")
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
                "Titre": st.column_config.TextColumn("Titre", width=320, placeholder="Saisir un titre..."),
                "Lieu": st.column_config.SelectboxColumn("Lieu", options=l_list, width=130),
                "Horaire": st.column_config.SelectboxColumn("Horaire", options=h_list, width=130),
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
                    
                    # Mise à jour auto capacité
                    for i, row in res_gen.iterrows():
                        if i < len(st.session_state['at_list']):
                            if row['Lieu'] != st.session_state['at_list'][i]['Lieu']:
                                res_gen.at[i, 'Capacité'] = map_capa.get(row['Lieu'], 10)
                                st.session_state['at_list'] = res_gen.to_dict(orient='records')
                                st.rerun()

                    c_save, c_plus, c_del_gen = st.columns([1, 1.5, 2])
                    if c_save.button("✅ Enregistrer"):
                        # CORRECTION : Extraction de la date depuis la colonne 'Date' du tableau
                        to_db = []
                        for _, r in res_gen.iterrows():
                            if r['Titre'] and not r['Select']:
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
                            st.session_state['at_list'] = []; st.success("Ateliers d'avril enregistrés !"); st.rerun()

                    if c_plus.button("➕ Ligne vide"):
                        st.session_state['at_list'].append({"Select": False, "Date": format_date_fr(date.today()), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa[l_list[0]], "Actif": True})
                        st.rerun()

                    selected_to_pop = res_gen[res_gen['Select'] == True].index.tolist()
                    if selected_to_pop:
                        if c_del_gen.button(f"🗑️ Retirer ({len(selected_to_pop)})", type="primary"):
                            new_list = res_gen[res_gen['Select'] == False].to_dict(orient='records')
                            st.session_state['at_list'] = new_list; st.rerun()

            else:
                # RÉPERTOIRE (Logique M-2 / M+2 conservée)
                today = date.today()
                m_minus_2 = today.month - 2
                y_start = today.year
                if m_minus_2 <= 0: m_minus_2 += 12; y_start -= 1
                default_start = date(y_start, m_minus_2, 1)
                
                m_plus_2 = today.month + 2
                y_end = today.year
                if m_plus_2 > 12: m_plus_2 -= 12; y_end += 1
                m_next = m_plus_2 + 1
                y_next = y_end
                if m_next > 12: m_next = 1; y_next += 1
                default_end = date(y_next, m_next, 1) - timedelta(days=1)

                st.subheader("🔍 Filtres")
                c_f1, c_f2, c_f3 = st.columns([2, 1.5, 1.5])
                with c_f1: f_r = st.radio("Statut :", ["Tous", "Actifs", "Inactifs"], horizontal=True)
                with c_f2: date_debut = st.date_input("Du :", default_start, format="DD/MM/YYYY")
                with c_f3: date_fin = st.date_input("Au :", default_end, format="DD/MM/YYYY")

                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)")
                if f_r == "Actifs": query = query.eq("est_actif", True)
                elif f_r == "Inactifs": query = query.eq("est_actif", False)
                query = query.gte("date_atelier", str(date_debut)).lte("date_atelier", str(date_fin))
                db_d = query.order("date_atelier", desc=False).execute().data
                
                if db_d:
                    df_r = pd.DataFrame([{"Select": False, "ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Capacité": a['capacite_max'], "Actif": a['est_actif']} for a in db_d])
                    res_r = st.data_editor(df_r, hide_index=True, disabled=["Date"], column_config=conf, key="ed_rep")
                    
                    c1, c2 = st.columns([1, 4])
                    if c1.button("💾 Sauvegarder"):
                        rows_to_update = res_r[res_r['Select'] == False]
                        for _, row in rows_to_update.iterrows():
                            try:
                                supabase.table("ateliers").update({
                                    "titre": row['Titre'], "lieu_id": map_l_id[row['Lieu']], "horaire_id": map_h_id[row['Horaire']], 
                                    "capacite_max": row['Capacité'], "est_actif": row['Actif']
                                }).eq("id", int(row['ID'])).execute()
                            except: pass
                        st.success("Modifications enregistrées !"); st.rerun()
                    
                    selected_rows = res_r[res_r['Select'] == True]
                    if not selected_rows.empty:
                        if c2.button(f"🗑️ Supprimer ({len(selected_rows)})", type="primary"):
                            @st.dialog("Confirmation")
                            def multi_del(rows):
                                ids = rows['ID'].tolist()
                                st.write(f"Supprimer ces {len(ids)} ateliers ?")
                                if st.button("Confirmer"):
                                    supabase.table("inscriptions").delete().in_("atelier_id", ids).execute()
                                    supabase.table("ateliers").delete().in_("id", ids).execute()
                                    st.rerun()
                            multi_del(selected_rows)
                else: st.info("Aucun atelier trouvé.")

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
            col_l, col_h = st.columns(2)
            with col_l:
                with st.form("f_l"):
                    nl, cl = st.text_input("Nom"), st.number_input("Capacité", min_value=1)
                    if st.form_submit_button("OK"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cl, "est_actif": True}).execute(); st.rerun()
                for l in l_raw:
                    c1, c2 = st.columns([3, 1]); c1.write(f"{l['nom']} ({l['capacite_accueil']} pl.)")
                    if c2.button("🗑️", key=f"l_{l['id']}"):
                        supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute(); st.rerun()
            with col_h:
                with st.form("f_h"):
                    nh = st.text_input("Libellé")
                    if st.form_submit_button("OK"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()
                for h in h_raw:
                    c1, c2 = st.columns([3, 1]); c1.write(h['libelle'])
                    if c2.button("🗑️", key=f"h_{h['id']}"):
                        supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute(); st.rerun()

        with t4:
            with st.form("f_sec"):
                o, n = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.rerun()
    else: st.info("Saisissez le code secret.")
