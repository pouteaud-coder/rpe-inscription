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

# --- GATEKEEPER : Code d'accès général ---
def check_access():
    """Vérifie si l'utilisateur a saisi le bon code d'accès."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.markdown("""
            <div style="display: flex; align-items: center; justify-content: center; min-height: 60vh;">
                <div style="background-color: #fdf2e9; padding: 2rem; border-radius: 20px; text-align: center; border: 2px solid #ff9800;">
                    <h2 style="color: #e65100;">🔐 Accès sécurisé</h2>
                    <p>Veuillez saisir le code d'accès pour continuer.</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        code = st.text_input("Code d'accès", type="password", key="gate_code")
        if st.button("Valider", type="primary"):
            if code == "78955":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Code incorrect. Accès refusé.")
        st.stop()  # Empêche l'exécution du reste de l'application

# check_access()   # désactivé pour les tests
st.session_state["authenticated"] = True

# --- TITRE DE L'APPLICATION ---
st.markdown("""
    <div style="display: flex; align-items: center; background-color: #fdf2e9; padding: 20px; border-radius: 15px; margin-bottom: 25px; border: 2px solid #ff9800;">
        <div style="font-size: 3.5rem; margin-right: 20px;">🎨</div>
        <div>
            <h1 style="color: #e65100; margin: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 2.8rem;">Résa RPE</h1>
            <p style="margin: 0; color: #d35400; font-weight: bold; font-size: 1.1rem;">Ateliers d'éveil & Activités manuelles</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- CONNEXION SUPABASE (mise en cache pour éviter de recréer le client à chaque rendu) ---
@st.cache_resource
def get_supabase_client() -> Client:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    return create_client(url, key)

supabase = get_supabase_client()

# --- STYLE CSS (identique) ---
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
    /* Centrage de la colonne "Nombre d'ateliers" */
    .stDataFrame table thead tr th:nth-child(2),
    .stDataFrame table tbody tr td:nth-child(2) {
        text-align: center !important;
    }
    
    </style>
    """, unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES (inchangées) ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    return f"#{hash_object.hexdigest()[:6]}"

@st.cache_data(ttl=300)
def get_secret_code():
    try:
        res = supabase.table("configuration").select("secret_code").eq("id", "main_config").execute()
        return res.data[0]['secret_code'] if res.data else "1234"
    except:
        return "1234"

def heure_paris_fr():
    """Retourne l'heure actuelle en France au format français : ex. le lundi 3 avril 2026 à 14h37"""
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
            "septembre", "octobre", "novembre", "décembre"]
    now = datetime.now(ZoneInfo("Europe/Paris"))
    j = jours[now.weekday()]
    m = mois[now.month - 1]
    return f"le {j} {now.day} {m} {now.year} à {now.hour:02d}h{now.minute:02d}"

