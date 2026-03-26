import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- SYSTÈME DE COULEURS POUR LES LIEUX ---
# Les couleurs sont définies ici et utilisées partout
COULEURS_LIEUX = {
    "DEFAULT": "#6c757d",
    "POISSY": "#d32f2f",      # Rouge vif
    "CARRIÈRES": "#1976d2",   # Bleu vif
    "RAMBOUILLET": "#388e3c", # Vert forêt
    "VERSAILLES": "#f57c00",  # Orange
    "ST-GERMAIN": "#7b1fa2",  # Violet
}

def get_lieu_color(nom_lieu):
    nom_upper = str(nom_lieu).upper()
    for clé, couleur in COULEURS_LIEUX.items():
        if clé in nom_upper:
            return couleur
    return COULEURS_LIEUX["DEFAULT"]

# Style CSS
st.markdown(f"""
    <style>
    .st-emotion-cache-p5m613 p {{ white-space: normal !important; line-height: 1.4 !important; }}
    .date-gras {{ font-weight: 800; color: #000; }}
    .lieu-badge {{ 
        padding: 2px 8px; 
        border-radius: 4px; 
        color: white; 
        font-weight: bold; 
        font-size: 0.8rem;
    }}
    .suivi-ligne {{ padding: 8px 0px; border-bottom: 1px solid #eee; display: flex; align-items: center; }}
    .nom-header {{ color: #1b5e20; border-bottom: 2px solid #1b5e20; padding-top: 15px; margin-bottom: 8px; font-weight: bold; }}
    /* Style pour la ligne compacte des inscrits */
    .inscrit-item {{ display: flex; align-items: center; gap: 10px; margin-bottom: 5px; }}
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

def format_date_fr_complete(date_obj, gras=False):
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

# --- SESSION STATE & DATA ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
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
            
            # Label d'accordéon avec DATE EN GRAS
            date_f = format_date_fr_complete(at['date_atelier'], gras=True)
            label_titre = f"{date_f} — {at['titre']}"
            label_details = f"📍 {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | 👥 {restantes} places"
            
            with st.expander(f"{label_titre}\n{label_details}"):
                if res_ins.data:
                    for i in res_ins.data:
                        # Ligne compacte : Nom + Enfants + Bouton sur la même ligne
                        c_nom, c_action = st.columns([4, 1])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_nom.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_action.button("🗑️", key=f"del_{i['id']}"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()
                
                st.markdown("---")
                c_q, c_e, c_v = st.columns([2, 1, 1])
                try: default_idx = (liste_adh.index(user_principal) + 1)
                except: default_idx = 0
                target = c_q.selectbox("Qui ?", ["Choisir..."] + liste_adh, index=default_idx, key=f"s_{at['id']}")
                nb_e = c_e.number_input("Enfants", 1, 10, 1, key=f"n_{at['id']}")
                if c_v.button("Valider", key=f"b_{at['id']}", type="primary"):
                    if target != "Choisir...":
                        id_t = dict_adh[target]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_t), None)
                        if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                        else: supabase.table("inscriptions").insert({"adherent_id": id_t, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
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
            c_lieu = get_lieu_color(at['lieux']['nom'])
            st.markdown(f"""
                <div class='suivi-ligne'>
                    <span style='width:200px'>{format_date_fr_complete(at['date_atelier'], gras=True)}</span>
                    <span style='flex-grow:1'>{at['titre']} 
                        <span class='lieu-badge' style='background-color:{c_lieu}'>{at['lieux']['nom']}</span>
                        <span style='color:#666; font-size:0.8rem;'> ({at['horaires']['libelle']})</span>
                    </span>
                    <span style='font-weight:bold; color:#2e7d32'>👶 {i['nb_enfants']} enf.</span>
                </div>
            """, unsafe_allow_html=True)

    with t2:
        today = str(date.today())
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today).order("date_atelier").execute()
        for a in ats_raw.data:
            c_lieu = get_lieu_color(a['lieux']['nom'])
            st.markdown(f"""
                <div style='margin-top:15px'>
                    {format_date_fr_complete(a['date_atelier'], gras=True)} | 
                    <span class='lieu-badge' style='background-color:{c_lieu}'>{a['lieux']['nom']}</span> | 
                    <b>{a['horaires']['libelle']}</b><br>
                    <small>{a['titre']}</small>
                </div>
            """, unsafe_allow_html=True)
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            if not ins_at.data: st.write("<small style='color:gray; padding-left:20px;'>Aucun inscrit</small>", unsafe_allow_html=True)
            else:
                for p in ins_at.data:
                    st.markdown(f"<div style='padding-left:20px; font-size:0.85rem;'>• {p['adherents']['prenom']} {p['adherents']['nom']} **({p['nb_enfants']} enf.)**</div>", unsafe_allow_html=True)

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1: # ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]
            h_list = [h['libelle'] for h in h_raw]
            map_l_id = {l['nom']: l['id'] for l in l_raw}
            map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                with st.expander("🛠️ Paramétrer"):
                    d1 = st.date_input("Début", date.today())
                    d2 = st.date_input("Fin", d1 + timedelta(days=7))
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
                res_rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").order("date_atelier", desc=True).execute().data
                if res_rep:
                    df_r = pd.DataFrame([{"ID": a['id'], "Date": format_date_fr_complete(a['date_atelier'], gras=True), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Actif": a['est_actif']} for a in res_rep])
                    st.data_editor(df_r, hide_index=True)

        with t3: # LIEUX avec COULEURS
            st.subheader("Lieux")
            for l in l_raw:
                c_lieu = get_lieu_color(l['nom'])
                col_a, col_b = st.columns([4,1])
                col_a.markdown(f"<span class='lieu-badge' style='background-color:{c_lieu}'>{l['nom']}</span>", unsafe_allow_html=True)
                if col_b.button("🗑️", key=f"l_{l['id']}"):
                    check = supabase.table("ateliers").select("id").eq("lieu_id", l['id']).eq("est_actif", True).execute()
                    if check.data: secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                    else: supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute(); st.rerun()
            # ... reste du code d'ajout inchangé ...

        # Les autres onglets Adhérents, Horaires, Sécurité restent identiques à la version précédente
    else: st.info("Saisissez le code secret.")
