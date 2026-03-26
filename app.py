import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- SYSTÈME DE COULEURS ET ÉMOJIS POUR LES LIEUX ---
MAP_INFOS_LIEUX = {
    "POISSY": {"color": "#d32f2f", "emoji": "🔴"},
    "CARRIÈRES": {"color": "#1976d2", "emoji": "🔵"},
    "RAMBOUILLET": {"color": "#388e3c", "emoji": "🟢"},
    "VERSAILLES": {"color": "#f57c00", "emoji": "🟠"},
    "ST-GERMAIN": {"color": "#7b1fa2", "emoji": "🟣"},
    "DEFAULT": {"color": "#6c757d", "emoji": "⚪"}
}

def get_lieu_info(nom_lieu):
    nom_upper = str(nom_lieu).upper()
    for clé, info in MAP_INFOS_LIEUX.items():
        if clé in nom_upper: return info
    return MAP_INFOS_LIEUX["DEFAULT"]

# Style CSS
st.markdown("""
    <style>
    .st-emotion-cache-p5m613 p { white-space: normal !important; line-height: 1.5 !important; }
    .lieu-badge { padding: 2px 10px; border-radius: 12px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px; }
    .nom-header { color: #1b5e20; border-bottom: 2px solid #1b5e20; padding-top: 15px; margin-bottom: 8px; font-weight: bold; font-size: 1.1rem; }
    .suivi-ligne { padding: 10px 0px; border-bottom: 1px solid #eee; display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
    </style>
    """, unsafe_allow_html=True)

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

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    res = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{res}**" if gras else res

def parse_date_fr_to_iso(date_str):
    date_str = str(date_str).lower().replace("**", "").strip()
    mois_map = {"janvier":"01", "février":"02", "mars":"03", "avril":"04", "mai":"05", "juin":"06", "juillet":"07", "août":"08", "septembre":"09", "octobre":"10", "novembre":"11", "décembre":"12"}
    match = re.search(r"(\d{1,2})\s+([a-zéû.]+)\s+(\d{4})", date_str)
    if match:
        d, m, y = match.groups()
        return f"{y}-{mois_map.get(m, '01')}-{d.zfill(2)}"
    return str(date.today())

# --- DIALOGUES DE SÉCURITÉ ---
@st.dialog("⚠️ Confirmation de sécurité")
def secure_delete_dialog(table, item_id, label, current_code):
    st.warning(f"Désactivation de : **{label}**")
    confirm_pw = st.text_input("Code administrateur", type="password")
    if st.button("Confirmer", type="primary"):
        if confirm_pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.rerun()
        else: st.error("Code incorrect.")

