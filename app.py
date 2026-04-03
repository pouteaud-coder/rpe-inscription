import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
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
    .badge-verrouille { background-color: #e65100; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; margin-left: 6px; }
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

def heure_paris_fr():
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    now = datetime.now(ZoneInfo("Europe/Paris"))
    return f"le {jours[now.weekday()]} {now.day} {mois[now.month - 1]} {now.year} à {now.hour:02d}h{now.minute:02d}"

def enregistrer_log(utilisateur, action, details):
    try:
        heure_str = heure_paris_fr()
        supabase.table("logs").insert({
            "utilisateur": utilisateur,
            "action": action,
            "details": f"{details} [{heure_str}]"
        }).execute()
    except:
        pass

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    res = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{res}**" if gras else res

def format_date_fr_simple(date_str):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    try:
        d = datetime.strptime(str(date_str), '%Y-%m-%d')
        return f"{jours[d.weekday()]} {d.day} {mois[d.month-1]} {d.year}"
    except:
        return str(date_str)

def parse_date_fr_to_iso(date_str):
    clean = str(date_str).replace("**", "").strip()
    parts = clean.split(" ")
    if len(parts) < 4: return date_str
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    try: m = months.index(parts[2].lower()) + 1
    except: m = 1
    return f"{parts[3]}-{m:02d}-{int(parts[1]):02d}"

def is_verrouille(at):
    return bool(at.get("Verrouille", at.get("verrouille", False)))

def trier_par_nom_puis_date(data):
    return sorted(data, key=lambda i: (
        i['adherents']['nom'].upper(),
        i['adherents']['prenom'].upper(),
        i['ateliers']['date_atelier']
    ))

# --- FONCTIONS D'EXPORT ---
def export_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Export')
    return output.getvalue()

def export_suivi_am_pdf(title, data_triee):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(6)
    curr_am = ""
    for i in data_triee:
        nom_am = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
        at = i['ateliers']
        if nom_am != curr_am:
            pdf.ln(3)
            pdf.set_fill_color(27, 94, 32)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 9, f"  {nom_am}".encode('latin-1', 'replace').decode('latin-1'), ln=True, fill=True)
            pdf.set_text_color(0, 0, 0)
            curr_am = nom_am
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, f"  {format_date_fr_simple(at['date_atelier'])}".encode('latin-1', 'replace').decode('latin-1'), ln=True)
        pdf.set_font("Arial", size=10)
        detail = f"     {at.get('titre', '')}  | {at['lieux']['nom']} | {at['horaires']['libelle']} | {i['nb_enfants']} enfant(s)"
        pdf.cell(0, 6, detail.encode('latin-1', 'replace').decode('latin-1'), ln=True)
    return pdf.output(dest='S').encode('latin-1')

def export_planning_ateliers_pdf(title, ateliers_data, get_inscrits_fn):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(6)
    for a in ateliers_data:
        ins_at = get_inscrits_fn(a['id'])
        t_ad, t_en = len(ins_at), sum([p['nb_enfants'] for p in ins_at])
        pdf.set_fill_color(224, 235, 245)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, f"  {format_date_fr_simple(a['date_atelier'])} | {a.get('titre', '')}".encode('latin-1', 'replace').decode('latin-1'), ln=True, fill=True)
        pdf.set_font("Arial", size=10)
        sous = f"     Lieu : {a['lieux']['nom']} | Horaire : {a['horaires']['libelle']} | AM : {t_ad} | Enfants : {t_en}"
        pdf.cell(0, 6, sous.encode('latin-1', 'replace').decode('latin-1'), ln=True)
        for p in sorted(ins_at, key=lambda x: x['adherents']['nom'].upper()):
            pdf.cell(0, 6, f"       • {p['adherents']['prenom']} {p['adherents']['nom']} ({p['nb_enfants']} enf.)".encode('latin-1', 'replace').decode('latin-1'), ln=True)
        pdf.ln(3)
    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment désactiver/supprimer : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer", type="primary"):
        if pw == current_code or pw == "0000":
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Opération réussie")
            st.rerun()
        else: st.error("Code incorrect")