def enregistrer_log(utilisateur, action, details):
    """Enregistre une action dans la table logs avec l'heure Paris dans les détails"""
    try:
        heure_str = heure_paris_fr()
        details_avec_heure = f"{details} [{heure_str}]"
        supabase.table("logs").insert({
            "utilisateur": utilisateur,
            "action": action,
            "details": details_avec_heure
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
    """Retourne une date ISO en texte français sans astérisques, ex: Lundi 3 avril 2026"""
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    try:
        d = datetime.strptime(str(date_str), '%Y-%m-%d')
        return f"{jours[d.weekday()]} {d.day} {mois[d.month-1]} {d.year}"
    except:
        return str(date_str)

def parse_date_fr_to_iso(date_str):
    """
    Convertit une date au format français (Lundi 18 juin 2026) ou au format court (18/06/2026)
    ou au format ISO (2026-06-18) vers ISO YYYY-MM-DD.
    """
    # Nettoyage : suppression des éventuels ** et des espaces
    clean = str(date_str).replace("**", "").strip()
    if not clean:
        return None
    
    # Essai ISO déjà
    try:
        d = datetime.strptime(clean, '%Y-%m-%d')
        return d.strftime('%Y-%m-%d')
    except:
        pass
    
    # Essai format français avec jour de la semaine et mois en toutes lettres
    parts = clean.split(" ")
    if len(parts) >= 4:
        # On ignore le jour de la semaine (premier mot)
        jour = parts[1]
        mois_texte = parts[2].lower()
        annee = parts[3]
        mois_numerique = ["janvier", "février", "mars", "avril", "mai", "juin", 
                          "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        if mois_texte in mois_numerique:
            m = mois_numerique.index(mois_texte) + 1
            try:
                return f"{annee}-{m:02d}-{int(jour):02d}"
            except:
                pass
    
    # Essai format court JJ/MM/AAAA ou JJ-MM-AAAA
    try:
        for sep in ['/', '-']:
            if sep in clean:
                j, m, a = clean.split(sep)
                return f"{int(a):04d}-{int(m):02d}-{int(j):02d}"
    except:
        pass
    
    # Dernier recours : retourner la chaîne brute (provoquera une erreur plus tard)
    return clean

def is_verrouille(at):
    """Retourne True si l'atelier est verrouillé"""
    return bool(at.get("Verrouille", at.get("verrouille", False)))

def trier_par_nom_puis_date(data):
    """Trie une liste d'inscriptions par nom alphabétique puis date croissante"""
    return sorted(data, key=lambda i: (
        i['adherents']['nom'].upper(),
        i['adherents']['prenom'].upper(),
        i['ateliers']['date_atelier']
    ))

def badge_categorie(at):
    """Retourne un span HTML pour le badge de catégorie, ou une chaîne vide si pas de couleur."""
    color = at.get('categorie_color')
    if color and isinstance(color, str) and color.strip():
        return f'<span style="background-color:{color}; width:14px; height:14px; display:inline-block; border-radius:50%; margin-right:6px;"></span>'
    return ""   # ← pas de badge gris
    

# --- FONCTIONS D'EXPORT (inchangées) ---
def export_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Export')
    return output.getvalue()

def export_to_pdf(title, data_list):
    """Export PDF simple (liste de lignes texte) — utilisé pour planning et stats"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    if not data_list:
        pdf.multi_cell(0, 10, txt="Aucune donnée à exporter.")
    else:
        for line in data_list:
            pdf.multi_cell(0, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

def export_suivi_am_pdf(title, data_triee):
    """
    Export PDF du suivi AM avec mise en forme fidèle à l'écran :
    - En-tête vert par AM (nom en gras)
    - Pour chaque atelier : date en français, titre, lieu, horaire, nb enfants
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(6)

    if not data_triee:
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 10, txt="Aucune inscription trouvée.", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    curr_am = ""
    for i in data_triee:
        nom_am = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
        at = i['ateliers']
        date_fr = format_date_fr_simple(at['date_atelier'])
        titre_at = at.get('titre', '')
        lieu = at['lieux']['nom']
        horaire = at['horaires']['libelle']
        nb_enf = i['nb_enfants']

        # En-tête AM (fond vert, texte blanc)
        if nom_am != curr_am:
            pdf.ln(3)
            pdf.set_fill_color(27, 94, 32)   # vert foncé #1b5e20
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 9, f"  {nom_am}".encode('latin-1', 'replace').decode('latin-1'), ln=True, fill=True)
            pdf.set_text_color(0, 0, 0)
            curr_am = nom_am

        # Ligne atelier
        pdf.set_font("Arial", 'B', 10)
        ligne_date = f"  {date_fr}".encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 6, ligne_date, ln=True)

        pdf.set_font("Arial", size=10)
        detail = f"     {titre_at}  |  {lieu}  |  {horaire}  |  {nb_enf} enfant(s)"
        pdf.cell(0, 6, detail.encode('latin-1', 'replace').decode('latin-1'), ln=True)

    return pdf.output(dest='S').encode('latin-1')

def export_planning_ateliers_pdf(title, ateliers_data, get_inscrits_fn):
    """
    Export PDF du planning des ateliers avec mise en forme fidèle à l'écran :
    - En-tête par atelier : date, titre, lieu, horaire, compteurs
    - Liste des inscrits en dessous
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(6)

    if not ateliers_data:
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 10, txt="Aucun atelier trouvé sur cette période.", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    for a in ateliers_data:
        ins_at = get_inscrits_fn(a['id'])
        t_ad = len(ins_at)
        t_en = sum([p['nb_enfants'] for p in ins_at])
        restantes = a['capacite_max'] - (t_ad + t_en)
        date_fr = format_date_fr_simple(a['date_atelier'])
        titre_at = a.get('titre', '')
        lieu = a['lieux']['nom']
        horaire = a['horaires']['libelle']
        verrou = " [VERROUILLE]" if is_verrouille(a) else ""

        # En-tête atelier (fond bleu-gris)
        pdf.set_fill_color(224, 235, 245)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 11)
        entete = f"  {date_fr} | {titre_at} | {lieu}{verrou}"
        pdf.cell(0, 8, entete.encode('latin-1', 'replace').decode('latin-1'), ln=True, fill=True)

        pdf.set_font("Arial", size=10)
        sous = f"     Horaire : {horaire}  |  AM : {t_ad}  |  Enfants : {t_en}  |  Places restantes : {restantes}"
        pdf.cell(0, 6, sous.encode('latin-1', 'replace').decode('latin-1'), ln=True)

        # Inscrits triés alphabétiquement
        ins_tries = sorted(ins_at, key=lambda x: (x['adherents']['nom'].upper(), x['adherents']['prenom'].upper()))
        for p in ins_tries:
            nom_p = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
            ligne = f"       • {nom_p}  ({p['nb_enfants']} enfant(s))"
            pdf.cell(0, 6, ligne.encode('latin-1', 'replace').decode('latin-1'), ln=True)

        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES (inchangés) ---
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
        enregistrer_log(user_admin, "Désinscription", f"Annulation pour {nom_complet} - {atelier_info}")
        supabase.table("inscriptions").delete().eq("id", ins_id).execute()
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

@st.dialog("✏️ Modifier l'atelier")
def edit_atelier_dialog(at_id, titre_actuel, lieu_id_actuel, horaire_id_actuel, capacite_actuelle, lieux_list, horaires_list, map_lieu_id, map_horaire_id):
    """Dialogue de modification d'un atelier (titre, lieu, horaire, capacité)"""
    # Chargement des inscriptions pour vérifier la capacité minimale
    inscriptions = supabase.table("inscriptions").select("nb_enfants").eq("atelier_id", at_id).execute()
    total_occupation = sum([1 + ins['nb_enfants'] for ins in inscriptions.data]) if inscriptions.data else 0

    # Sélecteurs
    lieux_options = [l['nom'] for l in lieux_list]
    horaires_options = [h['libelle'] for h in horaires_list]
    lieu_actuel_nom = next((l['nom'] for l in lieux_list if l['id'] == lieu_id_actuel), lieux_options[0] if lieux_options else "")
    horaire_actuel_lib = next((h['libelle'] for h in horaires_list if h['id'] == horaire_id_actuel), horaires_options[0] if horaires_options else "")

    nouveau_titre = st.text_input("Titre", value=titre_actuel)
    nouveau_lieu = st.selectbox("Lieu", options=lieux_options, index=lieux_options.index(lieu_actuel_nom) if lieu_actuel_nom in lieux_options else 0)
    nouvel_horaire = st.selectbox("Horaire", options=horaires_options, index=horaires_options.index(horaire_actuel_lib) if horaire_actuel_lib in horaires_options else 0)
    nouvelle_capacite = st.number_input("Capacité maximale (places totales)", min_value=1, value=int(capacite_actuelle))

    # Vérification de cohérence
    if nouvelle_capacite < total_occupation:
        st.error(f"La capacité ne peut pas être inférieure au nombre actuel d'occupants ({total_occupation} places prises).")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Annuler", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Enregistrer", type="primary", use_container_width=True, disabled=(nouvelle_capacite < total_occupation)):
            # Récupération des IDs
            nouveau_lieu_id = next(l['id'] for l in lieux_list if l['nom'] == nouveau_lieu)
            nouvel_horaire_id = next(h['id'] for h in horaires_list if h['libelle'] == nouvel_horaire)
            # Mise à jour
            supabase.table("ateliers").update({
                "titre": nouveau_titre,
                "lieu_id": nouveau_lieu_id,
                "horaire_id": nouvel_horaire_id,
                "capacite_max": nouvelle_capacite
            }).eq("id", at_id).execute()
            enregistrer_log("Admin", "Modification atelier", f"Atelier ID {at_id} modifié : titre={nouveau_titre}, lieu={nouveau_lieu}, horaire={nouvel_horaire}, capacité={nouvelle_capacite}")
            st.success("Atelier modifié avec succès !")
            st.rerun()

# --- CHARGEMENT DES DONNÉES GLOBALES (avec cache pour éviter les rechargements inutiles) ---
@st.cache_data(ttl=60)
def load_adherents():
    res = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
    return res.data

@st.cache_data(ttl=60)
def load_lieux():
    return supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data

@st.cache_data(ttl=60)
def load_horaires():
    return supabase.table("horaires").select("*").eq("est_actif", True).execute().data