# --- CHARGEMENT DATA ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- INTERFACE ---
st.title("🌿 Système RPE Connect")
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            
            # Couleur dynamique pour les places
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            info_l = get_lieu_info(at['lieux']['nom'])
            
            # Label accordéon
            date_f = format_date_fr_complete(at['date_atelier'], gras=True)
            titre_label = f"{date_f} — {at['titre']}\n{info_l['emoji']} {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_p}"
            
            with st.expander(titre_label):
                st.markdown(f"<span class='lieu-badge' style='background-color:{info_l['color']}'>📍 {at['lieux']['nom']}</span>", unsafe_allow_html=True)
                
                if res_ins.data:
                    for i in res_ins.data:
                        c_txt, c_btn = st.columns([4, 1])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_txt.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_btn.button("🗑️", key=f"del_{i['id']}"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()
                
                st.markdown("---")
                try: idx_def = (liste_adh.index(user_principal) + 1)
                except: idx_def = 0
                
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_adh = dict_adh[qui]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_adh), None)
                        if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                        else: supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                        st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).order("adherent_id").execute()
        
        curr_u = ""
        for i in data.data:
            nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom_u != curr_u:
                st.markdown(f"<div class='nom-header'>{nom_u}</div>", unsafe_allow_html=True)
                curr_u = nom_u
            
            at = i['ateliers']
            info_l = get_lieu_info(at['lieux']['nom'])
            st.markdown(f"""
                <div class='suivi-ligne'>
                    <span style='min-width:180px'>{format_date_fr_complete(at['date_atelier'], gras=True)}</span>
                    <span style='flex-grow:1'>{at['titre']} 
                        <span class='lieu-badge' style='background-color:{info_l['color']}'>{info_l['emoji']} {at['lieux']['nom']}</span>
                        <small style='color:#666'>({at['horaires']['libelle']})</small>
                    </span>
                    <span style='font-weight:bold; color:#2e7d32'>👶 {i['nb_enfants']} enfants</span>
                </div>
            """, unsafe_allow_html=True)

    with t2:
        today = str(date.today())
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today).order("date_atelier").execute()
        for a in ats_raw.data:
            info_l = get_lieu_info(a['lieux']['nom'])
            st.markdown(f"""
                <div style='margin-top:20px'>
                    {format_date_fr_complete(a['date_atelier'], gras=True)} | 
                    <span class='lieu-badge' style='background-color:{info_l['color']}'>{info_l['emoji']} {a['lieux']['nom']}</span> | 
                    <b>{a['horaires']['libelle']}</b><br>
                    <small>{a['titre']}</small>
                </div>
            """, unsafe_allow_html=True)
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            if not ins_at.data: st.write("<small style='color:gray; padding-left:20px;'>Aucun inscrit</small>", unsafe_allow_html=True)
            else:
                for p in ins_at.data:
                    st.markdown(f"<div style='padding-left:20px; font-size:0.9rem;'>• {p['adherents']['prenom']} {p['adherents']['nom']} **({p['nb_enfants']} enf.)**</div>", unsafe_allow_html=True)

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1: # GESTION ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]
            h_list = [h['libelle'] for h in h_raw]
            map_l_id = {l['nom']: l['id'] for l in l_raw}
            map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                with st.expander("🛠️ Paramétrer"):
                    d1 = st.date_input("Début", date.today()); d2 = st.date_input("Fin", d1 + timedelta(days=7))
                    js_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Générer"):
                        tmp = []; curr = d1; js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d2:
                            if js_fr[curr.weekday()] in js_sel:
                                tmp.append({"Date": format_date_fr_complete(curr, gras=True), "Titre": "", "Lieu": l_list[0] if l_list else "", "Horaire": h_list[0] if h_list else "", "Capacité": 10, "Actif": True})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = tmp; st.rerun()
                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, num_rows="dynamic")
                    if st.button("✅ Enregistrer"):
                        to_db = [{"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": True} for _, r in res_gen.iterrows() if r['Titre'] != ""]
                        if to_db: supabase.table("ateliers").insert(to_db).execute(); st.session_state['at_list'] = []; st.rerun()
            else:
                at_rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").order("date_atelier", desc=True).limit(50).execute().data
                if at_rep:
                    df_r = pd.DataFrame([{"ID": a['id'], "Date": format_date_fr_complete(a['date_atelier'], gras=True), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Actif": a['est_actif']} for a in at_rep])
                    st.data_editor(df_r, hide_index=True)

        with t2: # ADHÉRENTS
            with st.form("add_adh"):
                col1, col2 = st.columns(2)
                n = col1.text_input("Nom"); p = col2.text_input("Prénom")
                if st.form_submit_button("Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([5, 1])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_{u['id']}"):
                    secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t3: # LIEUX & HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    inf = get_lieu_info(l['nom'])
                    c_a, c_b = st.columns([4, 1])
                    c_a.markdown(f"<span class='lieu-badge' style='background-color:{inf['color']}'>{inf['emoji']} {l['nom']}</span>", unsafe_allow_html=True)
                    if c_b.button("🗑️", key=f"l_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("new_l"):
                    nl = st.text_input("Lieu")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "est_actif": True, "capacite_accueil": 10}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    c_c, c_d = st.columns([4, 1])
                    c_c.write(f"• {h['libelle']}")
                    if c_d.button("🗑️", key=f"h_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("new_h"):
                    nh = st.text_input("Libellé")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()

        with t4: # SÉCURITÉ
            st.subheader("⚙️ Code Secret")
            with st.form("f_sec"):
                o, n = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Modifier"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Modifié !"); st.rerun()
                    else: st.error("Ancien code incorrect.")
    else: st.info("Saisissez le code secret.")
