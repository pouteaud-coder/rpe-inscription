import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# Style CSS Adaptatif et Épuré
st.markdown("""
    <style>
    .suivi-ligne { padding: 8px 0px; border-bottom: 1px solid #eee; display: flex; flex-wrap: wrap; align-items: center; font-size: 0.85rem; }
    .date-info { font-weight: 600; color: #444; width: 120px; }
    .titre-info { flex-grow: 1; color: #222; }
    .badge-fin { font-size: 0.7rem; padding: 1px 5px; border: 1px solid #ddd; border-radius: 3px; color: #777; margin-left: 5px; display: inline-block; }
    .nb-enfants { font-weight: bold; color: #2e7d32; margin-left: auto; padding-left: 10px; }
    .nom-header { color: #1b5e20; border-bottom: 1px solid #1b5e20; padding-top: 15px; margin-bottom: 8px; font-size: 1rem; font-weight: bold; }
    @media (max-width: 768px) {
        .date-info { width: 100%; margin-bottom: 2px; font-size: 0.8rem; }
        .nb-enfants { width: 100%; margin-left: 0; margin-top: 5px; text-align: left; background: #f9f9f9; padding: 2px 5px; border-radius: 4px; }
        .stButton button { width: 100%; }
    }
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

def format_date_fr(date_obj):
    jours = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    return f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]}"

def parse_date_fr_to_iso(date_str):
    date_str = str(date_str).lower().strip()
    mois_map = {"janv.":"01", "janvier":"01", "févr.":"02", "février":"02", "mars":"03", "avr.":"04", "avril":"04", "mai":"05", "juin":"06", "juil.":"07", "juillet":"07", "août":"08", "sept.":"09", "septembre":"09", "oct.":"10", "octobre":"10", "nov.":"11", "novembre":"11", "déc.":"12", "décembre":"12"}
    match = re.search(r"(\d{1,2})\s+([a-zéû.]+)\s+(\d{4})", date_str)
    if match:
        d, m, y = match.groups()
        return f"{y}-{mois_map.get(m, '01')}-{d.zfill(2)}"
    return str(date.today())

# --- DIALOGUES DE SÉCURITÉ ---
@st.dialog("⚠️ Confirmation de sécurité")
def secure_delete_dialog(table, item_id, label, current_code):
    st.warning(f"Vous allez désactiver : **{label}**")
    st.write("Cet élément est actuellement lié à des données actives.")
    confirm_pw = st.text_input("Saisissez le code administrateur pour confirmer", type="password")
    if st.button("Confirmer la désactivation", type="primary"):
        if confirm_pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Action effectuée.")
            st.rerun()
        else:
            st.error("Code incorrect.")

# --- SESSION STATE ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
if 'u_opened_at' not in st.session_state: st.session_state['u_opened_at'] = None

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
            
            est_ouvert = st.session_state['u_opened_at'] == at['id']
            label = f"{format_date_fr(at['date_atelier'])} - {at['titre']} ({restantes} pl.)"
            
            with st.expander(label, expanded=est_ouvert):
                if res_ins.data:
                    for i in res_ins.data:
                        c1, c2, c3 = st.columns([3, 2, 1])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c1.write(f"• {n_f}")
                        c2.write(f"{i['nb_enfants']} enf.")
                        if c3.button("🗑️", key=f"del_{at['id']}_{i['id']}"):
                            st.session_state['u_opened_at'] = at['id']
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()
                
                st.markdown("---")
                c_q, c_e, c_v = st.columns([2, 2, 1])
                target = c_q.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"s_{at['id']}")
                nb_e = c_e.number_input("Enfants", 1, 10, 1, key=f"n_{at['id']}")
                if c_v.button("Valider", key=f"b_{at['id']}", type="primary"):
                    if target != "Choisir...":
                        st.session_state['u_opened_at'] = at['id']
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
            st.markdown(f"<div class='suivi-ligne'><span class='date-info'>{format_date_fr(at['date_atelier'])}</span><span class='titre-info'>{at['titre']} <span class='badge-fin'>{at['lieux']['nom']}</span><span class='badge-fin'>{at['horaires']['libelle']}</span></span><span class='nb-enfants'>👶 {i['nb_enfants']} enf.</span></div>", unsafe_allow_html=True)

    with t2:
        today = str(date.today())
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today).order("date_atelier").execute()
        dict_at = {f"{format_date_fr(a['date_atelier'])} - {a['titre']}": a['id'] for a in ats_raw.data}
        sel_at = st.multiselect("Filtrer par atelier :", list(dict_at.keys()))
        at_ids = [dict_at[n] for n in sel_at] if sel_at else [a['id'] for a in ats_raw.data]
        for a_id in at_ids:
            a_info = next(at for at in ats_raw.data if at['id'] == a_id)
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a_id).execute()
            st.markdown(f"**{format_date_fr(a_info['date_atelier'])} — {a_info['titre']}** <small>({a_info['lieux']['nom']} | {a_info['horaires']['libelle']})</small>", unsafe_allow_html=True)
            if not ins_at.data: st.write("<small style='color:gray; padding-left:20px;'>Aucun inscrit</small>", unsafe_allow_html=True)
            else:
                for p in ins_at.data:
                    st.markdown(f"<div style='display:flex; justify-content:space-between; max-width:400px; padding-left:20px; font-size:0.85rem; border-left:1px solid #ddd; margin:2px 0;'><span>{p['adherents']['prenom']} {p['adherents']['nom']}</span><span style='color:#2e7d32; font-weight:bold;'>{p['nb_enfants']} enf.</span></div>", unsafe_allow_html=True)
            st.write("")

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
            l_list, h_list = [l['nom'] for l in l_raw], [h['libelle'] for h in h_raw]
            map_l_id, map_h_id = {l['nom']: l['id'] for l in l_raw}, {h['libelle']: h['id'] for h in h_raw}
            map_capa = {l['nom']: l['capacite_accueil'] for l in l_raw}
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            conf = {"Date": st.column_config.TextColumn("Date"), "Titre": st.column_config.TextColumn("Titre"), "Lieu": st.column_config.SelectboxColumn("Lieu", options=l_list), "Horaire": st.column_config.SelectboxColumn("Horaire", options=h_list), "Capacité": st.column_config.NumberColumn("Cap."), "Actif": st.column_config.CheckboxColumn("Actif")}

            if sub == "Générateur":
                with st.expander("🛠️ Paramétrer"):
                    d1 = st.date_input("Début", date.today()); d2 = st.date_input("Fin", d1 + timedelta(days=7))
                    js_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                    if st.button("📊 Générer"):
                        tmp = []; curr = d1; js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        while curr <= d2:
                            if js_fr[curr.weekday()] in js_sel:
                                tmp.append({"Date": format_date_fr(curr), "Titre": "", "Lieu": l_list[0] if l_list else "", "Horaire": h_list[0] if h_list else "", "Capacité": map_capa.get(l_list[0], 10), "Actif": True})
                            curr += timedelta(days=1)
                        st.session_state['at_list'] = tmp; st.rerun()
                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, num_rows="dynamic", column_config=conf)
                    if st.button("✅ Enregistrer"):
                        to_db = [{"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": bool(r['Actif'])} for _, r in res_gen.iterrows() if str(r['Titre']).strip() != ""]
                        if to_db: supabase.table("ateliers").insert(to_db).execute(); st.session_state['at_list'] = []; st.rerun()
            else: # RÉPERTOIRE
                res_rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").order("date_atelier", desc=True).execute().data
                if res_rep:
                    df_r = pd.DataFrame([{"ID": a['id'], "Date": format_date_fr(a['date_atelier']), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'], "Capacité": a['capacite_max'], "Actif": a['est_actif']} for a in res_rep])
                    ed_r = st.data_editor(df_r, hide_index=True, column_config=conf)
                    if st.button("💾 Sauvegarder"):
                        for _, r in ed_r.iterrows():
                            supabase.table("ateliers").update({"titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": bool(r['Actif'])}).eq("id", r['ID']).execute()
                        st.rerun()

        with t2: # ADHÉRENTS
            with st.form("f_adh"):
                n, p = st.text_input("Nom"), st.text_input("Prénom")
                if st.form_submit_button("Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            
            for u in res_adh.data:
                c1, c2 = st.columns([5, 1])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_{u['id']}"):
                    # VÉRIFICATION DE SÉCURITÉ : Inscriptions en cours ?
                    check = supabase.table("inscriptions").select("id").eq("adherent_id", u['id']).execute()
                    if check.data:
                        secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)
                    else:
                        supabase.table("adherents").update({"est_actif": False}).eq("id", u['id']).execute()
                        st.rerun()

        with t3: # LIEUX/HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    col_a, col_b = st.columns([4,1])
                    col_a.write(f"• {l['nom']} ({l['capacite_accueil']} pl.)")
                    if col_b.button("🗑️", key=f"l_{l['id']}"):
                        check_l = supabase.table("ateliers").select("id").eq("lieu_id", l['id']).eq("est_actif", True).execute()
                        if check_l.data:
                            secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                        else:
                            supabase.table("lieux").update({"est_actif": False}).eq("id", l['id']).execute()
                            st.rerun()
                with st.form("new_l"):
                    nl, cp = st.text_input("Lieu"), st.number_input("Capa", 1, 50, 10)
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp, "est_actif": True}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    col_c, col_d = st.columns([4,1])
                    col_c.write(f"• {h['libelle']}")
                    if col_d.button("🗑️", key=f"h_{h['id']}"):
                        check_h = supabase.table("ateliers").select("id").eq("horaire_id", h['id']).eq("est_actif", True).execute()
                        if check_h.data:
                            secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                        else:
                            supabase.table("horaires").update({"est_actif": False}).eq("id", h['id']).execute()
                            st.rerun()
                with st.form("new_h"):
                    nh = st.text_input("Horaire")
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
