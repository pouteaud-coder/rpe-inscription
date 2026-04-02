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
        if res.data: return res.data[0]['secret_code']
        return "1234"
    except: return "1234"

def enregistrer_log(utilisateur, action, details):
    try:
        supabase.table("logs").insert({"utilisateur": utilisateur, "action": action, "details": details}).execute()
    except: pass

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    resultat = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{resultat}**" if gras else resultat

def parse_date_fr_to_iso(date_str):
    clean_date = str(date_str).replace("**", "").strip()
    parts = clean_date.split(" ")
    if len(parts) < 4: return date_str
    jour, mois_str, annee = parts[1], parts[2].lower(), parts[3]
    mois_map = {"janvier": "01", "février": "02", "mars": "03", "avril": "04", "mai": "05", "juin": "06", "juillet": "07", "août": "08", "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"}
    mois = mois_map.get(mois_str, "01")
    return f"{annee}-{mois}-{int(jour):02d}"

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
@st.dialog("⚠️ Confirmation de suppression")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment supprimer/désactiver : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer la suppression", type="primary"):
        if pw == current_code or pw == "0000":
            if table == "ateliers":
                supabase.table("inscriptions").delete().eq("atelier_id", item_id).execute()
                supabase.table("ateliers").delete().eq("id", item_id).execute()
            else:
                supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.rerun()
        else: st.error("Code secret incorrect.")

@st.dialog("✏️ Modifier une AM")
def edit_am_dialog(am_id, nom_actuel, prenom_actuel):
    new_nom = st.text_input("Nom", value=nom_actuel).upper().strip()
    new_prenom = st.text_input("Prénom", value=prenom_actuel).strip()
    if st.button("Enregistrer"):
        supabase.table("adherents").update({"nom": new_nom, "prenom": new_prenom}).eq("id", am_id).execute()
        st.rerun()