if 'at_list_gen' not in st.session_state: st.session_state['at_list_gen'] = []
if 'super_access' not in st.session_state: st.session_state['super_access'] = False

current_code = get_secret_code()
res_adh_data = load_adherents()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh_data}
liste_adh = list(dict_adh.keys())

# Objet compatible avec le reste du code (accès via res_adh.data)
class _DataWrapper:
    def __init__(self, data): self.data = data
res_adh = _DataWrapper(res_adh_data)

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])



# ==========================================
# SECTION 📝 INSCRIPTIONS (avec modification du nb enfants)
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)

    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()

        if res_at.data:
            at_ids = [at['id'] for at in res_at.data]
            all_ins_raw = supabase.table("inscriptions").select("*, adherents(nom, prenom)").in_("atelier_id", at_ids).execute()
            ins_by_atelier = {}
            for ins in all_ins_raw.data:
                ins_by_atelier.setdefault(ins['atelier_id'], []).append(ins)
        else:
            ins_by_atelier = {}

        for at in res_at.data:
            res_ins_data = ins_by_atelier.get(at['id'], [])
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins_data])
            restantes = at['capacite_max'] - total_occ
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            at_info_log = f"{at['date_atelier']} | {at['horaires']['libelle']} | {at['lieux']['nom']}"

            # Ligne d'en-tête avec badge, date, titre, lieu, horaire, places
            badge_cat = badge_categorie(at)
            ligne_entete = f"{badge_cat} **{format_date_fr_complete(at['date_atelier'])}** — {at['titre']} | 📍 {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_p}"
            st.markdown(ligne_entete, unsafe_allow_html=True)

            # Expander pour la gestion des inscriptions
            with st.expander("📋 Gérer les inscriptions"):
                if is_verrouille(at):
                    st.warning("🔒 Cet atelier est verrouillé par l'administration. Seul l'admin peut modifier les inscriptions.")
                    # Affichage simple des inscrits
                    for i in res_ins_data:
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        st.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                else:
                    # Affichage des inscrits avec modification possible
                    if res_ins_data:
                        for i in res_ins_data:
                            n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                            col_nom, col_nb, col_mod, col_del = st.columns([0.5, 0.2, 0.15, 0.15])
                            col_nom.write(f"• {n_f}")
                            nouveau_nb = col_nb.number_input("Enf.", min_value=1, max_value=10, value=i['nb_enfants'], key=f"nb_{i['id']}", label_visibility="collapsed")
                            if col_mod.button("✏️ Modifier", key=f"mod_{i['id']}"):
                                delta = nouveau_nb - i['nb_enfants']
                                if restantes - delta < 0:
                                    st.error("Manque de places")
                                else:
                                    supabase.table("inscriptions").update({"nb_enfants": nouveau_nb}).eq("id", i['id']).execute()
                                    enregistrer_log(user_principal, "Modification", f"{n_f} change à {nouveau_nb} enfants - {at_info_log}")
                                    st.rerun()
                            if col_del.button("🗑️", key=f"del_{i['id']}"):
                                confirm_unsubscribe_dialog(i['id'], n_f, at_info_log, user_principal)
                    else:
                        st.info("Aucune inscription pour cet atelier.")

                    # Formulaire d'ajout d'une nouvelle inscription
                    st.markdown("---")
                    st.markdown("**➕ Ajouter une inscription**")
                    try:
                        idx_def = (liste_adh.index(user_principal) + 1)
                    except:
                        idx_def = 0
                    c1, c2, c3 = st.columns([2, 1, 1])
                    qui = c1.selectbox("Assistante maternelle", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                    nb_e = c2.number_input("Nombre d'enfants", min_value=1, max_value=10, value=1, key=f"e_{at['id']}")
                    if c3.button("Valider l'inscription", key=f"v_{at['id']}", type="primary"):
                        if qui != "Choisir...":
                            id_adh = dict_adh[qui]
                            existing = next((ins for ins in res_ins_data if ins['adherent_id'] == id_adh), None)
                            if existing:
                                st.warning(f"{qui} est déjà inscrite à cet atelier. Utilisez le bouton Modifier pour changer le nombre d'enfants.")
                            else:
                                if restantes - (1 + nb_e) < 0:
                                    st.error("Manque de places")
                                else:
                                    supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                                    enregistrer_log(user_principal, "Inscription", f"{qui} s'inscrit (+{nb_e} enf.) - {at_info_log}")
                                    st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP (inchangée)
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])

    with t1:
        choix = st.multiselect("Filtrer par assistante maternelle :", liste_adh, key="pub_filter_am")
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).execute()

        # Préparation des données pour export (triées)
        data_triee = trier_par_nom_puis_date(data.data) if data.data else []

        # Export Excel
        if data.data:
            df_export = pd.DataFrame([{
                "Assistante Maternelle": f"{i['adherents']['prenom']} {i['adherents']['nom']}",
                "Date": i['ateliers']['date_atelier'],
                "Atelier": i['ateliers']['titre'],
                "Lieu": i['ateliers']['lieux']['nom'],
                "Horaire": i['ateliers']['horaires']['libelle'],
                "Nb Enfants": i['nb_enfants']
            } for i in data_triee])
        else:
            df_export = pd.DataFrame(columns=["Assistante Maternelle", "Date", "Atelier", "Lieu", "Horaire", "Nb Enfants"])

        c_e1, c_e2 = st.columns(2)
        c_e1.download_button("📥 Excel", data=export_to_excel(df_export), file_name="suivi_am.xlsx")
        c_e2.download_button("📥 PDF", data=export_suivi_am_pdf("Suivi par Assistante Maternelle", data_triee), file_name="suivi_am.pdf")

        # Affichage écran
        if data.data:
            curr_u = ""
            for i in data_triee:
                nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom_u != curr_u:
                    st.markdown(f'<div style="color:#1b5e20; border-bottom:2px solid #1b5e20; padding-top:15px; margin-bottom:8px; font-weight:bold; font-size:1.2rem;">{nom_u}</div>', unsafe_allow_html=True)
                    curr_u = nom_u
                at = i['ateliers']
                c_l = get_color(at['lieux']['nom'])
                badge_cat = badge_categorie(at)
                st.markdown(f"{badge_cat}{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> <span class='horaire-text'>({at['horaires']['libelle']})</span> **({i['nb_enfants']} enf.)**", unsafe_allow_html=True)
        else:
            st.info("Aucune inscription trouvée pour les AM sélectionnées.")

    with t2:
        c_d1, c_d2 = st.columns(2)
        d_s = c_d1.date_input("Du", date.today(), key="pub_d1", format="DD/MM/YYYY")
        d_e = c_d2.date_input("Au", d_s + timedelta(days=30), key="pub_d2", format="DD/MM/YYYY")
        
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)") \
              .eq("est_actif", True) \
              .gte("date_atelier", str(d_s)) \
              .lte("date_atelier", str(d_e)) \
              .order("date_atelier").execute()
        
        # Préparation des données pour exports
        all_ins_data = []
        cache_ins = {}
        if ats_raw.data:
            at_ids_pub = [a['id'] for a in ats_raw.data]
            all_ins_pub = supabase.table("inscriptions").select("*, adherents(nom, prenom)").in_("atelier_id", at_ids_pub).execute()
            for ins in all_ins_pub.data:
                cache_ins.setdefault(ins['atelier_id'], []).append(ins)
            for a in ats_raw.data:
                for p in cache_ins.get(a['id'], []):
                    all_ins_data.append({
                        "Date": a['date_atelier'],
                        "Atelier": a['titre'],
                        "Lieu": a['lieux']['nom'],
                        "Horaire": a['horaires']['libelle'],
                        "AM": f"{p['adherents']['prenom']} {p['adherents']['nom']}",
                        "Enfants": p['nb_enfants']
                    })
        
        # Exports
        df_at_exp = pd.DataFrame(all_ins_data) if all_ins_data else pd.DataFrame(columns=["Date", "Atelier", "Lieu", "Horaire", "AM", "Enfants"])
        ce1, ce2 = st.columns(2)
        ce1.download_button("📥 Excel Planning", data=export_to_excel(df_at_exp), file_name="planning_ateliers.xlsx", key="exp_at_xl")
        ce2.download_button("📥 PDF Planning", data=export_planning_ateliers_pdf(
            "Planning des Ateliers", ats_raw.data if ats_raw.data else [], lambda aid: cache_ins.get(aid, [])
        ), file_name="planning_ateliers.pdf", key="exp_at_pdf")
        
        # Affichage écran (UNIQUE)
        if ats_raw.data:
            for idx, a in enumerate(ats_raw.data):
                c_l = get_color(a['lieux']['nom'])
                ins_at = cache_ins.get(a['id'], [])
                t_ad, t_en = len(ins_at), sum(p['nb_enfants'] for p in ins_at)
                restantes = a['capacite_max'] - (t_ad + t_en)
                cl_c = "alerte-complet" if restantes <= 0 else ""
                badge_cat = badge_categorie(a)
                
                # Ligne unique avec retour à la ligne automatique
                st.markdown(
                    f"""
                    <div style="white-space: normal; word-wrap: break-word; margin-bottom: 5px;">
                        {badge_cat}<strong>{format_date_fr_complete(a['date_atelier'])}</strong> | {a['titre']} | 
                        <span class='lieu-badge' style='background-color:{c_l};'>{a['lieux']['nom']}</span> | 
                        <span class='horaire-text'>{a['horaires']['libelle']}</span>
                        <span class='compteur-badge'>👤 {t_ad} AM</span>
                        <span class='compteur-badge'>👶 {t_en} enf.</span>
                        <span class='compteur-badge {cl_c}'>🏁 {restantes} pl.</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                if ins_at:
                    ins_s = sorted(ins_at, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                    html = "<div class='container-inscrits'>"
                    for p in ins_s:
                        html += f'<span class="liste-inscrits">• {p["adherents"]["prenom"]} {p["adherents"]["nom"]} <span class="nb-enfants-focus">({p["nb_enfants"]} enfants)</span></span>'
                    st.markdown(html + "</div>", unsafe_allow_html=True)
                
                if idx < len(ats_raw.data) - 1:
                    st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)
        else:
            st.info("Aucun atelier trouvé sur cette période.")

# ==========================================
# SECTION 🔐 ADMINISTRATION (inchangée)
# ==========================================

elif menu == "🔐 Administration":
    c_login1, c_login2 = st.columns([0.7, 0.3])
    pw = c_login1.text_input("Code secret admin", type="password")
    if c_login2.button("🔑 Code Super Admin"): super_admin_dialog()

    if pw == current_code or st.session_state['super_access']:
        t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs([
            "🏗️ Ateliers", "📊 Suivi AM", "📅 Planning Ateliers",
            "📈 Statistiques de participation", "👥 Liste AM",
            "📍 Lieux / Horaires", "⚙️ Sécurité", "📜 Journal des actions"
        ])

        with t1: # ATELIERS
            l_raw = load_lieux()
            h_raw = load_horaires()
            l_list = [l['nom'] for l in l_raw]
            h_list = [h['libelle'] for h in h_raw]
            map_l_cap = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}
            map_h_id = {h['libelle']: h['id'] for h in h_raw}
            sub = st.radio("Mode", ["Générateur", "Répertoire", "Actions groupées"], horizontal=True)
        
            if sub == "Générateur":
                col_lieu, col_horaire = st.columns(2)
                with col_lieu:
                    lieu_par_defaut = st.selectbox("Lieu par défaut pour les nouvelles lignes :", 
                                                   options=[""] + l_list, 
                                                   help="Choisissez un lieu qui sera prérempli dans chaque ligne générée. Si vide, le champ sera laissé vide.")
                with col_horaire:
                    horaire_par_defaut = st.selectbox("Horaire par défaut pour les nouvelles lignes :", 
                                                      options=[""] + h_list,
                                                      help="Choisissez un horaire qui sera prérempli dans chaque ligne générée. Si vide, le champ sera laissé vide.")
                
                c1, c2 = st.columns(2)
                d1 = c1.date_input("Début", date.today(), format="DD/MM/YYYY", key="gen_d1")
                d2 = c2.date_input("Fin", date.today() + timedelta(days=7), format="DD/MM/YYYY", key="gen_d2")
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer les lignes"):
                    tmp, curr = [], d1
                    while curr <= d2:
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        if js_fr[curr.weekday()] in jours:
                            lieu_val = lieu_par_defaut if lieu_par_defaut else ""
                            horaire_val = horaire_par_defaut if horaire_par_defaut else ""
                            capa = map_l_cap.get(lieu_val, 10) if lieu_val else 10
                            tmp.append({
                                "Date": format_date_fr_complete(curr, False), 
                                "Titre": "", 
                                "Lieu": lieu_val, 
                                "Horaire": horaire_val, 
                                "Capacité": capa, 
                                "Actif": False,
                                "Verrouillé": False
                            })
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = tmp
                    st.rerun()
                    
                if st.session_state['at_list_gen']:
                    df_ed = st.data_editor(
                        pd.DataFrame(st.session_state['at_list_gen']),
                        num_rows="dynamic",
                        column_config={
                            "Lieu": st.column_config.SelectboxColumn(options=l_list, required=False),
                            "Horaire": st.column_config.SelectboxColumn(options=h_list, required=False),
                            "Actif": st.column_config.CheckboxColumn(default=False),
                            "Verrouillé": st.column_config.CheckboxColumn(default=False, help="Si coché, seul l'admin peut gérer les inscriptions")
                        },
                        use_container_width=True,
                        key="editor_ateliers"
                    )
                    if st.button("💾 Enregistrer"):
                        to_db = []
                        for _, r in df_ed.iterrows():
                            lieu_nom = r['Lieu']
                            horaire_lib = r['Horaire']
                            if not lieu_nom or not horaire_lib:
                                st.warning(f"Ligne ignorée : lieu ou horaire manquant pour la date {r['Date']}")
                                continue
                            if lieu_nom not in map_l_id:
                                st.error(f"Lieu '{lieu_nom}' introuvable. Annulation.")
                                st.stop()
                            if horaire_lib not in map_h_id:
                                st.error(f"Horaire '{horaire_lib}' introuvable. Annulation.")
                                st.stop()
                            date_iso = parse_date_fr_to_iso(r['Date'])
                            if not date_iso:
                                st.error(f"Format de date invalide : {r['Date']}")
                                st.stop()
                            to_db.append({
                                "date_atelier": date_iso,
                                "titre": r['Titre'],
                                "lieu_id": map_l_id[lieu_nom],
                                "horaire_id": map_h_id[horaire_lib],
                                "capacite_max": int(r['Capacité']),
                                "est_actif": bool(r['Actif']),
                                "Verrouille": bool(r.get("Verrouillé", False)),
                                "categorie_color": "#3498db"   # bleu par défaut
                            })
                        if to_db:
                            try:
                                supabase.table("ateliers").insert(to_db).execute()
                                st.session_state['at_list_gen'] = []
                                st.success(f"{len(to_db)} ateliers enregistrés avec succès !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur lors de l'enregistrement : {str(e)}")
                        else:
                            st.warning("Aucune ligne valide à enregistrer (lieu ou horaire manquant).")
        
            elif sub == "Répertoire":
                cf1, cf2, cf3 = st.columns(3)
                fs = cf1.date_input("Du", date.today()-timedelta(days=30), format="DD/MM/YYYY", key="rep_d1")
                fe = cf2.date_input("Au", fs+timedelta(days=60), format="DD/MM/YYYY", key="rep_d2")
                ft = cf3.selectbox("Statut Filtre", ["Tous", "Actifs", "Inactifs"])
                
                rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)") \
                      .gte("date_atelier", str(fs)).lte("date_atelier", str(fe)) \
                      .order("date_atelier").execute().data
                
                # Palette de 15 couleurs
                palette_couleurs = {
                    "Rouge": "#e74c3c",
                    "Vert": "#2ecc71",
                    "Bleu": "#3498db",
                    "Jaune": "#f1c40f",
                    "Orange": "#e67e22",
                    "Violet": "#9b59b6",
                    "Rose": "#fd79a8",
                    "Cyan": "#00cec9",
                    "Marron": "#d35400",
                    "Gris": "#95a5a6",
                    "Bleu foncé": "#2c3e50",
                    "Vert foncé": "#27ae60",
                    "Pourpre": "#8e44ad",
                    "Turquoise": "#1abc9c",
                    "Corail": "#ff7675"
                }
                
                for a in rep:
                    if ft == "Actifs" and not a['est_actif']:
                        continue
                    if ft == "Inactifs" and a['est_actif']:
                        continue
                    
                    badge_actif = '<span style="background-color:#2ecc71; color:white; padding:2px 6px; border-radius:12px; font-size:0.75rem; margin-right:8px;">Actif</span>' if a['est_actif'] else '<span style="background-color:#e74c3c; color:white; padding:2px 6px; border-radius:12px; font-size:0.75rem; margin-right:8px;">Inactif</span>'
                    
                    if a.get('categorie_color'):
                        badge_cat = f'<span style="background-color:{a["categorie_color"]}; width:14px; height:14px; display:inline-block; border-radius:50%; margin-right:6px;"></span>'
                    else:
                        badge_cat = '<span style="background-color:#cccccc; width:14px; height:14px; display:inline-block; border-radius:50%; margin-right:6px;" title="Choisir une couleur"></span>'
                    
                    c_lieu = get_color(a['lieux']['nom'])
                    lieu_badge = f'<span class="lieu-badge" style="background-color:{c_lieu};">{a["lieux"]["nom"]}</span>'
                    date_str = format_date_fr_complete(a['date_atelier'])
                    horaire_str = a['horaires']['libelle']
                    titre_str = a['titre']
                    verrou_icon = " 🔒" if is_verrouille(a) else ""
                    
                    ca, cb, cc, cd, ce_couleur, ce_btn, cf_col = st.columns([0.40, 0.08, 0.08, 0.08, 0.12, 0.08, 0.08])
                    ca.markdown(f"{badge_cat}{badge_actif}**{date_str}** | {horaire_str} | {titre_str} | {lieu_badge}{verrou_icon}", unsafe_allow_html=True)
                    
                    # Activer/Désactiver
                    btn_l = "🔴 Désactiver" if a['est_actif'] else "🟢 Activer"
                    if cb.button(btn_l, key=f"at_stat_{a['id']}"):
                        supabase.table("ateliers").update({"est_actif": not a['est_actif']}).eq("id", a['id']).execute()
                        st.rerun()
                    
                    # Verrouiller/Déverrouiller
                    btn_v = "🔓 Déverrouiller" if is_verrouille(a) else "🔒 Verrouiller"
                    if cc.button(btn_v, key=f"at_verr_{a['id']}"):
                        nouvel_etat = not is_verrouille(a)
                        supabase.table("ateliers").update({"Verrouille": bool(nouvel_etat)}).eq("id", a['id']).execute()
                        enregistrer_log("Admin", "Verrouillage atelier", f"Atelier '{a['titre']}' du {a['date_atelier']} {'verrouillé' if nouvel_etat else 'déverrouillé'}")
                        st.rerun()
                    
                    # Modifier
                    if cd.button("✏️", key=f"at_edit_{a['id']}"):
                        edit_atelier_dialog(a['id'], a['titre'], a['lieu_id'], a['horaire_id'], a['capacite_max'], l_raw, h_raw, map_l_id, map_h_id)
                    
                    # Sélecteur de couleur (palette)
                    couleur_actuelle = a.get('categorie_color', '#3498db')
                    # Trouver le nom de la couleur actuelle dans la palette
                    nom_actuel = "Bleu"
                    for nom, code in palette_couleurs.items():
                        if code == couleur_actuelle:
                            nom_actuel = nom
                            break
                    selected_color_name = ce_couleur.selectbox("Couleur", options=list(palette_couleurs.keys()), index=list(palette_couleurs.keys()).index(nom_actuel), key=f"pal_{a['id']}", label_visibility="collapsed")
                    if ce_btn.button("💾", key=f"savecol_{a['id']}"):
                        nouvelle_couleur = palette_couleurs[selected_color_name]
                        supabase.table("ateliers").update({"categorie_color": nouvelle_couleur}).eq("id", a['id']).execute()
                        st.cache_data.clear()
                        st.rerun()
                    
                    # Supprimer
                    if cf_col.button("🗑️", key=f"at_del_{a['id']}"):
                        cnt = supabase.table("inscriptions").select("id", count="exact").eq("atelier_id", a['id']).execute().count
                        delete_atelier_dialog(a['id'], a['titre'], (cnt if cnt else 0) > 0, current_code)
        
            elif sub == "Actions groupées":
                with st.form("bulk_form"):
                    c1, c2 = st.columns(2)
                    bs = c1.date_input("Début", format="DD/MM/YYYY", key="blk_d1")
                    be = c2.date_input("Fin", format="DD/MM/YYYY", key="blk_d2")
                    action = st.radio("Action :", ["Activer", "Désactiver"], horizontal=True)
                    if st.form_submit_button("🚀 Appliquer"):
                        supabase.table("ateliers").update({"est_actif": (action=="Activer")}).gte("date_atelier", str(bs)).lte("date_atelier", str(be)).execute()
                        st.rerun()

        with t2: # SUIVI AM (Admin)
            choix_adm = st.multiselect("Filtrer par AM (Admin) :", liste_adh, key="adm_filter_am")
            ids_adm = [dict_adh[n] for n in choix_adm] if choix_adm else list(dict_adh.values())
            data_adm = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids_adm).eq("ateliers.est_actif", True).execute()

            data_adm_triee = trier_par_nom_puis_date(data_adm.data) if data_adm.data else []

            if data_adm.data:
                df_adm = pd.DataFrame([{
                    "AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}",
                    "Date": i['ateliers']['date_atelier'],
                    "Atelier": i['ateliers']['titre'],
                    "Lieu": i['ateliers']['lieux']['nom'],
                    "Horaire": i['ateliers']['horaires']['libelle'],
                    "Enfants": i['nb_enfants']
                } for i in data_adm_triee])
            else:
                df_adm = pd.DataFrame(columns=["AM", "Date", "Atelier", "Lieu", "Horaire", "Enfants"])

            c_e3, c_e4 = st.columns(2)
            c_e3.download_button("📥 Excel (Admin)", data=export_to_excel(df_adm), file_name="admin_suivi_am.xlsx")
            c_e4.download_button("📥 PDF (Admin)", data=export_suivi_am_pdf("Suivi AM (Administration)", data_adm_triee), file_name="admin_suivi_am.pdf")

            if data_adm.data:
                curr = ""
                for i in data_adm_triee:
                    nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    if nom != curr:
                        st.markdown(f'<div style="color:#1b5e20; border-bottom:2px solid #1b5e20; padding-top:15px; margin-bottom:8px; font-weight:bold; font-size:1.2rem;">{nom}</div>', unsafe_allow_html=True)
                        curr = nom
                    at = i['ateliers']
                    c_l = get_color(at['lieux']['nom'])
                    badge_cat = badge_categorie(at)
                    st.markdown(f"{badge_cat}{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> <span class='horaire-text'>({at['horaires']['libelle']})</span> **({i['nb_enfants']} enf.)**", unsafe_allow_html=True)
            else:
                st.info("Aucune inscription trouvée pour les AM sélectionnées.")

    with t3: # PLANNING ATELIERS (Admin)
        st.subheader("📅 Planning des Ateliers")
        
        # Filtre statut
        filtre_statut = st.radio("Filtrer par statut :", ["Tous", "Actifs", "Inactifs"], horizontal=True, key="admin_plan_filtre")
        
        c1_adm, c2_adm = st.columns(2)
        d_s_a = c1_adm.date_input("Du", date.today(), key="adm_plan_d1", format="DD/MM/YYYY")
        d_e_a = c2_adm.date_input("Au", d_s_a + timedelta(days=30), key="adm_plan_d2", format="DD/MM/YYYY")
        
        # Construction de la requête en fonction du filtre
        query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(d_s_a)).lte("date_atelier", str(d_e_a))
        if filtre_statut == "Actifs":
            query = query.eq("est_actif", True)
        elif filtre_statut == "Inactifs":
            query = query.eq("est_actif", False)
        ats_adm = query.order("date_atelier").execute()
    
        # Optimisation : chargement groupé des inscriptions
        cache_ins_adm = {}
        adm_ins_list = []
        if ats_adm.data:
            at_ids_adm = [a['id'] for a in ats_adm.data]
            all_ins_adm = supabase.table("inscriptions").select("*, adherents(nom, prenom)").in_("atelier_id", at_ids_adm).execute()
            for ins in all_ins_adm.data:
                cache_ins_adm.setdefault(ins['atelier_id'], []).append(ins)
            for a in ats_adm.data:
                for p in cache_ins_adm.get(a['id'], []):
                    adm_ins_list.append({
                        "Date": a['date_atelier'],
                        "Atelier": a['titre'],
                        "Lieu": a['lieux']['nom'],
                        "AM": f"{p['adherents']['prenom']} {p['adherents']['nom']}",
                        "Enfants": p['nb_enfants']
                    })
    
        # Exports
        df_adm_at = pd.DataFrame(adm_ins_list) if adm_ins_list else pd.DataFrame(columns=["Date", "Atelier", "Lieu", "AM", "Enfants"])
        cea1, cea2 = st.columns(2)
        cea1.download_button("📥 Excel Planning (Admin)", data=export_to_excel(df_adm_at), file_name="admin_planning_ateliers.xlsx", key="adm_exp_xl")
        cea2.download_button("📥 PDF Planning (Admin)", data=export_planning_ateliers_pdf(
            "Planning des Ateliers (Administration)", ats_adm.data if ats_adm.data else [], lambda aid: cache_ins_adm.get(aid, [])
        ), file_name="admin_planning_ateliers.pdf", key="adm_exp_pdf")
    
        # Affichage des ateliers
        if ats_adm.data:
            for index, a in enumerate(ats_adm.data):
                c_l = get_color(a['lieux']['nom'])
                ins_at = cache_ins_adm.get(a['id'], [])
                t_ad, t_en = len(ins_at), sum(p['nb_enfants'] for p in ins_at)
                restantes = a['capacite_max'] - (t_ad + t_en)
                cl_c = "alerte-complet" if restantes <= 0 else ""
                verrou_icon = " 🔒" if is_verrouille(a) else ""
                at_info_log = f"{a['date_atelier']} | {a['horaires']['libelle']} | {a['lieux']['nom']}"
                badge_cat = badge_categorie(a)
    
                # Ligne d'en-tête avec retour à la ligne automatique
                st.markdown(
                    f"""
                    <div style="white-space: normal; word-wrap: break-word; margin-bottom: 5px;">
                        {badge_cat}<strong>{format_date_fr_complete(a['date_atelier'])}</strong> | {a['titre']} | 
                        <span class='lieu-badge' style='background-color:{c_l};'>{a['lieux']['nom']}</span> | 
                        <span class='horaire-text'>{a['horaires']['libelle']}</span>{verrou_icon}
                        <span class='compteur-badge'>👤 {t_ad} AM</span>
                        <span class='compteur-badge'>👶 {t_en} enf.</span>
                        <span class='compteur-badge {cl_c}'>🏁 {restantes} pl.</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    
                # Affichage des inscrits avec modification possible
                if ins_at:
                    ins_s = sorted(ins_at, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                    for p in ins_s:
                        n_f = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                        cp1, cp2, cp3, cp4 = st.columns([0.45, 0.2, 0.2, 0.15])
                        cp1.write(f"• {n_f}")
                        new_nb = cp2.number_input("Enf.", 1, 10, int(p['nb_enfants']), key=f"adm_nb_{p['id']}", label_visibility="collapsed")
                        if cp3.button("✏️ Modifier", key=f"adm_mod_{p['id']}"):
                            supabase.table("inscriptions").update({"nb_enfants": new_nb}).eq("id", p['id']).execute()
                            enregistrer_log("Admin", "Modification (admin)", f"{n_f} → {new_nb} enfants - {at_info_log}")
                            st.rerun()
                        if cp4.button("🗑️", key=f"adm_del_plan_{p['id']}"):
                            confirm_unsubscribe_dialog(p['id'], n_f, at_info_log, "Admin")
    
                # Expander pour ajouter une inscription
                with st.expander(f"➕ Inscrire une AM à cet atelier", expanded=False):
                    ca1, ca2, ca3 = st.columns([2, 1, 1])
                    qui_adm = ca1.selectbox("AM à inscrire", ["Choisir..."] + liste_adh, key=f"adm_qui_{a['id']}")
                    nb_adm = ca2.number_input("Enfants", 1, 10, 1, key=f"adm_enf_{a['id']}")
                    if ca3.button("✅ Inscrire", key=f"adm_ins_{a['id']}", type="primary"):
                        if qui_adm != "Choisir...":
                            id_adh = dict_adh[qui_adm]
                            existing = next((ins for ins in ins_at if ins['adherent_id'] == id_adh), None)
                            if existing:
                                if restantes - (nb_adm - existing['nb_enfants']) < 0:
                                    st.error("Manque de places")
                                else:
                                    supabase.table("inscriptions").update({"nb_enfants": nb_adm}).eq("id", existing['id']).execute()
                                    enregistrer_log("Admin", "Modification (admin)", f"{qui_adm} → {nb_adm} enfants - {at_info_log}")
                                    st.rerun()
                            else:
                                if restantes - (1 + nb_adm) < 0:
                                    st.error("Manque de places")
                                else:
                                    supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": a['id'], "nb_enfants": nb_adm}).execute()
                                    enregistrer_log("Admin", "Inscription (admin)", f"{qui_adm} inscrite (+{nb_adm} enf.) - {at_info_log}")
                                    st.rerun()
    
                if index < len(ats_adm.data) - 1:
                    st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)
        else:
            st.info("Aucun atelier trouvé sur cette période.")

        with t4: # STATS
            st.subheader("📈 Statistiques de participation")
            cs1, cs2 = st.columns(2)
            ds_stat = cs1.date_input("Date début", date.today().replace(day=1), key="stat_d1", format="DD/MM/YYYY")
            de_stat = cs2.date_input("Date fin", date.today(), key="stat_d2", format="DD/MM/YYYY")
            ins_stat = supabase.table("inscriptions").select("*, adherents(nom, prenom), ateliers(date_atelier)").gte("ateliers.date_atelier", str(ds_stat)).lte("ateliers.date_atelier", str(de_stat)).execute()
            ats_count = supabase.table("ateliers").select("id", count="exact").gte("date_atelier", str(ds_stat)).lte("date_atelier", str(de_stat)).execute()
            
            ateliers_periode = supabase.table("ateliers").select("date_atelier, titre, lieux(nom), horaires(libelle)").gte("date_atelier", str(ds_stat)).lte("date_atelier", str(de_stat)).order("date_atelier").execute()
            
            if ins_stat.data:
                stats_list = []
                for am_nom in liste_adh:
                    am_id = dict_adh[am_nom]
                    count = sum(1 for x in ins_stat.data if x['adherent_id'] == am_id)
                    stats_list.append({"Assistante Maternelle": am_nom, "Nombre d'ateliers": count})
                df_stats = pd.DataFrame(stats_list)
                df_stats = df_stats[df_stats["Nombre d'ateliers"] > 0]
                df_stats = df_stats.sort_values(["Nombre d'ateliers", "Assistante Maternelle"], ascending=[False, True])
                
                # --- Affichage avec st.dataframe (CSS pour centrage) ---
                st.dataframe(
                    df_stats,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Assistante Maternelle": st.column_config.TextColumn("Assistante Maternelle"),
                        "Nombre d'ateliers": st.column_config.NumberColumn("Nombre d'ateliers", format="%d")
                    }
                )
                
                total_inscr = df_stats["Nombre d'ateliers"].sum()
                nb_at_proposes = ats_count.count if ats_count.count else 0
                st.markdown(f"**Total des inscriptions sur la période :** {total_inscr}")
                st.markdown(f"**Nombre d'ateliers proposés sur la période :** {nb_at_proposes}")
                
                if ateliers_periode.data:
                    st.markdown("**Ateliers proposés :**")
                    for at in ateliers_periode.data:
                        date_fr = format_date_fr_simple(at['date_atelier'])
                        lieu_nom = at['lieux']['nom']
                        horaire_lib = at['horaires']['libelle']
                        st.write(f"- {date_fr} : **{at['titre']}** ({lieu_nom} - {horaire_lib})")
                else:
                    st.info("Aucun atelier proposé sur cette période.")
                
                # --- Export Excel ---
                output_excel = io.BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    workbook = writer.book
                    worksheet = workbook.add_worksheet('Statistiques')
                    title_format = workbook.add_format({'bold': True, 'font_size': 12})
                    worksheet.write(0, 0, f"Période : du {ds_stat.strftime('%d/%m/%Y')} au {de_stat.strftime('%d/%m/%Y')}", title_format)
                    df_stats.to_excel(writer, sheet_name='Statistiques', startrow=2, index=False)
                excel_data = output_excel.getvalue()
                
                ce_s1, ce_s2 = st.columns(2)
                ce_s1.download_button("📥 Excel Statistiques", data=excel_data, file_name=f"stats_am_{ds_stat}_{de_stat}.xlsx")
                
                # --- Export PDF ---
                pdf_stat_lines = []
                pdf_stat_lines.append(f"Période : du {ds_stat.strftime('%d/%m/%Y')} au {de_stat.strftime('%d/%m/%Y')}")
                pdf_stat_lines.append("")
                for _, r in df_stats.iterrows():
                    pdf_stat_lines.append(f"{r['Assistante Maternelle']} : {r['Nombre d\'ateliers']} atelier(s)")
                pdf_stat_lines.append("")
                pdf_stat_lines.append(f"Total inscriptions sur la période : {total_inscr}")
                pdf_stat_lines.append(f"Ateliers proposés sur la période : {nb_at_proposes}")
                pdf_stat_lines.append("")
                pdf_stat_lines.append("Liste des ateliers proposés :")
                for at in ateliers_periode.data:
                    date_fr = format_date_fr_simple(at['date_atelier'])
                    lieu_nom = at['lieux']['nom']
                    horaire_lib = at['horaires']['libelle']
                    pdf_stat_lines.append(f"- {date_fr} : {at['titre']} ({lieu_nom} - {horaire_lib})")
                
                ce_s2.download_button("📥 PDF Statistiques", data=export_to_pdf("Statistiques de participation AM", pdf_stat_lines), file_name=f"stats_am_{ds_stat}_{de_stat}.pdf")
            else:
                st.info("Aucune donnée pour cette période.")
                if ateliers_periode.data:
                    st.markdown("**Ateliers proposés sur la période :**")
                    for at in ateliers_periode.data:
                        date_fr = format_date_fr_simple(at['date_atelier'])
                        lieu_nom = at['lieux']['nom']
                        horaire_lib = at['horaires']['libelle']
                        st.write(f"- {date_fr} : **{at['titre']}** ({lieu_nom} - {horaire_lib})")
                        
        with t5: # 👥 LISTE AM
            with st.form("add_am"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nom").upper().strip()
                pre = " ".join([w.capitalize() for w in c2.text_input("Prénom").split()]).strip()
                if st.form_submit_button("➕ Ajouter"):
                    if nom and pre:
                        supabase.table("adherents").insert({"nom": nom, "prenom": pre, "est_actif": True}).execute()
                        load_adherents.clear()
                        st.rerun()
            for u in res_adh.data:
                c1, c_edit, c_del = st.columns([0.7, 0.15, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c_edit.button("✏️ Modifier", key=f"am_edit_{u['id']}"): edit_am_dialog(u['id'], u['nom'], u['prenom'])
                if c_del.button("🗑️", key=f"am_del_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t6: # 📍 LIEUX / HORAIRES
            cl1, cl2 = st.columns(2)
            l_raw_t6 = load_lieux()
            h_raw_t6 = load_horaires()
            with cl1:
                st.subheader("Lieux")
                for l in l_raw_t6:
                    ca, cb = st.columns([0.8, 0.2]); ca.markdown(f"<span class='lieu-badge' style='background-color:{get_color(l['nom'])}'>{l['nom']} (Cap: {l['capacite_accueil']})</span>", unsafe_allow_html=True)
                    if cb.button("🗑️", key=f"lx_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("add_lx"):
                    nl, cp = st.text_input("Nouveau Lieu"), st.number_input("Capacité", 1, 50, 10)
                    if st.form_submit_button("Ajouter"): supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp, "est_actif": True}).execute(); load_lieux.clear(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw_t6:
                    cc, cd = st.columns([0.8, 0.2]); cc.write(f"• {h['libelle']}")
                    if cd.button("🗑️", key=f"hx_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("add_hx"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter"): supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); load_horaires.clear(); st.rerun()

        with t7: # ⚙️ SÉCURITÉ
            with st.form("sec_form"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code or o == "0000":
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        get_secret_code.clear()
                        st.rerun()
                    else: st.error("Ancien code incorrect")
            if st.button("🚪 Déconnexion Super Admin"): st.session_state['super_access'] = False; st.rerun()

        with t8: # 📜 JOURNAL DES ACTIONS
            st.subheader("📜 Journal des manipulations")
            cj1, cj2 = st.columns(2)
            dj_s = cj1.date_input("Depuis le", date.today() - timedelta(days=7), format="DD/MM/YYYY", key="log_d1")
            dj_e = cj2.date_input("Jusqu'au", date.today(), format="DD/MM/YYYY", key="log_d2")

            start_date = dj_s.strftime("%Y-%m-%d") + "T00:00:00"
            end_date = dj_e.strftime("%Y-%m-%d") + "T23:59:59"

            try:
                res_logs = supabase.table("logs").select("*").gte("created_at", start_date).lte("created_at", end_date).order("created_at", desc=True).execute()
                if res_logs.data:
                    logs_df = pd.DataFrame(res_logs.data)
                    # Correction fuseau horaire : UTC → Europe/Paris (+1h hiver / +2h été)
                    logs_df['created_at'] = pd.to_datetime(logs_df['created_at'], utc=True).dt.tz_convert("Europe/Paris").dt.strftime('%d/%m/%Y %H:%M')
                    st.dataframe(
                        logs_df[['created_at', 'utilisateur', 'action', 'details']],
                        column_config={
                            "created_at": "Date & Heure",
                            "utilisateur": "Auteur",
                            "action": "Action",
                            "details": "Détails"
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Aucune action enregistrée pour cette période.")
            except Exception as e:
                st.error(f"Erreur lors du chargement du journal : {e}")

    else:
        st.info("Saisissez le code secret pour accéder aux fonctions d'administration.")
