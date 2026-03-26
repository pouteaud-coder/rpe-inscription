import streamlit as st
import pd as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect - Inscriptions", page_icon="🌿", layout="wide")

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
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscription aux Ateliers")
    
    res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
    dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
    liste_noms = ["Choisir..."] + list(dict_adh.keys())
    
    user_principal = st.selectbox("👤 Vous êtes :", liste_noms)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        if not res_at.data:
            st.info("Aucun atelier prévu prochainement.")
        else:
            for at in res_at.data:
                # Récupération des inscriptions actuelles
                res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
                inscrits = res_ins.data
                
                # Calcul de l'occupation actuelle
                total_occupé = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in inscrits])
                restantes = at['capacite_max'] - total_occupé
                
                date_txt = format_date_fr(at['date_atelier'])
                lieu_h = f"{at['lieux']['nom']} | {at['horaires']['libelle']}"
                statut = f"({restantes} places restantes)" if restantes > 0 else "(COMPLET)"
                
                with st.expander(f"📅 {date_txt} - {at['titre']} | {lieu_h} {statut}"):
                    
                    st.markdown("##### 👥 Liste des inscrits")
                    if not inscrits:
                        st.write("_Aucun inscrit._")
                    else:
                        for i in inscrits:
                            col_n, col_e, col_act = st.columns([3, 2, 1])
                            nom_i = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                            col_n.write(f"• **{nom_i}**")
                            col_e.write(f"{i['nb_enfants']} enfant(s)")
                            if col_act.button("🗑️", key=f"del_{at['id']}_{i['id']}"):
                                supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                                st.rerun()
                    
                    st.markdown("---")
                    st.markdown("##### ➕ Inscrire ou Modifier")
                    
                    ci1, ci2, ci3 = st.columns([2, 2, 1])
                    with ci1:
                        beneficiaire = st.selectbox("Qui ?", liste_noms, key=f"ben_{at['id']}")
                    with ci2:
                        mode_e = st.radio("Enfants :", ["1", "2", "3", "4", "Plus..."], horizontal=True, key=f"me_{at['id']}")
                        nb_e = st.number_input("Nombre :", 5, 20, 5, key=f"ne_{at['id']}") if mode_e == "Plus..." else int(mode_e)
                    
                    with ci3:
                        st.write("")
                        if st.button("Valider", key=f"btn_{at['id']}", type="primary"):
                            if beneficiaire == "Choisir...":
                                st.error("Sélectionnez un nom.")
                            else:
                                id_ben = dict_adh[beneficiaire]
                                # Vérifier si la personne est déjà là
                                existing = next((ins for ins in inscrits if ins['adherent_id'] == id_ben), None)
                                
                                # Calcul du changement de jauge
                                # Si nouveau : + (1 + nb_e)
                                # Si modif : + (nb_e_nouveau - nb_e_ancien)
                                diff = (1 + nb_e) if not existing else (nb_e - existing['nb_enfants'])
                                
                                if diff > restantes:
                                    st.error(f"Places insuffisantes (manque {diff - restantes} places).")
                                else:
                                    if existing:
                                        # MISE À JOUR (on ne change que le nombre d'enfants)
                                        supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                                        st.toast(f"Mise à jour pour {beneficiaire} effectueé !")
                                    else:
                                        # NOUVELLE INSCRIPTION
                                        supabase.table("inscriptions").insert({"adherent_id": id_ben, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                                        st.toast(f"{beneficiaire} inscrit(e) !")
                                    
                                    # Pour rester au même endroit, on utilise rerun pour actualiser la liste et le calcul
                                    st.rerun()

# ==========================================
# SECTION 🔐 ADMINISTRATION (Inchangée)
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
            conf = {"Date": st.column_config.TextColumn("Date", width=200), "Titre": st.column_config.TextColumn("Titre", width=300), "Lieu": st.column_config.SelectboxColumn("Lieu", options=l_list), "Horaire": st.column_config.SelectboxColumn("Horaire", options=h_list), "Capacité": st.column_config.NumberColumn("Cap."), "Actif": st.column_config.CheckboxColumn("Actif"), "Select": st.column_config.CheckboxColumn("Sél."), "ID": None}

            if sub == "Générateur":
                with st.expander("🛠️ Paramétrer une série"):
                    d1 = st.date_input("Début", date.today()); d2 = st.date_input("Fin", d1 + timedelta(days=7))
                    js_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Générer"):
                        tmp = []; curr = d1; js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d2:
                            if js_fr[curr.weekday()] in js_sel:
                                tmp.append({"Select": False, "Date": format_date_fr(curr), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa.get(l_list[0], 10), "Actif": True})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = tmp; st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, num_rows="dynamic", column_config=conf, key="ed_gen")
                    c_up, c_plus, c_save, c_del = st.columns(4)
                    if c_up.button("🔄 Rafraîchir"):
                        upd = []
                        for _, r in res_gen.iterrows():
                            r['Capacité'] = map_capa.get(r['Lieu'], 10)
                            r['Date'] = format_date_fr(parse_date_fr_to_iso(r['Date']))
                            upd.append(r.to_dict())
                        st.session_state['at_list'] = upd; st.rerun()
                    if c_plus.button("➕ Ligne"):
                        rows = res_gen.to_dict(orient='records')
                        rows.append({"Select": False, "Date": format_date_fr(date.today()), "Titre": "", "Lieu": l_list[0], "Horaire": h_list[0], "Capacité": map_capa.get(l_list[0], 10), "Actif": True})
                        st.session_state['at_list'] = rows; st.rerun()
                    if c_save.button("✅ Créer"):
                        to_db = [{"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": bool(r['Actif'])} for _, r in res_gen.iterrows() if str(r['Titre']).strip() != "" and not r['Select']]
                        if to_db: supabase.table("ateliers").insert(to_db).execute(); st.session_state['at_list'] = []; st.rerun()
                    if c_del.button("🗑️ Retirer"):
                        st.session_state['at_list'] = res_gen[res_gen['Select'] == False].to_dict(orient='records'); st.rerun()
            else:
                # RÉPERTOIRE
                res_rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").order("date_atelier").execute().data
                if res_rep:
                    df_r = pd.DataFrame([{"Select": False, "ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Capacité": a['capacite_max'], "Actif": a['est_actif']} for a in res_rep])
                    ed_r = st.data_editor(df_r, hide_index=True, column_config=conf, key="ed_rep")
                    if st.button("💾 Sauvegarder"):
                        for _, row in ed_r.iterrows():
                            supabase.table("ateliers").update({"titre": row['Titre'], "lieu_id": map_l_id[row['Lieu']], "horaire_id": map_h_id[row['Horaire']], "capacite_max": int(row['Capacité']), "est_actif": bool(row['Actif'])}).eq("id", row['ID']).execute()
                        st.rerun()

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
            with cl2:
                with st.form("fh"):
                    nh = st.text_input("Horaire")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()
        with t4:
            with st.form("f_sec"):
                o, n = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code: supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.rerun()
    else: st.info("Saisissez le code secret.")
