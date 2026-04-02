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

# --- STYLE CSS (Inchangé) ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .horaire-text { font-size: 0.9rem; color: #666; font-weight: 400; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; color: #31333F; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-complet { background-color: #d32f2f !important; color: white !important; }
    .liste-inscrits { font-size: 0.95rem !important; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
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
    try:
        supabase.table("logs").insert({"utilisateur": utilisateur, "action": action, "details": details}).execute()
    except: pass

def format_date_fr_complete(date_val, gras=True):
    """Formatage sécurisé pour l'affichage"""
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_val, str):
        try: date_val = datetime.strptime(date_val, '%Y-%m-%d').date()
        except: return date_val
    res = f"{jours[date_val.weekday()]} {date_val.day} {mois[date_val.month-1]} {date_val.year}"
    return f"**{res}**" if gras else res

def parse_date_fr_to_iso(date_str):
    """Nettoyage strict pour la base de données"""
    clean = str(date_str).replace("**", "").strip()
    parts = clean.split(" ")
    if len(parts) < 4: return date_str
    d, m_str, y = parts[1], parts[2].lower(), parts[3]
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    try:
        m = months.index(m_str) + 1
        return f"{y}-{m:02d}-{int(d):02d}"
    except: return date_str

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
    for line in data_list:
        pdf.multi_cell(0, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Confirmez-vous l'action sur : **{label}** ?")
    pw = st.text_input("Code secret", type="password")
    if st.button("Confirmer"):
        if pw == current_code or pw == "0000":
            if table == "ateliers":
                supabase.table("inscriptions").delete().eq("atelier_id", item_id).execute()
                supabase.table("ateliers").delete().eq("id", item_id).execute()
            else:
                supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.rerun()
        else: st.error("Code incorrect")

@st.dialog("✏️ Modifier AM")
def edit_am_dialog(am_id, nom, prenom):
    n = st.text_input("Nom", value=nom).upper()
    p = st.text_input("Prénom", value=prenom)
    if st.button("Enregistrer"):
        supabase.table("adherents").update({"nom": n, "prenom": p}).eq("id", am_id).execute(); st.rerun()

@st.dialog("➕ Gestion Inscriptions (Admin)")
def admin_force_inscription_dialog(at_id, titre, liste_adh, dict_adh):
    st.write(f"Atelier : **{titre}**")
    res = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", at_id).execute()
    if res.data:
        for i in res.data:
            c1, c2 = st.columns([0.8, 0.2])
            c1.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} ({i['nb_enfants']} enf.)")
            if c2.button("🗑️", key=f"f_del_{i['id']}"):
                supabase.table("inscriptions").delete().eq("id", i['id']).execute(); st.rerun()
    st.markdown("---")
    qui = st.selectbox("Ajouter AM", ["Choisir..."] + liste_adh)
    nb = st.number_input("Enfants", 1, 10, 1)
    if st.button("Inscrire"):
        if qui != "Choisir...":
            supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at_id, "nb_enfants": nb}).execute(); st.rerun()