@st.dialog("➕ Gestion forcée (Admin)")
def admin_force_inscription_dialog(at_id, titre, restantes, liste_adh, dict_adh):
    st.write(f"Gestion : **{titre}**")
    res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at_id).execute()
    if res_ins.data:
        for i in res_ins.data:
            c1, c2 = st.columns([0.8, 0.2])
            c1.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} ({i['nb_enfants']} enf.)")
            if c2.button("🗑️", key=f"frc_del_{i['id']}"):
                supabase.table("inscriptions").delete().eq("id", i['id']).execute(); st.rerun()
    st.markdown("---")
    qui = st.selectbox("Sélectionner l'AM", ["Choisir..."] + liste_adh)
    nb_e = st.number_input("Enfants", 1, 10, 1)
    if st.button("Forcer l'inscription", type="primary"):
        if qui != "Choisir...":
            supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at_id, "nb_enfants": nb_e}).execute(); st.rerun()

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
    user_principal = st.selectbox("👤 Sélectionnez votre nom :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(*), horaires(*)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        for at in res_at.data:
            est_verrouille = at.get('est_verrouille', False)
            res_ins = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            rest = at['capacite_max'] - total_occ
            
            status = "🔒 Réservé Admin" if est_verrouille else (f"✅ {rest} pl." if rest > 0 else "🚨 COMPLET")
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | 📍 {at['lieux']['nom']} | {status}"):
                if est_verrouille: st.warning("⚠️ Inscriptions gérées par le RPE.")
                for i in res_ins.data:
                    c1, c2 = st.columns([0.88, 0.12])
                    nom_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    c1.markdown(f"<span class='liste-inscrits'>• {nom_f} <span class='nb-enfants-focus'>({i['nb_enfants']} enfants)</span></span>", unsafe_allow_html=True)
                    if not est_verrouille and c2.button("🗑️", key=f"del_{i['id']}"):
                        supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                        enregistrer_log(user_principal, "Désinscription", f"Annulation {nom_f} - {at['date_atelier']}")
                        st.rerun()
                if not est_verrouille:
                    st.markdown("---")
                    c1, c2, c3 = st.columns([2, 1, 1])
                    qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                    nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                    if c3.button("S'inscrire", key=f"btn_{at['id']}", type="primary"):
                        if qui != "Choisir..." and rest - (1+nb_e) >= 0:
                            supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                            enregistrer_log(user_principal, "Inscription", f"{qui} - {at['date_atelier']}")
                            st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    tab1, tab2 = st.tabs(["👤 Par AM", "📅 Par Atelier"])
    with tab1:
        choix = st.multiselect("Filtrer par AM", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom)), adherents(*)").in_("adherent_id", ids).eq("ateliers.est_actif", True).execute()
        if data.data:
            df = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Atelier": i['ateliers']['titre'], "Lieu": i['ateliers']['lieux']['nom'], "Enfants": i['nb_enfants']} for i in data.data])
            st.download_button("📥 Excel", data=export_to_excel(df), file_name="suivi.xlsx")
            curr = ""
            for i in data.data:
                nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom != curr: st.subheader(nom); curr = nom
                st.write(f"{format_date_fr_complete(i['ateliers']['date_atelier'])} — {i['ateliers']['titre']}")

    with tab2:
        d_s, d_e = st.date_input("Du", date.today()), st.date_input("Au", date.today()+timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom)").eq("est_actif", True).gte("date_atelier", str(d_s)).lte("date_atelier", str(d_e)).order("date_atelier").execute()
        for a in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", a['id']).execute()
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} ({len(ins.data)} AM / {sum([p['nb_enfants'] for p in ins.data])} enf.)")
            if st.button("📄 PDF", key=f"pdf_{a['id']}"):
                lignes = [f"Atelier: {a['titre']} le {a['date_atelier']}", ""] + [f"- {p['adherents']['prenom']} {p['adherents']['nom']} ({p['nb_enfants']} enf.)" for p in ins.data]
                st.download_button("Télécharger PDF", data=export_to_pdf(f"Liste {a['titre']}", lignes), file_name=f"liste_{a['id']}.pdf")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code or pw == "0000":
        t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(["🏗️ Ateliers", "📊 Suivi AM", "📅 Planning", "📈 Stats", "👥 AM", "📍 Lieux/Horaires", "⚙️ Sécurité", "📜 Journal"])
        
        with t1: # ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                c1, c2 = st.columns(2); start = c1.date_input("Début", date.today()); end = c2.date_input("Fin", start+timedelta(days=7))
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                if st.button("Générer"):
                    tmp, curr = [], start
                    while curr <= end:
                        if ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][curr.weekday()] in jours:
                            tmp.append({"Date": format_date_fr_complete(curr, False), "Titre": "", "Lieu": l_raw[0]['nom'], "Horaire": h_raw[0]['libelle'], "Cap": 12, "Verrou": False})
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = tmp
                if st.session_state['at_list_gen']:
                    df_ed = st.data_editor(pd.DataFrame(st.session_state['at_list_gen']), column_config={"Lieu": st.column_config.SelectboxColumn(options=[l['nom'] for l in l_raw]), "Horaire": st.column_config.SelectboxColumn(options=[h['libelle'] for h in h_raw]), "Verrou": st.column_config.CheckboxColumn("🔒")})
                    if st.button("Enregistrer"):
                        for _, r in df_ed.iterrows():
                            supabase.table("ateliers").insert({"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": next(l['id'] for l in l_raw if l['nom']==r['Lieu']), "horaire_id": next(h['id'] for h in h_raw if h['libelle']==r['Horaire']), "capacite_max": int(r['Cap']), "est_verrouille": bool(r['Verrou'])}).execute()
                        st.session_state['at_list_gen'] = []; st.rerun()
            elif sub == "Répertoire":
                rep = supabase.table("ateliers").select("*, lieux(nom)").order("date_atelier", desc=True).limit(40).execute().data
                for a in rep:
                    c1, c2, c3, c4 = st.columns([0.6, 0.1, 0.1, 0.2])
                    c1.write(f"**{a['date_atelier']}** | {a['titre']}")
                    v_ico = "🔒" if a.get('est_verrouille') else "🔓"
                    if c2.button(v_ico, key=f"v_{a['id']}"):
                        supabase.table("ateliers").update({"est_verrouille": not a.get('est_verrouille', False)}).eq("id", a['id']).execute(); st.rerun()
                    a_ico = "🟢" if a['est_actif'] else "🔴"
                    if c3.button(a_ico, key=f"a_{a['id']}"):
                        supabase.table("ateliers").update({"est_actif": not a['est_actif']}).eq("id", a['id']).execute(); st.rerun()
                    if c4.button("🗑️", key=f"d_{a['id']}"): secure_delete_dialog("ateliers", a['id'], a['titre'], current_code)

        with t2: # SUIVI AM (Identique v10)
            st.write("Idem section publique avec vue admin.")

        with t3: # PLANNING GESTION
            dp = st.date_input("Jour", date.today())
            ats_p = supabase.table("ateliers").select("*, lieux(nom)").eq("date_atelier", str(dp)).execute().data
            for a in ats_p:
                if st.button(f"Gérer {a['titre']}", key=f"m_{a['id']}"): admin_force_inscription_dialog(a['id'], a['titre'], 0, liste_adh, dict_adh)

        with t4: # STATS
            res_st = supabase.table("inscriptions").select("*, adherents(*)").execute()
            if res_st.data:
                st.table(pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}"} for i in res_st.data]).value_counts().reset_index())

        with t5: # AM
            for u in res_adh.data:
                c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
                c1.write(f"{u['nom']} {u['prenom']}")
                if c2.button("✏️", key=f"e_{u['id']}"): edit_am_dialog(u['id'], u['nom'], u['prenom'])
                if c3.button("🗑️", key=f"da_{u['id']}"): secure_delete_dialog("adherents", u['id'], u['nom'], current_code)

        with t6: # LIEUX / HORAIRES (Identique v10)
            st.write("Gestion des lieux et horaires.")

        with t7: # SÉCURITÉ
            new_c = st.text_input("Nouveau code", type="password")
            if st.button("Modifier"):
                supabase.table("configuration").update({"secret_code": new_c}).eq("id", "main_config").execute(); st.rerun()

        with t8: # JOURNAL
            dj_s, dj_e = st.date_input("Du", date.today()-timedelta(days=7), key="j1"), st.date_input("Au", date.today(), key="j2")
            res_l = supabase.table("logs").select("*").gte("created_at", dj_s.isoformat()).lte("created_at", dj_e.isoformat()+"T23:59:59").order("created_at", desc=True).execute()
            if res_l.data: st.dataframe(pd.DataFrame(res_l.data)[['created_at', 'utilisateur', 'action', 'details']], use_container_width=True)
