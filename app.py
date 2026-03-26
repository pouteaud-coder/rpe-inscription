import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- SYSTÈME DE COULEURS DYNAMIQUES PAR LIEU ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    hex_hash = hash_object.hexdigest()
    return f"#{hex_hash[:6]}"

# --- STYLE CSS AJUSTÉ ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    [data-testid="stSidebarNav"] span { font-size: 1.1rem !important; font-weight: 500; }
    .stRadio div[role="radiogroup"] label { font-size: 1.2rem !important; padding-bottom: 10px; }
    
    .lieu-badge { padding: 4px 12px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.9rem; display: inline-block; margin: 2px 0; }
    .nom-header { color: #1b5e20; border-bottom: 2px solid #1b5e20; padding-top: 15px; margin-bottom: 8px; font-weight: bold; font-size: 1.2rem; }
    
    /* Taille intermédiaire pour la liste des inscrits */
    .liste-inscrits { 
        font-size: 1.1rem !important; /* Réduit par rapport au 1.25rem précédent */
        font-weight: 500; 
        margin-left: 15px;
        line-height: 1.6;
        color: #333;
    }
    .nb-enfants-focus { color: #1b5e20; font-weight: 700; font-size: 1.15rem; }

    /* Boutons alignés à gauche */
    .stButton button { 
        border-radius: 8px !important;
        min-width: 220px !important;
    }
    
    button[data-baseweb="tab"] div { font-size: 1.1rem !important; }
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

@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.warning(f"Désactivation de : **{label}**")
    confirm_pw = st.text_input("Code administrateur", type="password")
    if st.button("Confirmer", type="primary"):
        if confirm_pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.rerun()
        else: st.error("Code incorrect.")

# --- INITIALISATION ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- NAVIGATION ---
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
            
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            date_f = format_date_fr_complete(at['date_atelier'], gras=True)
            titre_label = f"{date_f} — {at['titre']}\n📍 {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_p}"
            
            with st.expander(titre_label):
                if res_ins.data:
                    for i in res_ins.data:
                        c_nom, c_poub = st.columns([0.88, 0.12])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_nom.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_poub.button("🗑️", key=f"del_{i['id']}"):
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
        # Filtrage pour ne garder que les ateliers actifs
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        curr_u = ""
        for i in data.data:
            nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom_u != curr_u:
                st.markdown(f'<div class="nom-header">{nom_u}</div>', unsafe_allow_html=True)
                curr_u = nom_u
            at = i['ateliers']
            c_l = get_color(at['lieux']['nom'])
            st.write(f"{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> **({i['nb_enfants']} enf.)**", unsafe_allow_html=True)

    with t2:
        c_d1, c_d2 = st.columns(2)
        d_start = c_d1.date_input("Du", date.today(), format="DD/MM/YYYY")
        d_end = c_d2.date_input("Au", d_start + timedelta(days=30), format="DD/MM/YYYY")
        
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end)).order("date_atelier").execute()
            
        for a in ats_raw.data:
            c_l = get_color(a['lieux']['nom'])
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> | {a['horaires']['libelle']}", unsafe_allow_html=True)
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            if not ins_at.data: 
                st.write("  <small>Aucun inscrit</small>", unsafe_allow_html=True)
            else:
                for p in ins_at.data:
                    # Taille intermédiaire Nom + Enfants
                    st.markdown(f'<div class="liste-inscrits">• {p["adherents"]["prenom"]} {p["adherents"]["nom"]} <span class="nb-enfants-focus">({p["nb_enfants"]} enfants)</span></div>', unsafe_allow_html=True)

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t_ad1, t_ad2, t_ad3, t_ad4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t_ad1:
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]; h_list = [h['libelle'] for h in h_raw]
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                c_g1, c_g2 = st.columns(2)
                d1 = c_g1.date_input("Début", date.today(), format="DD/MM/YYYY")
                d2 = c_g2.date_input("Fin", d1 + timedelta(days=7), format="DD/MM/YYYY")
                js_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer la liste des ateliers"):
                    tmp = []; curr = d1; js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    while curr <= d2:
                        if js_fr[curr.weekday()] in js_sel:
                            tmp.append({"Date": format_date_fr_complete(curr, gras=True), "Titre": "", "Lieu": l_list[0] if l_list else "", "Horaire": h_list[0] if h_list else "", "Capacité": 10, "Actif": True})
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = tmp; st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, use_container_width=True)
                    if st.button("✅ Enregistrer définitivement"):
                        to_db = [{"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": True} for _, r in res_gen.iterrows() if r['Titre'] != ""]
                        if to_db: supabase.table("ateliers").insert(to_db).execute(); st.session_state['at_list'] = []; st.rerun()
            else: 
                at_rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").order("date_atelier", desc=True).limit(60).execute().data
                if at_rep:
                    df_rep = pd.DataFrame([{"Date": format_date_fr_complete(a['date_atelier'], gras=True), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Actif": a['est_actif']} for a in at_rep])
                    edited_df = st.data_editor(df_rep, hide_index=True, use_container_width=True)
                    
                    if st.button("💾 Sauvegarder les modifications du répertoire", type="primary"):
                        for idx, row in edited_df.iterrows():
                            at_id = at_rep[idx]['id']
                            supabase.table("ateliers").update({"titre": row['Titre'], "est_actif": bool(row['Actif'])}).eq("id", at_id).execute()
                        st.success("Répertoire mis à jour !"); st.rerun()

        with t_ad2: # ADHÉRENTS
            with st.form("add_adh"):
                col_n, col_p = st.columns(2); n = col_n.text_input("Nom"); p = col_p.text_input("Prénom")
                if st.form_submit_button("➕ Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([0.85, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t_ad3: # LIEUX & HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    c_a, c_b = st.columns([0.85, 0.15])
                    c_a.markdown(f"<span class='lieu-badge' style='background-color:{get_color(l['nom'])}'>{l['nom']}</span>", unsafe_allow_html=True)
                    if c_b.button("🗑️", key=f"l_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("new_l"):
                    nl = st.text_input("Nouveau Lieu")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "est_actif": True, "capacite_accueil": 10}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    c_c, c_d = st.columns([0.85, 0.15]); c_c.write(f"• {h['libelle']}")
                    if c_d.button("🗑️", key=f"h_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("new_h"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()

        with t_ad4: # SÉCURITÉ
            st.subheader("⚙️ Code Administrateur")
            with st.form("f_sec"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code modifié !"); st.rerun()
                    else: st.error("L'ancien code est incorrect.")
    else: st.info("Saisissez le code secret administrateur.")