@st.dialog("⚠️ Confirmer la désinscription")
def confirm_unsubscribe_dialog(ins_id, nom_complet, atelier_info, user_admin="Utilisateur"):
    st.warning(f"Souhaitez-vous vraiment annuler la réservation de **{nom_complet}** ?")
    if st.button("Oui, désinscrire", type="primary"):
        enregistrer_log(user_admin, "Désinscription", f"Annulation pour {nom_complet} - {atelier_info}")
        supabase.table("inscriptions").delete().eq("id", ins_id).execute()
        st.rerun()

# --- CHARGEMENT DONNÉES ---
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
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    if user_principal != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | {at['lieux']['nom']} | {restantes} pl."):
                if is_verrouille(at):
                    st.warning("🔒 Atelier verrouillé par l'administration.")
                for i in res_ins.data:
                    n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    c_n, c_p = st.columns([0.88, 0.12])
                    c_n.write(f"• {n_f} ({i['nb_enfants']} enf.)")
                    if not is_verrouille(at) and c_p.button("🗑️", key=f"del_{i['id']}"):
                        confirm_unsubscribe_dialog(i['id'], n_f, at['date_atelier'], user_principal)
                if not is_verrouille(at):
                    st.markdown("---")
                    c1, c2, c3 = st.columns([2, 1, 1])
                    qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                    nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                    if c3.button("Valider", key=f"v_{at['id']}", type="primary") and qui != "Choisir...":
                        supabase.table("inscriptions").insert({"adherent_id": dict_adh[qui], "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                        enregistrer_log(user_principal, "Inscription", f"{qui} (+{nb_e} enf.)")
                        st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par AM :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).execute()
        if data.data:
            data_triee = trier_par_nom_puis_date(data.data)
            df_exp = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Lieu": i['ateliers']['lieux']['nom'], "Enfants": i['nb_enfants']} for i in data_triee])
            # BOUTONS D'EXPORT RETROUVÉS ICI
            ce1, ce2 = st.columns(2)
            ce1.download_button("📥 Excel", data=export_to_excel(df_exp), file_name="suivi_am.xlsx")
            ce2.download_button("📥 PDF", data=export_suivi_am_pdf("Suivi AM", data_triee), file_name="suivi_am.pdf")
            curr_u = ""
            for i in data_triee:
                nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom_u != curr_u:
                    st.subheader(nom_u)
                    curr_u = nom_u
                st.write(f"{format_date_fr_complete(i['ateliers']['date_atelier'])} — {i['ateliers']['titre']} ({i['nb_enfants']} enf.)")

    with t2:
        d_s = st.date_input("Du", date.today())
        d_e = st.date_input("Au", d_s + timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_s)).lte("date_atelier", str(d_e)).order("date_atelier").execute()
        if ats.data:
            cache_ins = {a['id']: supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute().data for a in ats.data}
            # BOUTONS D'EXPORT RETROUVÉS ICI AUSSI
            ce1, ce2 = st.columns(2)
            ce1.download_button("📥 Excel Planning", data=export_to_excel(pd.DataFrame([{"Date": a['date_atelier'], "AM": f"{p['adherents']['prenom']} {p['adherents']['nom']}"} for a in ats.data for p in cache_ins[a['id']]])), file_name="planning.xlsx")
            ce2.download_button("📥 PDF Planning", data=export_planning_ateliers_pdf("Planning", ats.data, lambda aid: cache_ins[aid]), file_name="planning.pdf")
            for a in ats.data:
                st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['lieux']['nom']}")

# ==========================================
# SECTION 🔐 ADMINISTRATION (Simplifiée pour la démo)
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret admin", type="password")
    if pw == current_code:
        st.success("Accès autorisé")
        # Ajoutez ici les onglets d'administration habituels (Gestion ateliers, Lieux, Logs...)
