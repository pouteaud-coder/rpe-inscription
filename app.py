import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import hashlib
import io
from fpdf import FPDF

# ==========================================
# CONFIGURATION ET INITIALISATION
# ==========================================
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .horaire-text { font-size: 0.9rem; color: #666; font-weight: 400; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; color: #31333F; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-complet { background-color: #d32f2f !important; color: white !important; }
    .container-inscrits { margin-top: -8px; padding-top: 0; margin-bottom: 5px; }
    .liste-inscrits { font-size: 0.95rem !important; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
    .nb-enfants-focus { color: #2e7d32; font-weight: 600; }
    .stButton button { border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    return f"#{hash_object.hexdigest()[:6]}"

def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except: return "1234"

def enregistrer_log(utilisateur, action, details):
    try: supabase.table("logs").insert({"utilisateur": utilisateur, "action": action, "details": details}).execute()
    except: pass

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    res = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{res}**" if gras else res

def parse_date_fr_to_iso(date_str):
    clean = str(date_str).replace("**", "").strip()
    parts = clean.split(" ")
    if len(parts) < 4: return date_str
    d, m_str, y = parts[1], parts[2].lower(), parts[3]
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    try: m = months.index(m_str) + 1
    except: m = 1
    return f"{y}-{m:02d}-{int(d):02d}"

# --- EXPORTS ---
def export_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Export')
    return output.getvalue()

def export_to_pdf(title, data_list):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    for line in data_list: pdf.multi_cell(0, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment désactiver/supprimer : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer", type="primary"):
        if pw == current_code or pw == "0000":
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.rerun()
        else: st.error("Code incorrect")

@st.dialog("✏️ Modifier une AM")
def edit_am_dialog(am_id, nom_actuel, prenom_actuel):
    new_nom = st.text_input("Nom", value=nom_actuel).upper().strip()
    new_pre = st.text_input("Prénom", value=prenom_actuel).strip()
    if st.button("Enregistrer"):
        if new_nom and new_pre:
            supabase.table("adherents").update({"nom": new_nom, "prenom": new_pre}).eq("id", am_id).execute(); st.rerun()

@st.dialog("➕ Gestion forcée (Admin)")
def admin_force_inscription_dialog(at_id, titre, restantes, liste_adh, dict_adh, user_admin="Admin"):
    st.write(f"Gestion des inscriptions pour : **{titre}**")
    res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at_id).execute()
    if res_ins.data:
        for i in res_ins.data:
            c1, c2 = st.columns([0.8, 0.2])
            n = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            c1.write(f"• {n} ({i['nb_enfants']} enf.)")
            if c2.button("🗑️", key=f"frc_del_{i['id']}"):
                supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                st.rerun()
    st.markdown("---")
    c1, c2 = st.columns([0.7, 0.3])
    qui = c1.selectbox("Sélectionner l'AM", ["Choisir..."] + liste_adh, key="frc_qui")
    nb_e = c2.number_input("Enfants", 1, 10, 1, key="frc_nb")
    if st.button("Forcer l'inscription", type="primary"):
        if qui != "Choisir...":
            id_adh = dict_adh[qui]
            supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at_id, "nb_enfants": nb_e}).execute()
            st.rerun()

@st.dialog("🔑 Super Administration")
def super_admin_dialog():
    sac = st.text_input("Code Super Admin", type="password")
    if st.button("Débloquer"):
        if sac == "0000": st.session_state['super_access'] = True; st.rerun()

# --- INITIALISATION ---
if 'at_list_gen' not in st.session_state: st.session_state['at_list_gen'] = []
if 'super_access' not in st.session_state: st.session_state['super_access'] = False

current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

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
            # VERIFICATION DU BOOLÉEN DÉDIÉ
            est_verrouille = at.get('est_verrouille', False)
            
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            if est_verrouille: statut_p = "🔒 Réservé Admin"
                
            at_info_log = f"{at['date_atelier']} | {at['horaires']['libelle']} | {at['lieux']['nom']}"
            titre_label = f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | 📍 {at['lieux']['nom']} | {statut_p}"
            
            with st.expander(titre_label):
                if est_verrouille: st.warning("⚠️ Les inscriptions pour cet atelier sont gérées par le RPE.")
                if res_ins.data:
                    for i in res_ins.data:
                        c_nom, c_poub = st.columns([0.88, 0.12])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_nom.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if not est_verrouille:
                            if c_poub.button("🗑️", key=f"del_{i['id']}"): 
                                enregistrer_log(user_principal, "Désinscription", f"Annulation pour {n_f} - {at_info_log}")
                                supabase.table("inscriptions").delete().eq("id", i['id']).execute(); st.rerun()
                if not est_verrouille:
                    st.markdown("---")
                    c1, c2, c3 = st.columns([2, 1, 1])
                    qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                    nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                    if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                        if qui != "Choisir...":
                            id_adh = dict_adh[qui]
                            if restantes - (1 + nb_e) < 0: st.error("Manque de places")
                            else: 
                                supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                                enregistrer_log(user_principal, "Inscription", f"{qui} s'inscrit - {at_info_log}")
                                st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP (Identique v12)
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    # ... (Le code reste identique à la v12 pour cette section)
    with t1:
        choix = st.multiselect("Filtrer par AM :", liste_adh, key="pub_filter_am")
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        if data.data:
            df_export = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Atelier": i['ateliers']['titre'], "Lieu": i['ateliers']['lieux']['nom'], "Enfants": i['nb_enfants']} for i in data.data])
            st.download_button("📥 Excel", data=export_to_excel(df_export), file_name="suivi_am.xlsx")
            curr_u = ""
            for i in data.data:
                nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom_u != curr_u: st.markdown(f"### {nom_u}"); curr_u = nom_u
                at = i['ateliers']; c_l = get_color(at['lieux']['nom'])
                st.write(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span>", unsafe_allow_html=True)
    with t2:
        c_d1, c_d2 = st.columns(2); d_s = c_d1.date_input("Du", date.today()); d_e = c_d2.date_input("Au", d_s + timedelta(days=30))
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_s)).lte("date_atelier", str(d_e)).order("date_atelier").execute()
        if ats_raw.data:
            for index, a in enumerate(ats_raw.data):
                c_l = get_color(a['lieux']['nom']); ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                t_ad, t_en = len(ins_at.data), sum([p['nb_enfants'] for p in ins_at.data]); rest = a['capacite_max'] - (t_ad + t_en)
                st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> <span class='compteur-badge'>👤 {t_ad} AM</span> <span class='compteur-badge'>👶 {t_en} enf.</span>", unsafe_allow_html=True)

# ==========================================
# SECTION 🔐 ADMINISTRATION (MODIFIÉE)
# ==========================================
elif menu == "🔐 Administration":
    c_login1, c_login2 = st.columns([0.7, 0.3]); pw = c_login1.text_input("Code secret admin", type="password")
    if c_login2.button("🔑 Code Super Admin"): super_admin_dialog()
    if pw == current_code or st.session_state['super_access']:
        t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(["🏗️ Ateliers", "📊 Suivi AM", "📅 Planning Ateliers", "📈 Statistiques", "👥 Liste AM", "📍 Lieux / Horaires", "⚙️ Sécurité", "📜 Journal"])
        
        with t1: # ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data; h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]; h_list = [h['libelle'] for h in h_raw]; map_l_cap = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            
            if sub == "Générateur":
                c1, c2 = st.columns(2); d1 = c1.date_input("Début", date.today()); d2 = c2.date_input("Fin", date.today()+timedelta(days=7))
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                if st.button("📊 Générer"):
                    tmp, curr = [], d1
                    while curr <= d2:
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        if js_fr[curr.weekday()] in jours:
                            tmp.append({"Date": format_date_fr_complete(curr, False), "Titre": "", "Lieu": l_list[0] if l_list else "", "Horaire": h_list[0] if h_list else "", "Capacité": map_l_cap.get(l_list[0], 10), "Verrouillé": False, "Actif": True})
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = tmp
                if st.session_state['at_list_gen']:
                    # AJOUT DE LA COLONNE VERROUILLÉ DANS L'EDITEUR
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list_gen']), num_rows="dynamic", column_config={"Lieu": st.column_config.SelectboxColumn(options=l_list, required=True), "Horaire": st.column_config.SelectboxColumn(options=h_list, required=True), "Verrouillé": st.column_config.CheckboxColumn("🔒 Admin Only")}, use_container_width=True)
                    if st.button("💾 Enregistrer"):
                        to_db = [{"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_verrouille": bool(r['Verrouillé']), "est_actif": bool(r['Actif'])} for _, r in df_ed.iterrows()]
                        if to_db: supabase.table("ateliers").insert(to_db).execute(); st.session_state['at_list_gen'] = []; st.rerun()
            
            elif sub == "Répertoire":
                cf1, cf2 = st.columns(2); fs = cf1.date_input("Du", date.today()-timedelta(days=30)); fe = cf2.date_input("Au", fs+timedelta(days=60))
                rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(fs)).lte("date_atelier", str(fe)).order("date_atelier").execute().data
                for a in rep:
                    ca, cb, cc, cd = st.columns([0.6, 0.13, 0.13, 0.14])
                    ca.write(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']}")
                    
                    # BOUTON VERROUILLAGE (🔒/🔓)
                    label_v = "🔒" if a.get('est_verrouille') else "🔓"
                    if cb.button(label_v, key=f"at_v_{a['id']}", help="Verrouiller/Déverrouiller"):
                        supabase.table("ateliers").update({"est_verrouille": not a.get('est_verrouille', False)}).eq("id", a['id']).execute(); st.rerun()
                    
                    # BOUTON ACTIF (🟢/🔴)
                    label_a = "🟢" if a['est_actif'] else "🔴"
                    if cc.button(label_a, key=f"at_st_{a['id']}", help="Activer/Désactiver"):
                        supabase.table("ateliers").update({"est_actif": not a['est_actif']}).eq("id", a['id']).execute(); st.rerun()
                    
                    if cd.button("🗑️", key=f"at_dl_{a['id']}"): secure_delete_dialog("ateliers", a['id'], a['titre'], current_code)

        with t2: # SUIVI AM
            choix_adm = st.multiselect("Filtrer par AM", liste_adh)
            ids_adm = [dict_adh[n] for n in choix_adm] if choix_adm else list(dict_adh.values())
            data_adm = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids_adm).eq("ateliers.est_actif", True).order("adherent_id").execute()
            if data_adm.data:
                curr = ""
                for i in data_adm.data:
                    nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    if nom != curr: st.markdown(f"### {nom}"); curr = nom
                    at = i['ateliers']; c_l = get_color(at['lieux']['nom'])
                    st.write(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> **({i['nb_enfants']} enf.)**", unsafe_allow_html=True)

        with t3: # PLANNING GESTION (MODIFIÉ)
            st.subheader("📅 Gestion Administrative")
            c1_p, c2_p = st.columns(2); dp_s = c1_p.date_input("Du", date.today(), key="adm_p1"); dp_e = c2_p.date_input("Au", dp_s+timedelta(days=30), key="adm_p2")
            ats_p = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(dp_s)).lte("date_atelier", str(dp_e)).order("date_atelier").execute()
            if ats_p.data:
                for a in ats_p.data:
                    c_l = get_color(a['lieux']['nom']); ins_p = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                    t_ad, t_en = len(ins_p.data), sum([p['nb_enfants'] for p in ins_p.data]); rest = a['capacite_max'] - (t_ad + t_en)
                    lock_icon = "🔒" if a.get('est_verrouille') else "🔓"
                    st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {lock_icon} {a['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> <span class='compteur-badge'>👤 {t_ad} AM</span> <span class='compteur-badge'>👶 {t_en} enf.</span>", unsafe_allow_html=True)
                    if st.button(f"➕ Gérer inscriptions : {a['titre']}", key=f"btn_adm_ins_{a['id']}"): admin_force_inscription_dialog(a['id'], a['titre'], rest, liste_adh, dict_adh)
                    if ins_p.data:
                        for p in ins_p.data: st.markdown(f"<span class='liste-inscrits'>• {p['adherents']['prenom']} {p['adherents']['nom']} ({p['nb_enfants']} enf.)</span>", unsafe_allow_html=True)
                    st.markdown("---")

        with t4: # STATS
            cs1, cs2 = st.columns(2); d_st1 = cs1.date_input("D1", date.today().replace(day=1)); d_st2 = cs2.date_input("D2", date.today())
            ins_st = supabase.table("inscriptions").select("*, adherents(nom, prenom), ateliers!inner(date_atelier)").gte("ateliers.date_atelier", str(d_st1)).lte("ateliers.date_atelier", str(d_st2)).execute()
            if ins_st.data:
                res_st = [{"AM": n, "Ateliers": sum(1 for x in ins_st.data if x['adherent_id'] == dict_adh[n])} for n in liste_adh]
                st.table(pd.DataFrame(res_st).sort_values("Ateliers", ascending=False))
        
        with t5: # LISTE AM
            with st.form("add_am"):
                c1, c2 = st.columns(2); nm = c1.text_input("Nom").upper(); pr = c2.text_input("Prénom")
                if st.form_submit_button("➕ Ajouter"): supabase.table("adherents").insert({"nom": nm, "prenom": pr, "est_actif": True}).execute(); st.rerun()
            for u in res_adh.data:
                c1, c2, c3 = st.columns([0.7, 0.15, 0.15]); c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("✏️", key=f"ed_am_{u['id']}"): edit_am_dialog(u['id'], u['nom'], u['prenom'])
                if c3.button("🗑️", key=f"dl_am_{u['id']}"): secure_delete_dialog("adherents", u['id'], u['nom'], current_code)

        with t6: # LIEUX / HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                for l in l_raw:
                    ca, cb = st.columns([0.8, 0.2]); ca.write(f"{l['nom']} (Cap: {l['capacite_accueil']})")
                    if cb.button("🗑️", key=f"lx_dl_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("lx_add"):
                    nl, nc = st.text_input("Lieu"), st.number_input("Capacité", 1, 50, 10)
                    if st.form_submit_button("Ajouter"): supabase.table("lieux").insert({"nom": nl, "capacite_accueil": nc, "est_actif": True}).execute(); st.rerun()
            with cl2:
                for h in h_raw:
                    ca, cb = st.columns([0.8, 0.2]); ca.write(h['libelle'])
                    if cb.button("🗑️", key=f"hx_dl_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("hx_add"):
                    nh = st.text_input("Horaire")
                    if st.form_submit_button("Ajouter"): supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()
        with t7: # SÉCURITÉ
            with st.form("sec"):
                ao, an = st.text_input("Ancien", type="password"), st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if ao == current_code: supabase.table("configuration").update({"secret_code": an}).eq("id", "main_config").execute(); st.rerun()
            if st.button("🚪 Déconnexion Super Admin"): st.session_state['super_access'] = False; st.rerun()
        with t8: # JOURNAL
            cj1, cj2 = st.columns(2); dj1 = cj1.date_input("D1", date.today()-timedelta(days=7)); dj2 = cj2.date_input("D2", date.today())
            try:
                res_l = supabase.table("logs").select("*").gte("created_at", str(dj1)).lte("created_at", str(dj2)+"T23:59:59").order("created_at", desc=True).execute()
                if res_l.data: st.dataframe(pd.DataFrame(res_l.data)[['created_at', 'utilisateur', 'action', 'details']], use_container_width=True, hide_index=True)
            except: pass
    else: st.info("Saisissez le code secret pour accéder à l'administration.")
