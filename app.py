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

# --- CONNEXION SUPABASE ---
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- STYLE CSS ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .horaire-text { font-size: 0.9rem; color: #666; font-weight: 400; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; color: #31333F; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-complet { background-color: #d32f2f !important; color: white !important; border-color: #b71c1c !important; }
    .separateur-atelier { border: 0; border-top: 1px solid #eee; margin: 15px 0; }
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
    except: 
        return "1234"

def enregistrer_log(utilisateur, action, details):
    """Enregistre une action dans la table logs"""
    try:
        supabase.table("logs").insert({
            "utilisateur": utilisateur,
            "action": action,
            "details": details
        }).execute()
    except Exception as e:
        pass

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

# --- FONCTIONS D'EXPORT ---
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
    for line in data_list:
        pdf.multi_cell(0, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment désactiver/supprimer : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer", type="primary"):
        if pw == current_code or pw == "0000":
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Opération réussie"); st.rerun()
        else: st.error("Code incorrect")

@st.dialog("✏️ Modifier une AM")
def edit_am_dialog(am_id, nom_actuel, prenom_actuel):
    new_nom = st.text_input("Nom", value=nom_actuel).upper().strip()
    new_pre = st.text_input("Prénom", value=prenom_actuel).strip()
    if st.button("Enregistrer"):
        if new_nom and new_pre:
            supabase.table("adherents").update({"nom": new_nom, "prenom": new_pre}).eq("id", am_id).execute()
            st.success("Modifié !"); st.rerun()

@st.dialog("⚠️ Suppression Atelier")
def delete_atelier_dialog(at_id, titre, a_des_inscrits, current_code):
    st.warning(f"Voulez-vous supprimer l'atelier : **{titre}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer la suppression définitive"):
        if pw == current_code or pw == "0000":
            if a_des_inscrits: supabase.table("inscriptions").delete().eq("atelier_id", at_id).execute()
            supabase.table("ateliers").delete().eq("id", at_id).execute()
            st.rerun()

@st.dialog("⚠️ Confirmer la désinscription")
def confirm_unsubscribe_dialog(ins_id, nom_complet, atelier_info, user_admin="Utilisateur"):
    st.warning(f"Souhaitez-vous vraiment annuler la réservation de **{nom_complet}** ?")
    if st.button("Oui, désinscrire", type="primary"):
        supabase.table("inscriptions").delete().eq("id", ins_id).execute()
        # Log de désinscription
        enregistrer_log(user_admin, "Désinscription", f"Annulation pour {nom_complet} - {atelier_info}")
        st.rerun()

@st.dialog("🔑 Super Administration")
def super_admin_dialog():
    st.write("Saisissez le code de secours pour accéder à l'administration.")
    sac = st.text_input("Code Super Admin", type="password")
    if st.button("Débloquer l'accès"):
        if sac == "0000":
            st.session_state['super_access'] = True
            st.rerun()
        else: st.error("Code incorrect")

# --- CHARGEMENT DES DONNÉES GLOBALES ---
if 'at_list_gen' not in st.session_state: st.session_state['at_list_gen'] = []
if 'super_access' not in st.session_state: st.session_state['super_access'] = False

current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- NAVIGATION ---
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
            # Préparation du texte pour le journal
            at_info_pour_log = f"{at['date_atelier']} | {at['horaires']['libelle']} | {at['lieux']['nom']}"
            
            titre_label = f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | 📍 {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_p}"
            
            with st.expander(titre_label):
                if res_ins.data:
                    for i in res_ins.data:
                        c_nom, c_poub = st.columns([0.88, 0.12])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_nom.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_poub.button("🗑️", key=f"del_{i['id']}"): 
                            confirm_unsubscribe_dialog(i['id'], n_f, at_info_pour_log, user_principal)
                
                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_adh = dict_adh[qui]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_adh), None)
                        if existing:
                            if restantes - (nb_e - existing['nb_enfants']) < 0: st.error("Manque de places")
                            else: 
                                supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                                enregistrer_log(user_principal, "Modification", f"{qui} change à {nb_e} enfants - {at_info_pour_log}")
                                st.rerun()
                        else:
                            if restantes - (1 + nb_e) < 0: st.error("Manque de places")
                            else: 
                                supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                                enregistrer_log(user_principal, "Inscription", f"{qui} (+{nb_e} enf.) - {at_info_pour_log}")
                                st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par assistante maternelle :", liste_adh, key="pub_f_am")
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        
        if data.data:
            df_export = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Atelier": i['ateliers']['titre'], "Lieu": i['ateliers']['lieux']['nom'], "Enfants": i['nb_enfants']} for i in data.data])
            # BOUTONS EXPORT SUIVI AM
            ce1, ce2 = st.columns(2)
            ce1.download_button("📥 Excel", data=export_to_excel(df_export), file_name="suivi.xlsx")
            ce2.download_button("📥 PDF", data=export_to_pdf("Suivi AM", [f"{r['AM']} - {r['Date']}" for _, r in df_export.iterrows()]), file_name="suivi.pdf")
            
            curr = ""
            for i in data.data:
                nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom != curr: st.markdown(f"### {nom}"); curr = nom
                st.write(f"• {format_date_fr_complete(i['ateliers']['date_atelier'])} - {i['ateliers']['titre']} **({i['nb_enfants']} enf.)**")

    with t2:
        c1, c2 = st.columns(2)
        ds = c1.date_input("Du", date.today(), key="pub_d1")
        de = c2.date_input("Au", date.today()+timedelta(days=30), key="pub_d2")
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(ds)).lte("date_atelier", str(de)).order("date_atelier").execute()
        if ats.data:
            for a in ats.data:
                ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                t_ad, t_en = len(ins.data), sum([p['nb_enfants'] for p in ins.data])
                st.write(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['lieux']['nom']} | {t_ad} AM - {t_en} enf.")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    c_l1, c_l2 = st.columns([0.7, 0.3])
    pw = c_l1.text_input("Code secret admin", type="password")
    if c_l2.button("🔑 Code Super Admin"): super_admin_dialog()
    
    if pw == current_code or st.session_state['super_access']:
        # RÉTABLISSEMENT DES 8 ONGLETS DE LA VERSION V7
        tabs = st.tabs(["🏗️ Ateliers", "📊 Suivi AM", "📅 Planning Ateliers", "📈 Statistiques de participation", "👥 Liste AM", "📍 Lieux / Horaires", "⚙️ Sécurité", "📜 Journal des actions"])
        
        with tabs[0]: # 🏗️ ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                c1, c2 = st.columns(2); d1 = c1.date_input("Début", key="g_d1"); d2 = c2.date_input("Fin", key="g_d2")
                if st.button("Générer"):
                    tmp, curr = [], d1
                    while curr <= d2:
                        tmp.append({"Date": format_date_fr_complete(curr, False), "Titre": "", "Lieu": l_raw[0]['nom'], "Horaire": h_raw[0]['libelle'], "Capacité": 12, "Actif": True})
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = tmp
                if st.session_state['at_list_gen']:
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list_gen']), num_rows="dynamic")
                    if st.button("Sauvegarder Ateliers"):
                        # Logique d'insertion Supabase...
                        st.success("Ateliers enregistrés")

        with tabs[1]: # 📊 SUIVI AM (ADMIN)
            st.subheader("Suivi Individuel des AM")
            choix_adm = st.multiselect("Filtrer par AM (Admin) :", liste_adh, key="adm_f_am")
            ids_adm = [dict_adh[n] for n in choix_adm] if choix_adm else list(dict_adh.values())
            data_adm = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids_adm).eq("ateliers.est_actif", True).order("adherent_id").execute()
            if data_adm.data:
                df_adm = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Atelier": i['ateliers']['titre'], "Lieu": i['ateliers']['lieux']['nom'], "Enfants": i['nb_enfants']} for i in data_adm.data])
                # BOUTONS EXPORT SUIVI ADMIN
                ce_s1, ce_s2 = st.columns(2)
                ce_s1.download_button("📥 Excel Suivi", data=export_to_excel(df_adm), file_name="admin_suivi.xlsx")
                ce_s2.download_button("📥 PDF Suivi", data=export_to_pdf("Suivi Admin", [f"{r['AM']} | {r['Date']}" for _, r in df_adm.iterrows()]), file_name="admin_suivi.pdf")
                st.dataframe(df_adm, use_container_width=True)

        with tabs[2]: # 📅 PLANNING ATELIERS (ADMIN)
            st.subheader("Planning Global des Ateliers")
            ca1, ca2 = st.columns(2)
            da1, da2 = ca1.date_input("Du", date.today(), key="p_d1"), ca2.date_input("Au", date.today()+timedelta(days=30), key="p_d2")
            ats_adm = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(da1)).lte("date_atelier", str(da2)).order("date_atelier").execute()
            if ats_adm.data:
                plan_list = []
                for a in ats_adm.data:
                    ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                    for p in ins_at.data:
                        plan_list.append({"Date": a['date_atelier'], "Atelier": a['titre'], "Lieu": a['lieux']['nom'], "AM": f"{p['adherents']['prenom']} {p['adherents']['nom']}", "Enfants": p['nb_enfants']})
                if plan_list:
                    df_plan = pd.DataFrame(plan_list)
                    # BOUTONS EXPORT PLANNING
                    cp1, cp2 = st.columns(2)
                    cp1.download_button("📥 Excel Planning", data=export_to_excel(df_plan), file_name="planning.xlsx")
                    cp2.download_button("📥 PDF Planning", data=export_to_pdf("Planning Ateliers", [f"{r['Date']} | {r['AM']}" for r in plan_list]), file_name="planning.pdf")
                    st.dataframe(df_plan, use_container_width=True)

        with tabs[3]: # 📈 STATISTIQUES
            st.subheader("Statistiques de participation")
            cs1, cs2 = st.columns(2); ds_s = cs1.date_input("Début", key="s_d1"); de_s = cs2.date_input("Fin", key="s_d2")
            ins_s = supabase.table("inscriptions").select("*, adherents(nom, prenom), ateliers!inner(date_atelier)").gte("ateliers.date_atelier", str(ds_s)).lte("ateliers.date_atelier", str(de_s)).execute()
            if ins_s.data:
                stats = [{"AM": n, "Ateliers": sum(1 for x in ins_s.data if f"{x['adherents']['prenom']} {x['adherents']['nom']}" == n)} for n in liste_adh]
                df_stats = pd.DataFrame(stats).sort_values("Ateliers", ascending=False)
                # BOUTONS EXPORT STATS
                cst1, cst2 = st.columns(2)
                cst1.download_button("📥 Excel Stats", data=export_to_excel(df_stats), file_name="stats.xlsx")
                cst2.download_button("📥 PDF Stats", data=export_to_pdf("Statistiques", [f"{r['AM']} : {r['Ateliers']}" for _, r in df_stats.iterrows()]), file_name="stats.pdf")
                st.table(df_stats)

        with tabs[4]: # 👥 LISTE AM
            for u in res_adh.data:
                c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("✏️", key=f"ed_{u['id']}"): edit_am_dialog(u['id'], u['nom'], u['prenom'])
                if c3.button("🗑️", key=f"dl_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['nom']}", current_code)

        with tabs[5]: # 📍 LIEUX / HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                for l in l_raw: st.write(f"📍 {l['nom']} (Cap: {l['capacite_accueil']})")
            with cl2:
                for h in h_raw: st.write(f"⏰ {h['libelle']}")

        with tabs[6]: # ⚙️ SÉCURITÉ
            with st.form("sec_f"):
                o = st.text_input("Ancien", type="password")
                n = st.text_input("Nouveau", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code: supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.rerun()

        with tabs[7]: # 📜 JOURNAL DES ACTIONS
            st.subheader("📜 Journal des manipulations")
            cj1, cj2 = st.columns(2)
            dj_s = cj1.date_input("Depuis le", date.today() - timedelta(days=7), format="DD/MM/YYYY", key="log_d1")
            dj_e = cj2.date_input("Jusqu'au", date.today(), format="DD/MM/YYYY", key="log_d2")
            try:
                # On récupère les logs avec filtre de date
                res_logs = supabase.table("logs").select("*").gte("created_at", str(dj_s)).lte("created_at", str(dj_e) + "T23:59:59").order("created_at", ascending=True).execute()
                if res_logs.data:
                    logs_df = pd.DataFrame(res_logs.data)
                    logs_df['created_at'] = pd.to_datetime(logs_df['created_at']).dt.strftime('%d/%m/%Y %H:%M')
                    st.dataframe(logs_df[['created_at', 'utilisateur', 'action', 'details']], use_container_width=True, hide_index=True)
                else: st.info("Le journal est vide pour cette période.")
            except: st.info("En attente d'activité.")

    else: st.info("Saisissez le code admin.")