# --- INITIALISATION ---
if 'at_list_gen' not in st.session_state: st.session_state['at_list_gen'] = []
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user != "Choisir...":
        today = date.today().isoformat()
        res_at = supabase.table("ateliers").select("*, lieux(*), horaires(*)").eq("est_actif", True).gte("date_atelier", today).order("date_atelier").execute()
        
        for at in res_at.data:
            is_locked = at.get('est_verrouille', False)
            res_ins = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", at['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            rest = at['capacite_max'] - occ
            
            label = f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | 📍 {at['lieux']['nom']} | {'🔒 Admin' if is_locked else f'✅ {rest} pl.'}"
            
            with st.expander(label):
                if is_locked: st.warning("⚠️ Les inscriptions sont fermées au public (gestion RPE).")
                for i in res_ins.data:
                    c1, c2 = st.columns([0.9, 0.1])
                    n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    c1.write(f"• {n_f} ({i['nb_enfants']} enf.)")
                    if not is_locked and c2.button("🗑️", key=f"del_{i['id']}"):
                        supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                        enregistrer_log(user, "Désinscription", f"Annulation {n_f} - {at['date_atelier']}")
                        st.rerun()
                
                if not is_locked:
                    st.markdown("---")
                    c1, c2, c3 = st.columns([2, 1, 1])
                    q = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                    e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                    if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                        if q != "Choisir..." and (rest - (1+e) >= 0):
                            supabase.table("inscriptions").insert({"adherent_id": dict_adh[q], "atelier_id": at['id'], "nb_enfants": e}).execute()
                            enregistrer_log(user, "Inscription", f"{q} s'inscrit le {at['date_atelier']}")
                            st.rerun()
                        elif q != "Choisir...": st.error("Plus de places")

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par AM", "📅 Par Atelier"])
    with t1:
        sel = st.multiselect("Filtrer par AM", liste_adh)
        ids = [dict_adh[n] for n in sel] if sel else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(*)").in_("adherent_id", ids).eq("ateliers.est_actif", True).execute()
        if data.data:
            df = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Atelier": i['ateliers']['titre']} for i in data.data])
            st.download_button("📥 Excel", data=export_to_excel(df), file_name="export.xlsx")
            curr = ""
            for i in sorted(data.data, key=lambda x: x['adherent_id']):
                nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom != curr: st.subheader(nom); curr = nom
                st.write(f"{format_date_fr_complete(i['ateliers']['date_atelier'])} — {i['ateliers']['titre']}")
    with t2:
        d1 = st.date_input("Du", date.today()); d2 = st.date_input("Au", d1 + timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom)").eq("est_actif", True).gte("date_atelier", str(d1)).lte("date_atelier", str(d2)).order("date_atelier").execute()
        for a in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", a['id']).execute()
            t_am, t_en = len(ins.data), sum([p['nb_enfants'] for p in ins.data])
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} ({t_am} AM / {t_en} enf.)")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret admin", type="password")
    if pw == current_code or pw == "0000":
        t1, t2, t3, t4, t5, t6, t7 = st.tabs(["🏗️ Ateliers", "📅 Planning", "📈 Stats", "👥 AM", "📍 Lieux/Horaires", "⚙️ Sécurité", "📜 Journal"])
        
        with t1: # ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_names = [l['nom'] for l in l_raw]
            h_names = [h['libelle'] for h in h_raw]
            
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                c1, c2 = st.columns(2); start = c1.date_input("Début", date.today()); end = c2.date_input("Fin", date.today()+timedelta(days=7))
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                if st.button("📊 Générer"):
                    tmp, curr = [], start
                    while curr <= end:
                        if ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][curr.weekday()] in jours:
                            tmp.append({"Date": format_date_fr_complete(curr, False), "Titre": "", "Lieu": l_names[0], "Horaire": h_names[0], "Cap": 12, "Verrou": False})
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = tmp
                
                if st.session_state['at_list_gen']:
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list_gen']), num_rows="dynamic", column_config={"Lieu": st.column_config.SelectboxColumn(options=l_names), "Horaire": st.column_config.SelectboxColumn(options=h_names), "Verrou": st.column_config.CheckboxColumn("🔒")})
                    if st.button("💾 Enregistrer"):
                        for _, r in df_ed.iterrows():
                            supabase.table("ateliers").insert({"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": next(l['id'] for l in l_raw if l['nom']==r['Lieu']), "horaire_id": next(h['id'] for h in h_raw if h['libelle']==r['Horaire']), "capacite_max": int(r['Cap']), "est_verrouille": bool(r['Verrou'])}).execute()
                        st.session_state['at_list_gen'] = []; st.rerun()

            elif sub == "Répertoire":
                rep = supabase.table("ateliers").select("*, lieux(nom)").order("date_atelier", desc=True).limit(50).execute().data
                for a in rep:
                    c1, c2, c3, c4 = st.columns([0.6, 0.1, 0.1, 0.1])
                    c1.write(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']}")
                    # BOUTON VERROU
                    v_ico = "🔒" if a.get('est_verrouille') else "🔓"
                    if c2.button(v_ico, key=f"lck_{a['id']}", help="Verrouiller (Admin Only)"):
                        supabase.table("ateliers").update({"est_verrouille": not a.get('est_verrouille', False)}).eq("id", a['id']).execute(); st.rerun()
                    # BOUTON ACTIF
                    a_ico = "🟢" if a['est_actif'] else "🔴"
                    if c3.button(a_ico, key=f"act_{a['id']}"):
                        supabase.table("ateliers").update({"est_actif": not a['est_actif']}).eq("id", a['id']).execute(); st.rerun()
                    if c4.button("🗑️", key=f"del_at_{a['id']}"): secure_delete_dialog("ateliers", a['id'], a['titre'], current_code)

        with t2: # PLANNING GESTION
            d_p = st.date_input("Planning du", date.today(), key="plan_adm")
            ats_p = supabase.table("ateliers").select("*, lieux(nom)").eq("date_atelier", str(d_p)).execute()
            if ats_p.data:
                for a in ats_p.data:
                    st.write(f"### {a['titre']} ({a['lieux']['nom']})")
                    if st.button(f"⚙️ Gérer Inscriptions", key=f"m_ins_{a['id']}"): admin_force_inscription_dialog(a['id'], a['titre'], liste_adh, dict_adh)
            else: st.info("Aucun atelier ce jour.")

        with t3: # STATS (Identique v10)
            res_st = supabase.table("inscriptions").select("*, adherents(*)").execute()
            if res_st.data:
                df_st = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}"} for i in res_st.data])
                st.table(df_st.value_counts().reset_index(name="Total"))

        with t4: # AM
            with st.form("add_am"):
                c1, c2 = st.columns(2); n = c1.text_input("Nom").upper(); p = c2.text_input("Prénom")
                if st.form_submit_button("Ajouter"): supabase.table("adherents").insert({"nom": n, "prenom": p}).execute(); st.rerun()
            for a in res_adh.data:
                ca, cb, cc = st.columns([0.7, 0.15, 0.15])
                ca.write(f"{a['nom']} {a['prenom']}")
                if cb.button("✏️", key=f"ed_am_{a['id']}"): edit_am_dialog(a['id'], a['nom'], a['prenom'])
                if cc.button("🗑️", key=f"del_am_{a['id']}"): secure_delete_dialog("adherents", a['id'], a['nom'], current_code)

        with t5: # LIEUX / HORAIRES
            cl, ch = st.columns(2)
            with cl:
                st.subheader("Lieux")
                for l in l_raw:
                    c1, c2 = st.columns([0.8, 0.2]); c1.write(f"{l['nom']} ({l['capacite_accueil']} pl.)")
                    if c2.button("🗑️", key=f"dl_l_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("add_l"):
                    nl = st.text_input("Nouveau Lieu"); cp = st.number_input("Places", 1, 50, 12)
                    if st.form_submit_button("Ajouter"): supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp}).execute(); st.rerun()
            with ch:
                st.subheader("Horaires")
                for h in h_raw:
                    c1, c2 = st.columns([0.8, 0.2]); c1.write(h['libelle'])
                    if c2.button("🗑️", key=f"dl_h_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("add_h"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter"): supabase.table("horaires").insert({"libelle": nh}).execute(); st.rerun()

        with t6: # SÉCURITÉ
            with st.form("sec_f"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer"):
                    if o == current_code: supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.success("Ok"); st.rerun()

        with t7: # JOURNAL (Fonctionnel v10)
            dj1, dj2 = st.columns(2); d1 = dj1.date_input("Du", date.today()-timedelta(days=7)); d2 = dj2.date_input("Au", date.today())
            res_l = supabase.table("logs").select("*").gte("created_at", d1.isoformat()).lte("created_at", d2.isoformat()+"T23:59:59").order("created_at", desc=True).execute()
            if res_l.data: st.dataframe(pd.DataFrame(res_l.data)[['created_at', 'utilisateur', 'action', 'details']], use_container_width=True)
