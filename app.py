import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from supabase import create_client, Client
import hashlib
import io
import re
import urllib.parse
import html as html_lib
import base64
from fpdf import FPDF
import xlsxwriter
import calendar

def ajouter_mois(d, mois):
    """Ajoute un nombre de mois (entier) à une date, en gérant les fins de mois
    (ex: 31 janvier + 1 mois -> 28 ou 29 février selon l'année)."""
    mois_total = d.month - 1 + mois
    annee = d.year + mois_total // 12
    mois_resultat = mois_total % 12 + 1
    dernier_jour = calendar.monthrange(annee, mois_resultat)[1]
    jour = min(d.day, dernier_jour)
    return date(annee, mois_resultat, jour)

def periode_defaut_suivi_inscriptions(d=None):
    """Période par défaut de l'écran Suivi Inscription, calculée à partir de la date du jour :
    - Entre le 1er août et le 20 décembre (année en cours) -> période du 25 août au 25 décembre (année en cours)
    - Entre le 21 décembre (année en cours) et le 30 avril (année suivante) -> période du 1er janvier au 31 juillet (année suivante)
    - Entre le 1er janvier et le 31 juillet (année en cours, hors cas ci-dessus) -> période du 1er janvier au 31 juillet
      de l'année en cours (on est déjà dans cette période)."""
    if d is None:
        d = date.today()
    if date(d.year, 8, 1) <= d <= date(d.year, 12, 20):
        return date(d.year, 8, 25), date(d.year, 12, 25)
    elif d.month == 12 and d.day >= 21:
        return date(d.year + 1, 1, 1), date(d.year + 1, 7, 31)
    else:
        return date(d.year, 1, 1), date(d.year, 7, 31)

def fin_defaut_places_restantes(d=None):
    """Date de fin par défaut de l'écran Places restantes : le 31 juillet suivant la date du jour
    (année en cours si le 31 juillet n'est pas encore passé, sinon année suivante).
    Ex : le 30/09/2026 -> 31/07/2027 ; le 01/01/2027 -> 31/07/2027."""
    if d is None:
        d = date.today()
    juillet_annee_courante = date(d.year, 7, 31)
    if d <= juillet_annee_courante:
        return juillet_annee_courante
    return date(d.year + 1, 7, 31)

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
                    <p><span style="font-size: 2.8rem; font-weight: bold; color: #e65100;">Résa RPE</span></p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        code = st.text_input("Code d'accès", type="password", key="gate_code")
        if st.button("Valider", type="primary"):
            if code == "RPECSP":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Code incorrect. Accès refusé.")
        st.stop()
       
check_access()

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
    .btn-agenda { display:inline-flex; align-items:center; gap:0.55rem; padding:0.4rem 1.1rem 0.4rem 0.4rem; margin-left:8px;
        border-radius:999px; border:none; background-color:#fbe3d3; color:#b15a24;
        font-size:0.85rem; font-weight:700; text-decoration:none; vertical-align:middle;
        transition:filter .15s, transform .15s; }
    .btn-agenda:hover { filter:brightness(0.97); transform:translateY(-1px); color:#b15a24; }
    .btn-agenda-icon { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px;
        border-radius:8px; background-color:#ffffff; box-shadow:0 1px 3px rgba(43,38,33,0.14);
        font-size:0.9rem; line-height:1; }
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

def enfants_requis(at):
    """Retourne True si le nombre d'enfants doit être demandé pour cet atelier (comportement par défaut).
    Si la colonne n'existe pas encore ou est vide, on considère que c'est requis (rétrocompatibilité)."""
    val = at.get("nb_enfants_requis", True)
    return True if val is None else bool(val)

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


# --- BOUTON "AJOUTER À MON AGENDA" (lien Google Agenda pré-rempli, sans API) ---
PREFIXE_AGENDA = "RPE"

_HORAIRE_RE = re.compile(
    r'^\s*(\d{1,2})\s*[hH:]\s*(\d{1,2})?\s*-\s*(\d{1,2})\s*[hH:]\s*(\d{1,2})?\s*$'
)

def _parse_horaire(horaire_str):
    """Parse un horaire tolérant : '9h-11h', '9h30-11h45', '9:30 - 11:00', '9H30 - 11H'...
    Retourne (h_debut, min_debut, h_fin, min_fin) ou None si non reconnu."""
    if not horaire_str:
        return None
    m = _HORAIRE_RE.match(str(horaire_str).strip())
    if not m:
        return None
    try:
        h1 = int(m.group(1)); mi1 = int(m.group(2)) if m.group(2) else 0
        h2 = int(m.group(3)); mi2 = int(m.group(4)) if m.group(4) else 0
        if not (0 <= h1 <= 23 and 0 <= mi1 <= 59 and 0 <= h2 <= 23 and 0 <= mi2 <= 59):
            return None
        return h1, mi1, h2, mi2
    except (ValueError, TypeError):
        return None

def lien_google_agenda(date_atelier, horaire, titre=None, lieu=None, prefixe=PREFIXE_AGENDA):
    """Construit une URL Google Agenda pré-remplie (action=TEMPLATE), sans passer par l'API Google.
    Réutilisable sur n'importe quel écran affichant un atelier (date, horaire, titre, lieu)."""
    titre_clean = str(titre).strip() if titre else ""
    text = f"{prefixe} - {titre_clean}" if titre_clean else prefixe

    lieu_clean = str(lieu).strip() if lieu else ""
    details_parts = []
    if titre_clean:
        details_parts.append(f"Atelier : {titre_clean}")
    if lieu_clean:
        details_parts.append(f"Lieu : {lieu_clean}")
    details = "\n".join(details_parts)

    try:
        if isinstance(date_atelier, str):
            d = datetime.strptime(date_atelier, "%Y-%m-%d").date()
        elif isinstance(date_atelier, datetime):
            d = date_atelier.date()
        elif isinstance(date_atelier, date):
            d = date_atelier
        else:
            d = None
    except (ValueError, TypeError):
        d = None
    if d is None:
        d = date.today()

    parsed = _parse_horaire(horaire)
    if parsed:
        h1, mi1, h2, mi2 = parsed
        debut = datetime(d.year, d.month, d.day, h1, mi1)
        fin = datetime(d.year, d.month, d.day, h2, mi2)
        if fin <= debut:
            fin = debut + timedelta(hours=1)
        dates_value = f"{debut.strftime('%Y%m%dT%H%M%S')}/{fin.strftime('%Y%m%dT%H%M%S')}"
    else:
        # Horaire non reconnu -> événement journée entière plutôt que planter
        lendemain = d + timedelta(days=1)
        dates_value = f"{d.strftime('%Y%m%d')}/{lendemain.strftime('%Y%m%d')}"

    params = {
        "action": "TEMPLATE", "text": text, "dates": dates_value,
        "details": details, "location": lieu_clean, "ctz": "Europe/Paris",
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"

def bouton_agenda_html(date_atelier, horaire, titre=None, lieu=None):
    """Génère le HTML du bouton "Google Agenda" (pilule pastel pêche), prêt à insérer
    dans un st.markdown(..., unsafe_allow_html=True)."""
    url_safe = html_lib.escape(lien_google_agenda(date_atelier, horaire, titre, lieu), quote=True)
    return f'<a href="{url_safe}" target="_blank" rel="noopener noreferrer" class="btn-agenda"><span class="btn-agenda-icon">📅</span>Google Agenda</a>'


# --- BOUTON "AJOUTER À L'AGENDA IPHONE" (fichier .ics, sans API) ---
def _ics_escape(text):
    """Échappe une chaîne pour l'insertion dans un champ .ics (RFC 5545) :
    antislash, virgule, point-virgule et retours à la ligne."""
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\n", "\\n")
    return text

def evenement_ics(date_atelier, horaire, titre=None, lieu=None, prefixe=PREFIXE_AGENDA):
    """Construit le contenu d'un fichier .ics (iCalendar) pour l'atelier, compatible
    Agenda iPhone/iOS (et Apple Calendar, Outlook). Réutilise le même parsing
    d'horaire tolérant que lien_google_agenda() : mêmes règles (fin <= début -> +1h,
    horaire non reconnu -> événement journée entière)."""
    titre_clean = str(titre).strip() if titre else ""
    text = f"{prefixe} - {titre_clean}" if titre_clean else prefixe

    lieu_clean = str(lieu).strip() if lieu else ""
    details_parts = []
    if titre_clean:
        details_parts.append(f"Atelier : {titre_clean}")
    if lieu_clean:
        details_parts.append(f"Lieu : {lieu_clean}")
    details = "\n".join(details_parts)

    try:
        if isinstance(date_atelier, str):
            d = datetime.strptime(date_atelier, "%Y-%m-%d").date()
        elif isinstance(date_atelier, datetime):
            d = date_atelier.date()
        elif isinstance(date_atelier, date):
            d = date_atelier
        else:
            d = None
    except (ValueError, TypeError):
        d = None
    if d is None:
        d = date.today()

    tz_paris = ZoneInfo("Europe/Paris")
    parsed = _parse_horaire(horaire)
    if parsed:
        h1, mi1, h2, mi2 = parsed
        debut_local = datetime(d.year, d.month, d.day, h1, mi1, tzinfo=tz_paris)
        fin_local = datetime(d.year, d.month, d.day, h2, mi2, tzinfo=tz_paris)
        if fin_local <= debut_local:
            fin_local = debut_local + timedelta(hours=1)
        debut_utc = debut_local.astimezone(ZoneInfo("UTC"))
        fin_utc = fin_local.astimezone(ZoneInfo("UTC"))
        dtstart_line = f"DTSTART:{debut_utc.strftime('%Y%m%dT%H%M%SZ')}"
        dtend_line = f"DTEND:{fin_utc.strftime('%Y%m%dT%H%M%SZ')}"
    else:
        # Horaire non reconnu -> événement journée entière plutôt que planter
        lendemain = d + timedelta(days=1)
        dtstart_line = f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}"
        dtend_line = f"DTEND;VALUE=DATE:{lendemain.strftime('%Y%m%d')}"

    dtstamp = datetime.now(ZoneInfo("UTC")).strftime('%Y%m%dT%H%M%SZ')
    uid_source = f"{d.isoformat()}-{horaire}-{titre_clean}-{lieu_clean}"
    uid = f"{hashlib.md5(uid_source.encode()).hexdigest()}@resa-rpe"

    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Resa RPE//Ajout Agenda//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        dtstart_line,
        dtend_line,
        f"SUMMARY:{_ics_escape(text)}",
    ]
    if details:
        lignes.append(f"DESCRIPTION:{_ics_escape(details)}")
    if lieu_clean:
        lignes.append(f"LOCATION:{_ics_escape(lieu_clean)}")
    lignes += ["END:VEVENT", "END:VCALENDAR"]

    return "\r\n".join(lignes)

def bouton_agenda_iphone_html(date_atelier, horaire, titre=None, lieu=None):
    """Génère le HTML du bouton "iPhone / Autre agenda" (fichier .ics encodé en
    data URI), prêt à insérer dans un st.markdown(..., unsafe_allow_html=True).
    Même classe CSS .btn-agenda que le bouton Google Agenda -> forme pilule identique.
    Compatible iPhone/iOS (appli Agenda), Apple Calendar (Mac) et Outlook."""
    ics_content = evenement_ics(date_atelier, horaire, titre, lieu)
    b64 = base64.b64encode(ics_content.encode("utf-8")).decode("ascii")
    href = f"data:text/calendar;charset=utf-8;base64,{b64}"
    return f'<a href="{href}" download="atelier_rpe.ics" class="btn-agenda"><span class="btn-agenda-icon">📱</span>iPhone / Autre agenda</a>'



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
        suffixe_enf_pdf = f"  |  {nb_enf} enfant(s)" if enfants_requis(at) else ""

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
        detail = f"     {titre_at}  |  {lieu}  |  {horaire}{suffixe_enf_pdf}"
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
        requiert_enfants_pdf = enfants_requis(a)

        # En-tête atelier (fond bleu-gris)
        pdf.set_fill_color(224, 235, 245)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 11)
        entete = f"  {date_fr} | {titre_at} | {lieu}{verrou}"
        pdf.cell(0, 8, entete.encode('latin-1', 'replace').decode('latin-1'), ln=True, fill=True)

        pdf.set_font("Arial", size=10)
        segment_enf_pdf = f"  |  Enfants : {t_en}" if requiert_enfants_pdf else ""
        sous = f"     Horaire : {horaire}  |  AM : {t_ad}{segment_enf_pdf}  |  Places restantes : {restantes}"
        pdf.cell(0, 6, sous.encode('latin-1', 'replace').decode('latin-1'), ln=True)

        # Inscrits triés alphabétiquement
        ins_tries = sorted(ins_at, key=lambda x: (x['adherents']['nom'].upper(), x['adherents']['prenom'].upper()))
        for p in ins_tries:
            nom_p = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
            suffixe_p_pdf = f"  ({p['nb_enfants']} enfant(s))" if requiert_enfants_pdf else ""
            ligne = f"       • {nom_p}{suffixe_p_pdf}"
            pdf.cell(0, 6, ligne.encode('latin-1', 'replace').decode('latin-1'), ln=True)

        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1')

def export_suivi_inscription_excel(rows, lieux_cols, totaux_par_lieu, total_general):
    """Export Excel du Suivi Inscription : une ligne par AM, une colonne par lieu (nombre + dates),
    avec mise en couleur et tailles de police différentes pour la lisibilité."""
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = workbook.add_worksheet("Suivi Inscription")

    fmt_header = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1B5E20', 'align': 'center', 'valign': 'vcenter', 'font_size': 11, 'border': 1})
    fmt_header_total = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#4C8C52', 'align': 'center', 'valign': 'vcenter', 'font_size': 11, 'border': 1})
    fmt_am = workbook.add_format({'bold': True, 'font_size': 11, 'border': 1, 'valign': 'vcenter'})
    fmt_am_alt = workbook.add_format({'bold': True, 'font_size': 11, 'border': 1, 'valign': 'vcenter', 'bg_color': '#FAF9F4'})
    fmt_cell = workbook.add_format({'border': 1, 'valign': 'top', 'align': 'center', 'text_wrap': True, 'font_size': 10})
    fmt_cell_alt = workbook.add_format({'border': 1, 'valign': 'top', 'align': 'center', 'text_wrap': True, 'font_size': 10, 'bg_color': '#FAF9F4'})
    fmt_cell_zero = workbook.add_format({'border': 1, 'valign': 'top', 'align': 'center', 'font_size': 10, 'font_color': '#AAAAAA'})
    fmt_cell_zero_alt = workbook.add_format({'border': 1, 'valign': 'top', 'align': 'center', 'font_size': 10, 'font_color': '#AAAAAA', 'bg_color': '#FAF9F4'})
    fmt_total_cell = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EEF2EA', 'font_color': '#1B5E20', 'align': 'center', 'valign': 'vcenter', 'font_size': 12})
    fmt_total_row = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EEF2EA', 'font_color': '#1B5E20', 'font_size': 11, 'align': 'center'})
    fmt_total_row_nom = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EEF2EA', 'font_color': '#1B5E20', 'font_size': 11})

    ws.write(0, 0, "Assistante Maternelle", fmt_header)
    for j, lieu in enumerate(lieux_cols, start=1):
        ws.write(0, j, lieu, fmt_header)
    ws.write(0, len(lieux_cols) + 1, "Total", fmt_header_total)

    ws.set_column(0, 0, 26)
    if lieux_cols:
        ws.set_column(1, len(lieux_cols), 22)
    ws.set_column(len(lieux_cols) + 1, len(lieux_cols) + 1, 10)

    row_idx = 1
    for i, r in enumerate(rows):
        alt = (i % 2 == 1)
        ws.write(row_idx, 0, f"{r['nom']} {r['prenom']}", fmt_am_alt if alt else fmt_am)
        for j, lieu in enumerate(lieux_cols, start=1):
            c = r['cells'].get(lieu, {"count": 0, "dates": []})
            if c['count'] > 0:
                texte = f"{c['count']}\n" + ", ".join(c['dates'])
                ws.write(row_idx, j, texte, fmt_cell_alt if alt else fmt_cell)
            else:
                ws.write(row_idx, j, 0, fmt_cell_zero_alt if alt else fmt_cell_zero)
        ws.write(row_idx, len(lieux_cols) + 1, r['total'], fmt_total_cell)
        row_idx += 1

    ws.write(row_idx, 0, "Total", fmt_total_row_nom)
    for j, lieu in enumerate(lieux_cols, start=1):
        ws.write(row_idx, j, totaux_par_lieu.get(lieu, 0), fmt_total_row)
    ws.write(row_idx, len(lieux_cols) + 1, total_general, fmt_total_row)

    workbook.close()
    return output.getvalue()

def export_suivi_inscription_pdf(title, rows, lieux_cols, totaux_par_lieu, total_general, periode_txt):
    """Export PDF du Suivi Inscription en paysage : une ligne par AM, une colonne par lieu
    (nombre d'inscriptions en gros/vert, dates en petit/gris), avec ligne et colonne Total."""
    pdf = FPDF(orientation='L')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, periode_txt.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    largeur_page = pdf.w - 2 * pdf.l_margin
    largeur_nom = 48
    largeur_total = 20
    nb_lieux = max(len(lieux_cols), 1)
    largeur_lieu = (largeur_page - largeur_nom - largeur_total) / nb_lieux
    row_h = 6
    header_h = 9

    def draw_header():
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(27, 94, 32)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(largeur_nom, header_h, "Assistante Maternelle".encode('latin-1', 'replace').decode('latin-1'), border=1, fill=True)
        for lieu in lieux_cols:
            pdf.cell(largeur_lieu, header_h, lieu.encode('latin-1', 'replace').decode('latin-1')[:22], border=1, fill=True, align='C')
        pdf.set_fill_color(76, 140, 82)
        pdf.cell(largeur_total, header_h, "Total", border=1, fill=True, align='C', ln=True)
        pdf.set_text_color(0, 0, 0)

    draw_header()

    if not rows:
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 10, "Aucune inscription trouvee sur cette periode.", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    for i, r in enumerate(rows):
        if pdf.get_y() + row_h * 2 > pdf.h - pdf.b_margin:
            pdf.add_page()
            draw_header()
        fill_row = (i % 2 == 1)
        if fill_row:
            pdf.set_fill_color(250, 249, 244)
        else:
            pdf.set_fill_color(255, 255, 255)

        y_start = pdf.get_y()
        x_start = pdf.get_x()

        pdf.set_font("Arial", 'B', 9)
        pdf.cell(largeur_nom, row_h * 2, f"{r['nom']} {r['prenom']}".encode('latin-1', 'replace').decode('latin-1'), border=1, fill=True)

        x = x_start + largeur_nom
        for lieu in lieux_cols:
            c = r['cells'].get(lieu, {"count": 0, "dates": []})
            pdf.set_xy(x, y_start)
            pdf.cell(largeur_lieu, row_h, "", border=1, fill=True)
            pdf.set_xy(x, y_start + row_h)
            pdf.cell(largeur_lieu, row_h, "", border=1, fill=True)

            pdf.set_xy(x, y_start)
            if c['count'] > 0:
                pdf.set_font("Arial", 'B', 11)
                pdf.set_text_color(27, 94, 32)
            else:
                pdf.set_font("Arial", size=9)
                pdf.set_text_color(160, 160, 160)
            pdf.cell(largeur_lieu, row_h, str(c['count']), align='C')
            pdf.set_text_color(0, 0, 0)

            if c['dates']:
                pdf.set_xy(x, y_start + row_h)
                pdf.set_font("Arial", size=6.5)
                pdf.set_text_color(110, 110, 110)
                dates_txt = ", ".join(c['dates'])[:40]
                pdf.cell(largeur_lieu, row_h, dates_txt.encode('latin-1', 'replace').decode('latin-1'), align='C')
                pdf.set_text_color(0, 0, 0)
            x += largeur_lieu

        pdf.set_xy(x, y_start)
        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(238, 242, 234)
        pdf.set_text_color(27, 94, 32)
        pdf.cell(largeur_total, row_h * 2, str(r['total']), border=1, fill=True, align='C')
        pdf.set_text_color(0, 0, 0)

        pdf.set_xy(x_start, y_start + row_h * 2)

    if pdf.get_y() + row_h * 2 > pdf.h - pdf.b_margin:
        pdf.add_page()
        draw_header()
    pdf.set_fill_color(238, 242, 234)
    pdf.set_text_color(27, 94, 32)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(largeur_nom, row_h * 2, "Total", border=1, fill=True)
    for lieu in lieux_cols:
        pdf.cell(largeur_lieu, row_h * 2, str(totaux_par_lieu.get(lieu, 0)), border=1, fill=True, align='C')
    pdf.cell(largeur_total, row_h * 2, str(total_general), border=1, fill=True, align='C', ln=True)
    pdf.set_text_color(0, 0, 0)

    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES (inchangés) ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment désactiver/supprimer : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer", type="primary"):
        if pw == current_code or pw == "0000":
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            if table == "adherents":
                load_adherents.clear()
                load_adherents_tous.clear()
            st.success("Opération réussie"); st.rerun()
        else: st.error("Code incorrect")

@st.dialog("✏️ Modifier une AM")
def edit_am_dialog(am_id, nom_actuel, prenom_actuel, nb_enfants_defaut_actuel=1):
    new_nom = st.text_input("Nom", value=nom_actuel).upper().strip()
    new_pre = st.text_input("Prénom", value=prenom_actuel).strip()
    new_nb_defaut = st.number_input(
        "Nombre d'enfants par défaut", min_value=1, max_value=10,
        value=int(nb_enfants_defaut_actuel or 1),
        help="Cette valeur pré-remplira automatiquement le nombre d'enfants lors des inscriptions de cette AM, partout dans le logiciel. Elle reste modifiable au cas par cas lors de chaque inscription."
    )
    if st.button("Enregistrer"):
        if new_nom and new_pre:
            supabase.table("adherents").update({"nom": new_nom, "prenom": new_pre, "nb_enfants_defaut": int(new_nb_defaut)}).eq("id", am_id).execute()
            load_adherents.clear()
            load_adherents_tous.clear()
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

@st.dialog("✅ Confirmation d'inscription")
def confirm_inscription_dialog(nom_complet, id_adh, atelier_id, date_atelier, nb_enfants, requiert_enfants, at_info_log, user_admin="Utilisateur"):
    """Double validation avant d'enregistrer une inscription : récapitulatif + Confirmer / Modifier / Annuler."""
    date_txt = format_date_fr_simple(date_atelier)
    if requiert_enfants:
        suffixe = "enfant" if nb_enfants <= 1 else "enfants"
        st.markdown(f"Inscription de **{nom_complet}** à l'atelier du **{date_txt}** pour **{nb_enfants} {suffixe}**.")
    else:
        st.markdown(f"Inscription de **{nom_complet}** à l'atelier du **{date_txt}**.")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Confirmer l'inscription", type="primary", use_container_width=True):
        supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": atelier_id, "nb_enfants": nb_enfants}).execute()
        enregistrer_log(user_admin, "Inscription", f"{nom_complet} s'inscrit" + (f" (+{nb_enfants} enf.)" if requiert_enfants else "") + f" - {at_info_log}")
        st.rerun()
    if c2.button("✏️ Modifier", use_container_width=True):
        st.rerun()
    if c3.button("❌ Annuler", use_container_width=True):
        st.rerun()

@st.dialog("⚠️ Supprimer le groupe")
def delete_groupe_dialog(groupe_id, nom):
    st.warning(f"Voulez-vous supprimer définitivement le groupe **{nom}** ?\n\nCette suppression est immédiate et n'a aucune incidence sur les inscriptions déjà enregistrées : seul le modèle de saisie rapide est supprimé.")
    if st.button("Oui, supprimer définitivement", type="primary"):
        supabase.table("groupe_membres").delete().eq("groupe_id", groupe_id).execute()
        supabase.table("groupes").delete().eq("id", groupe_id).execute()
        enregistrer_log("Admin", "Suppression groupe", f"Groupe '{nom}' supprimé")
        load_groupes.clear()
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
def edit_atelier_dialog(at_id, titre_actuel, lieu_id_actuel, horaire_id_actuel, capacite_actuelle, lieux_list, horaires_list, map_lieu_id, map_horaire_id, enfants_requis_actuel=True):
    """Dialogue de modification d'un atelier (titre, lieu, horaire, capacité, nombre d'enfants requis)"""
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
    nouveau_flag_enfants = st.checkbox("Demander le nombre d'enfants à l'inscription", value=bool(enfants_requis_actuel), help="Décocher pour ce type d'atelier si le nombre d'enfants n'est pas pertinent (l'inscription se fera alors sans ce champ).")

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
                "capacite_max": nouvelle_capacite,
                "nb_enfants_requis": bool(nouveau_flag_enfants)
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
def load_adherents_tous():
    """Charge TOUTES les AM (actives et inactives) — utilisé pour l'écran Liste AM (filtre de statut, doublons)."""
    res = supabase.table("adherents").select("*").order("nom").order("prenom").execute()
    return res.data

@st.cache_data(ttl=60)
def load_lieux():
    return supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data

@st.cache_data(ttl=60)
def load_horaires():
    return supabase.table("horaires").select("*").eq("est_actif", True).execute().data

@st.cache_data(ttl=30)
def load_groupes():
    """Charge les groupes d'AM avec leurs membres (nom, prénom, statut actif, nb enfants pour ce groupe)."""
    res = supabase.table("groupes").select(
        "id, nom, groupe_membres(id, nb_enfants, adherents(id, nom, prenom, est_actif))"
    ).order("nom").execute()
    groupes = []
    for g in (res.data or []):
        membres = []
        for gm in (g.get('groupe_membres') or []):
            adh = gm.get('adherents') or {}
            membres.append({
                "adherent_id": adh.get('id'),
                "nom": adh.get('nom', '?'),
                "prenom": adh.get('prenom', '?'),
                "est_actif": bool(adh.get('est_actif', False)),
                "nb_enfants": gm.get('nb_enfants', 0)
            })
        membres.sort(key=lambda m: (str(m['nom']).upper(), str(m['prenom']).upper()))
        groupes.append({"id": g['id'], "nom": g['nom'], "membres": membres})
    return groupes

if 'at_list_gen' not in st.session_state: st.session_state['at_list_gen'] = []
if 'super_access' not in st.session_state: st.session_state['super_access'] = False
if 'nb_slots_nouveau_groupe' not in st.session_state: st.session_state['nb_slots_nouveau_groupe'] = 1
if 'groupe_en_edition' not in st.session_state: st.session_state['groupe_en_edition'] = None
if 'reset_form_nouveau_groupe' not in st.session_state: st.session_state['reset_form_nouveau_groupe'] = False
if 'nb_slots_a_nettoyer' not in st.session_state: st.session_state['nb_slots_a_nettoyer'] = 0

# Nettoyage du formulaire "➕ Créer un groupe" après une création réussie.
# Doit impérativement s'exécuter AVANT que les widgets du formulaire (text_input/selectbox) ne soient
# instanciés plus bas dans le script : Streamlit interdit de modifier st.session_state pour une clé
# de widget déjà affiché lors du même passage du script.
if st.session_state['reset_form_nouveau_groupe']:
    st.session_state.pop('nom_nouveau_groupe', None)
    for _i in range(st.session_state['nb_slots_a_nettoyer']):
        st.session_state.pop(f'grp_new_am_{_i}', None)
    st.session_state['reset_form_nouveau_groupe'] = False

current_code = get_secret_code()
res_adh_data = load_adherents()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh_data}
liste_adh = list(dict_adh.keys())
# Nombre d'enfants par défaut de chaque AM (pré-remplissage des inscriptions, reste modifiable au cas par cas)
dict_adh_defaut = {a['id']: int(a.get('nb_enfants_defaut', 1) or 1) for a in res_adh_data}

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
            
            # Ajout d'un cadenas si l'atelier est verrouillé
            if is_verrouille(at):
                statut_p += " 🔒 (verrouillé)"

            # --- DÉFINITION DE at_info_log (AJOUTER CETTE LIGNE) ---
            at_info_log = f"{at['date_atelier']} | {at['horaires']['libelle']} | {at['lieux']['nom']}"            
            
            # --- Vérifier si l'utilisateur courant est déjà inscrit ---
            user_id = dict_adh.get(user_principal)  # user_principal est le nom complet sélectionné
            est_inscrit = any(ins['adherent_id'] == user_id for ins in res_ins_data) if user_id else False
            if est_inscrit:
                # Ajout d'une coche violette après le statut des places (et après le cadenas)
                statut_p += " <span style='color: #9b59b6; font-weight: bold; margin-left: 6px;'>✔️ Inscrite</span>"
            
            # Ligne d'en-tête avec badge, date, titre, lieu, horaire, places
            badge_cat = badge_categorie(at)
            ligne_entete = f"{badge_cat} **{format_date_fr_complete(at['date_atelier'])}** — {at['titre']} | 📍 {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_p}"
            st.markdown(ligne_entete, unsafe_allow_html=True)

            # Expander pour la gestion des inscriptions
            requiert_enfants = enfants_requis(at)
            with st.expander("📋 Gérer les inscriptions"):
                if is_verrouille(at):
                    st.warning("🔒 Cet atelier est verrouillé par l'administration. Seul l'admin peut modifier les inscriptions.")
                    # Affichage simple des inscrits
                    for i in res_ins_data:
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        if requiert_enfants:
                            st.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        else:
                            st.write(f"• {n_f}")
                else:
                    # Affichage des inscrits avec modification possible
                    if res_ins_data:
                        for i in res_ins_data:
                            n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                            if requiert_enfants:
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
                                col_nom, col_del = st.columns([0.85, 0.15])
                                col_nom.write(f"• {n_f}")
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
                    if requiert_enfants:
                        c1, c2, c3 = st.columns([2, 1, 1])
                        qui = c1.selectbox("Assistante maternelle", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                        id_adh_qui = dict_adh.get(qui)
                        default_nb_e = dict_adh_defaut.get(id_adh_qui, 1) if id_adh_qui else 1
                        nb_e = c2.number_input("Nombre d'enfants", min_value=1, max_value=10, value=default_nb_e, key=f"e_{at['id']}_{id_adh_qui or 'none'}")
                        bouton_valider = c3
                    else:
                        c1, c3 = st.columns([3, 1])
                        qui = c1.selectbox("Assistante maternelle", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                        nb_e = 0
                        bouton_valider = c3
                    if bouton_valider.button("Valider l'inscription", key=f"v_{at['id']}", type="primary"):
                        if qui != "Choisir...":
                            id_adh = dict_adh[qui]
                            existing = next((ins for ins in res_ins_data if ins['adherent_id'] == id_adh), None)
                            if existing:
                                st.warning(f"{qui} est déjà inscrite à cet atelier. Utilisez le bouton Modifier pour changer le nombre d'enfants.")
                            else:
                                if restantes - (1 + nb_e) < 0:
                                    st.error("Manque de places")
                                else:
                                    confirm_inscription_dialog(qui, id_adh, at['id'], at['date_atelier'], nb_e, requiert_enfants, at_info_log, user_principal)

# ==========================================
# SECTION 📊 SUIVI & RÉCAP (inchangée)
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2, t3 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier", "🪑 Places restantes"])

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
                bouton_agenda = bouton_agenda_html(at['date_atelier'], at['horaires']['libelle'], at['titre'], at['lieux']['nom'])
                bouton_agenda_iphone = bouton_agenda_iphone_html(at['date_atelier'], at['horaires']['libelle'], at['titre'], at['lieux']['nom'])
                suffixe_enf = f" **({i['nb_enfants']} enf.)**" if enfants_requis(at) else ""
                st.markdown(f"{badge_cat}{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> <span class='horaire-text'>({at['horaires']['libelle']})</span>{suffixe_enf} {bouton_agenda} {bouton_agenda_iphone}", unsafe_allow_html=True)
        else:
            st.info("Aucune inscription trouvée pour les AM sélectionnées.")

    with t2:
        c_d1, c_d2 = st.columns(2)
        d_s = c_d1.date_input("Du", date.today(), key="pub_d1", format="DD/MM/YYYY")
        d_e = c_d2.date_input("Au", ajouter_mois(d_s, 6), key="pub_d2", format="DD/MM/YYYY")
        
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
                requiert_enfants_a = enfants_requis(a)
                t_ad, t_en = len(ins_at), sum(p['nb_enfants'] for p in ins_at)
                restantes = a['capacite_max'] - (t_ad + t_en)
                cl_c = "alerte-complet" if restantes <= 0 else ""
                badge_cat = badge_categorie(a)
                badge_enf = f" <span class='compteur-badge'>👶 {t_en} enf.</span>" if requiert_enfants_a else ""
                badges_compteurs = f"<span class='compteur-badge'>👤 {t_ad} AM</span>{badge_enf} <span class='compteur-badge {cl_c}'>🏁 {restantes} pl.</span>"

                # Ligne unique avec retour à la ligne automatique
                st.markdown(
                    f"""
                    <div style="white-space: normal; word-wrap: break-word; margin-bottom: 5px;">
                        {badge_cat}<strong>{format_date_fr_complete(a['date_atelier'])}</strong> | {a['titre']} |
                        <span class='lieu-badge' style='background-color:{c_l};'>{a['lieux']['nom']}</span> |
                        <span class='horaire-text'>{a['horaires']['libelle']}</span>
                        {badges_compteurs}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if ins_at:
                    ins_s = sorted(ins_at, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                    html = "<div class='container-inscrits'>"
                    for p in ins_s:
                        suffixe_p = f' <span class="nb-enfants-focus">({p["nb_enfants"]} enfants)</span>' if requiert_enfants_a else ""
                        html += f'<span class="liste-inscrits">• {p["adherents"]["prenom"]} {p["adherents"]["nom"]}{suffixe_p}</span>'
                    st.markdown(html + "</div>", unsafe_allow_html=True)
                
                if idx < len(ats_raw.data) - 1:
                    st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)
        else:
            st.info("Aucun atelier trouvé sur cette période.")

    with t3:
        st.caption("Ateliers non complets, groupés par lieu, triés par nombre de places restantes décroissant.")

        cpr1, cpr2 = st.columns(2)
        d_deb_pr = cpr1.date_input("Du", date.today(), key="pr_date_debut", format="DD/MM/YYYY")
        d_fin_pr = cpr2.date_input("Au", fin_defaut_places_restantes(), key="pr_date_fin", format="DD/MM/YYYY")
        st.caption(f"Période calculée automatiquement (du jour au 31/07 suivant) ; modifiable librement.")

        lieux_dispo_pr = sorted([l['nom'] for l in load_lieux()])
        lieux_choisis_pr = st.multiselect(
            "Filtrer par lieu :", lieux_dispo_pr, default=lieux_dispo_pr, key="pr_filtre_lieux"
        )

        filtre_verrou_pr = st.radio(
            "Ateliers :",
            ["Tous les ateliers", "Réservés à la responsable (verrouillés)", "Ouverts uniquement"],
            index=0, horizontal=True, key="pr_filtre_verrou"
        )

        if not lieux_choisis_pr:
            st.info("Sélectionnez au moins un lieu.")
        else:
            ats_pr = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)") \
                .eq("est_actif", True) \
                .gte("date_atelier", str(d_deb_pr)) \
                .lte("date_atelier", str(d_fin_pr)) \
                .order("date_atelier").execute().data or []

            # Filtre par lieu (relation, donc filtré après récupération)
            ats_pr = [a for a in ats_pr if a.get('lieux') and a['lieux']['nom'] in lieux_choisis_pr]

            # Filtre par statut de verrouillage
            if filtre_verrou_pr == "Réservés à la responsable (verrouillés)":
                ats_pr = [a for a in ats_pr if is_verrouille(a)]
            elif filtre_verrou_pr == "Ouverts uniquement":
                ats_pr = [a for a in ats_pr if not is_verrouille(a)]

            occ_par_atelier_pr = {}
            if ats_pr:
                at_ids_pr = [a['id'] for a in ats_pr]
                ins_pr = supabase.table("inscriptions").select("atelier_id, nb_enfants").in_("atelier_id", at_ids_pr).execute().data or []
                for ins in ins_pr:
                    e = occ_par_atelier_pr.setdefault(ins['atelier_id'], {"ad": 0, "enf": 0})
                    e["ad"] += 1
                    e["enf"] += ins['nb_enfants'] or 0

            # Regroupement par lieu, ateliers complets exclus
            lignes_par_lieu_pr = {}
            for a in ats_pr:
                occ = occ_par_atelier_pr.get(a['id'], {"ad": 0, "enf": 0})
                restantes_pr = a['capacite_max'] - (occ['ad'] + occ['enf'])
                if restantes_pr <= 0:
                    continue
                lignes_par_lieu_pr.setdefault(a['lieux']['nom'], []).append({
                    "date": a['date_atelier'],
                    "titre": a['titre'],
                    "restantes": restantes_pr,
                    "verrouille": is_verrouille(a)
                })

            if not lignes_par_lieu_pr:
                st.info("Aucun atelier avec des places restantes sur cette période et ces filtres.")
            else:
                ordre_lieux_pr = sorted(
                    lignes_par_lieu_pr.keys(),
                    key=lambda l: (-max(r['restantes'] for r in lignes_par_lieu_pr[l]), l)
                )
                for nom_lieu_pr in ordre_lieux_pr:
                    lignes_pr = sorted(lignes_par_lieu_pr[nom_lieu_pr], key=lambda r: -r['restantes'])
                    nb_at_pr = len(lignes_pr)
                    st.markdown(
                        f"<div style='font-weight:700;color:#1b5e20;border-bottom:2px solid #1b5e20;"
                        f"padding:8px 2px 6px;margin-top:14px;'>{html_lib.escape(nom_lieu_pr)} "
                        f"<span style='font-weight:400;color:#777;font-size:0.82rem;'>"
                        f"({nb_at_pr} atelier{'s' if nb_at_pr > 1 else ''} non complet{'s' if nb_at_pr > 1 else ''})</span></div>",
                        unsafe_allow_html=True
                    )
                    html_pr = "<table style='border-collapse:collapse;width:100%;'>"
                    html_pr += (
                        "<tr>"
                        "<th style='text-align:left;padding:6px 8px;font-size:0.72rem;text-transform:uppercase;color:#777;'>Date</th>"
                        "<th style='text-align:left;padding:6px 8px;font-size:0.72rem;text-transform:uppercase;color:#777;'>Atelier</th>"
                        "<th style='text-align:left;padding:6px 8px;font-size:0.72rem;text-transform:uppercase;color:#777;'>Places restantes</th>"
                        "</tr>"
                    )
                    for r in lignes_pr:
                        verrou_txt = (
                            " <span style='font-size:0.76rem;color:#e65100;font-weight:600;'>🔒 verrouillé</span>"
                            if r['verrouille'] else ""
                        )
                        est_faible = r['restantes'] <= 3
                        couleur_badge = "#e65100" if est_faible else "#1b5e20"
                        fond_badge = "#fdf2e9" if est_faible else "#eef2ea"
                        suffixe_place = "place" if r['restantes'] <= 1 else "places"
                        html_pr += (
                            "<tr>"
                            f"<td style='padding:8px;border-top:1px solid #e2ddd0;white-space:nowrap;'>{format_date_fr_simple(r['date'])}</td>"
                            f"<td style='padding:8px;border-top:1px solid #e2ddd0;font-weight:600;'>{html_lib.escape(r['titre'])}{verrou_txt}</td>"
                            f"<td style='padding:8px;border-top:1px solid #e2ddd0;'>"
                            f"<span style='font-family:monospace;font-weight:700;padding:2px 10px;border-radius:999px;"
                            f"background:{fond_badge};color:{couleur_badge};'>{r['restantes']} {suffixe_place}</span></td>"
                            "</tr>"
                        )
                    html_pr += "</table>"
                    st.markdown(html_pr, unsafe_allow_html=True)

# ==========================================
# SECTION 🔐 ADMINISTRATION (inchangée)
# ==========================================

elif menu == "🔐 Administration":
    # Gestion de l'authentification admin
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    
    # Formulaire pour la saisie du code admin (permet la validation par Entrée)
    with st.form(key="admin_login_form"):
        col1, col2 = st.columns([0.7, 0.3])
        with col1:
            admin_code_input = st.text_input("Code secret admin", type="password", key="admin_code_input")
        with col2:
            submitted = st.form_submit_button("Valider")
        if submitted:
            if admin_code_input == current_code:
                st.session_state.admin_authenticated = True
                st.success("Accès admin validé")
                st.rerun()
            else:
                st.error("Code incorrect")
                st.session_state.admin_authenticated = False
    
    # Bouton Super Admin en dehors du formulaire
    if st.button("🔑 Code Super Admin"):
        super_admin_dialog()
    
    # Affichage des onglets si authentifié (admin classique ou super admin)
    if st.session_state.admin_authenticated or st.session_state.get('super_access', False):
        t1, t2, t3, t4, t5, t6, t7, t8, t9, t10 = st.tabs([
            "🏗️ Ateliers", "📊 Suivi AM", "🔎 Suivi Inscription", "📅 Planning Ateliers",
            "📈 Statistiques de participation", "👥 Liste AM", "👥➕ Groupes",
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
                                "Verrouillé": False,
                                "Nb enfants requis": True
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
                            "Verrouillé": st.column_config.CheckboxColumn(default=False, help="Si coché, seul l'admin peut gérer les inscriptions"),
                            "Nb enfants requis": st.column_config.CheckboxColumn(default=True, help="Si décoché, le nombre d'enfants ne sera pas demandé lors de l'inscription à cet atelier")
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
                                "categorie_color": "#3498db",   # bleu par défaut
                                "nb_enfants_requis": bool(r.get("Nb enfants requis", True))
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
                fe = cf2.date_input("Au", fs+timedelta(days=90), format="DD/MM/YYYY", key="rep_d2")
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
                    enfants_icon = "" if enfants_requis(a) else " <span class='badge-verrouille' style='background-color:#95a5a6;'>👶 non requis</span>"

                    ca, cb, cc, cg, cd, ce_couleur, ce_btn, cf_col = st.columns([0.32, 0.08, 0.08, 0.10, 0.08, 0.12, 0.08, 0.08])
                    ca.markdown(f"{badge_cat}{badge_actif}**{date_str}** | {horaire_str} | {titre_str} | {lieu_badge}{verrou_icon}{enfants_icon}", unsafe_allow_html=True)
                    
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
                    
                    # Enfants requis / non requis
                    btn_e = "👶✅" if enfants_requis(a) else "👶🚫"
                    aide_e = "Nombre d'enfants actuellement requis à l'inscription. Cliquer pour le rendre optionnel." if enfants_requis(a) else "Nombre d'enfants actuellement non requis à l'inscription. Cliquer pour le rendre obligatoire."
                    if cg.button(btn_e, key=f"at_enf_{a['id']}", help=aide_e):
                        nouvel_etat_enf = not enfants_requis(a)
                        supabase.table("ateliers").update({"nb_enfants_requis": bool(nouvel_etat_enf)}).eq("id", a['id']).execute()
                        enregistrer_log("Admin", "Modification atelier", f"Atelier '{a['titre']}' du {a['date_atelier']} : nombre d'enfants {'requis' if nouvel_etat_enf else 'non requis'}")
                        st.rerun()

                    # Modifier
                    if cd.button("✏️", key=f"at_edit_{a['id']}"):
                        edit_atelier_dialog(a['id'], a['titre'], a['lieu_id'], a['horaire_id'], a['capacite_max'], l_raw, h_raw, map_l_id, map_h_id, enfants_requis(a))
                    
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
                    suffixe_enf_adm = f" **({i['nb_enfants']} enf.)**" if enfants_requis(at) else ""
                    st.markdown(f"{badge_cat}{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> <span class='horaire-text'>({at['horaires']['libelle']})</span>{suffixe_enf_adm}", unsafe_allow_html=True)
            else:
                st.info("Aucune inscription trouvée pour les AM sélectionnées.")

        with t3: # 🔎 SUIVI INSCRIPTION
            st.subheader("🔎 Suivi Inscription")
            st.caption("Nombre d'inscriptions par assistante maternelle et par lieu, sur la période choisie.")

            debut_defaut_si, fin_defaut_si = periode_defaut_suivi_inscriptions()

            csi1, csi2, csi3 = st.columns([1, 1, 1.6])
            d_deb_si = csi1.date_input("Du", debut_defaut_si, key="si_date_debut", format="DD/MM/YYYY")
            d_fin_si = csi2.date_input("Au", fin_defaut_si, key="si_date_fin", format="DD/MM/YYYY")
            csi3.markdown(
                f"<div style='font-size:0.78rem;color:#666;padding-top:28px;'>Période calculée automatiquement à partir d'aujourd'hui "
                f"({date.today().strftime('%d/%m/%Y')}) ; modifiable librement.</div>",
                unsafe_allow_html=True
            )

            filtre_statut_si = st.radio("Ateliers :", ["Actifs", "Inactifs", "Tous"], index=0, horizontal=True, key="si_filtre_statut")

            query_si = supabase.table("ateliers").select("id, date_atelier, est_actif, lieux(nom)") \
                .gte("date_atelier", str(d_deb_si)).lte("date_atelier", str(d_fin_si))
            if filtre_statut_si == "Actifs":
                query_si = query_si.eq("est_actif", True)
            elif filtre_statut_si == "Inactifs":
                query_si = query_si.eq("est_actif", False)
            ateliers_si = query_si.execute().data or []
            at_by_id_si = {a['id']: a for a in ateliers_si}

            if at_by_id_si:
                ins_si = supabase.table("inscriptions").select("adherent_id, atelier_id, adherents(nom, prenom)") \
                    .in_("atelier_id", list(at_by_id_si.keys())).execute().data or []
            else:
                ins_si = []

            # Colonnes = tous les lieux actifs, plus tout lieu apparaissant dans la période (au cas où désactivé depuis)
            lieux_cols_si = sorted(set([l['nom'] for l in load_lieux()]) | set(
                a['lieux']['nom'] for a in ateliers_si if a.get('lieux')
            ))

            # Regroupement : AM -> lieu -> {count, dates}
            matrice_si = {}
            for ins in ins_si:
                at_si = at_by_id_si.get(ins['atelier_id'])
                adh_si = ins.get('adherents') or {}
                aid_si = ins.get('adherent_id')
                if not at_si or aid_si is None or not at_si.get('lieux'):
                    continue
                lieu_nom_si = at_si['lieux']['nom']
                entree = matrice_si.setdefault(aid_si, {"nom": adh_si.get('nom', '?'), "prenom": adh_si.get('prenom', '?'), "par_lieu": {}})
                cellule = entree["par_lieu"].setdefault(lieu_nom_si, {"count": 0, "dates": []})
                cellule["count"] += 1
                cellule["dates"].append(at_si['date_atelier'])

            rows_si = []
            for aid_si, entree in matrice_si.items():
                cells_fmt = {}
                for lieu in lieux_cols_si:
                    c = entree["par_lieu"].get(lieu)
                    if c:
                        dates_aff = [datetime.strptime(dd, "%Y-%m-%d").strftime("%d/%m") for dd in sorted(c['dates'])]
                        cells_fmt[lieu] = {"count": c['count'], "dates": dates_aff}
                    else:
                        cells_fmt[lieu] = {"count": 0, "dates": []}
                total_am_si = sum(v['count'] for v in cells_fmt.values())
                rows_si.append({"nom": entree['nom'], "prenom": entree['prenom'], "cells": cells_fmt, "total": total_am_si})

            rows_si.sort(key=lambda r: (str(r['nom']).upper(), str(r['prenom']).upper()))

            totaux_par_lieu_si = {lieu: sum(r['cells'][lieu]['count'] for r in rows_si) for lieu in lieux_cols_si}

            # On ne garde que les lieux ayant au moins 1 inscription sur la période (colonnes vides masquées)
            lieux_cols_si = [lieu for lieu in lieux_cols_si if totaux_par_lieu_si[lieu] > 0]
            totaux_par_lieu_si = {lieu: totaux_par_lieu_si[lieu] for lieu in lieux_cols_si}

            total_general_si = sum(totaux_par_lieu_si.values())

            periode_txt_si = f"Periode du {d_deb_si.strftime('%d/%m/%Y')} au {d_fin_si.strftime('%d/%m/%Y')} - Ateliers {filtre_statut_si.lower()}"

            ce_si1, ce_si2 = st.columns(2)
            ce_si1.download_button(
                "📊 Excel", data=export_suivi_inscription_excel(rows_si, lieux_cols_si, totaux_par_lieu_si, total_general_si),
                file_name="suivi_inscription.xlsx", key="si_excel"
            )
            ce_si2.download_button(
                "📄 PDF", data=export_suivi_inscription_pdf("Suivi Inscription", rows_si, lieux_cols_si, totaux_par_lieu_si, total_general_si, periode_txt_si),
                file_name="suivi_inscription.pdf", key="si_pdf"
            )

            if not rows_si:
                st.info("Aucune inscription trouvée sur cette période.")
            else:
                html_si = (
                    "<div style='overflow:auto;max-height:65vh;border:1px solid #e2ddd0;border-radius:6px;'>"
                    "<table style='border-collapse:collapse;width:100%;min-width:700px;'>"
                )
                html_si += "<thead><tr>"
                html_si += "<th style='text-align:left;padding:8px 10px;background:#1b5e20;color:white;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.04em;position:sticky;top:0;z-index:2;'>Assistante Maternelle</th>"
                for lieu in lieux_cols_si:
                    html_si += f"<th style='text-align:left;padding:8px 10px;background:#1b5e20;color:white;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.04em;position:sticky;top:0;z-index:2;'>{html_lib.escape(lieu)}</th>"
                html_si += "<th style='text-align:center;padding:8px 10px;background:#4c8c52;color:white;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.04em;position:sticky;top:0;z-index:2;'>Total</th></tr></thead>"
                html_si += "<tbody>"

                for idx_si, r in enumerate(rows_si):
                    bg_si = "#faf9f4" if idx_si % 2 == 1 else "#ffffff"
                    html_si += f"<tr style='background:{bg_si};'>"
                    html_si += (
                        f"<td style='padding:8px 10px;border-top:1px solid #e2ddd0;font-weight:700;white-space:nowrap;'>"
                        f"{html_lib.escape(r['nom'])} <span style='font-weight:400;color:#666;'>{html_lib.escape(r['prenom'])}</span></td>"
                    )
                    for lieu in lieux_cols_si:
                        c = r['cells'][lieu]
                        if c['count'] > 0:
                            dates_txt = ", ".join(c['dates'])
                            html_si += (
                                f"<td style='padding:8px 10px;border-top:1px solid #e2ddd0;'>"
                                f"<span style='font-size:1.05rem;font-weight:800;color:#1b5e20;'>{c['count']}</span><br>"
                                f"<span style='font-size:0.72rem;color:#777;'>{html_lib.escape(dates_txt)}</span></td>"
                            )
                        else:
                            html_si += "<td style='padding:8px 10px;border-top:1px solid #e2ddd0;color:#bbb;'>0</td>"
                    html_si += (
                        f"<td style='padding:8px 10px;border-top:1px solid #e2ddd0;text-align:center;font-weight:800;"
                        f"color:#1b5e20;background:#eef2ea;'>{r['total']}</td>"
                    )
                    html_si += "</tr>"

                html_si += "<tr style='background:#eef2ea;font-weight:700;'>"
                html_si += "<td style='padding:8px 10px;border-top:2px solid #1b5e20;color:#1b5e20;'>Total</td>"
                for lieu in lieux_cols_si:
                    html_si += f"<td style='padding:8px 10px;border-top:2px solid #1b5e20;color:#1b5e20;text-align:center;'>{totaux_par_lieu_si[lieu]}</td>"
                html_si += f"<td style='padding:8px 10px;border-top:2px solid #1b5e20;color:#1b5e20;text-align:center;'>{total_general_si}</td>"
                html_si += "</tr>"

                html_si += "</tbody></table></div>"
                st.markdown(html_si, unsafe_allow_html=True)

        with t4: # PLANNING ATELIERS (Admin)
            st.subheader("📅 Planning des Ateliers")
            
            filtre_statut = st.radio("Filtrer par statut :", ["Tous", "Actifs", "Inactifs"], horizontal=True, key="admin_plan_filtre")
            
            c1_adm, c2_adm = st.columns(2)
            d_s_a = c1_adm.date_input("Du", date.today(), key="adm_plan_d1", format="DD/MM/YYYY")
            d_e_a = c2_adm.date_input("Au", ajouter_mois(d_s_a, 6), key="adm_plan_d2", format="DD/MM/YYYY")
            
            query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(d_s_a)).lte("date_atelier", str(d_e_a))
            if filtre_statut == "Actifs":
                query = query.eq("est_actif", True)
            elif filtre_statut == "Inactifs":
                query = query.eq("est_actif", False)
            ats_adm = query.order("date_atelier").execute()
        
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
        
            df_adm_at = pd.DataFrame(adm_ins_list) if adm_ins_list else pd.DataFrame(columns=["Date", "Atelier", "Lieu", "AM", "Enfants"])
            cea1, cea2 = st.columns(2)
            cea1.download_button("📥 Excel Planning (Admin)", data=export_to_excel(df_adm_at), file_name="admin_planning_ateliers.xlsx", key="adm_exp_xl")
            cea2.download_button("📥 PDF Planning (Admin)", data=export_planning_ateliers_pdf(
                "Planning des Ateliers (Administration)", ats_adm.data if ats_adm.data else [], lambda aid: cache_ins_adm.get(aid, [])
            ), file_name="admin_planning_ateliers.pdf", key="adm_exp_pdf")
        
            if ats_adm.data:
                for index, a in enumerate(ats_adm.data):
                    c_l = get_color(a['lieux']['nom'])
                    ins_at = cache_ins_adm.get(a['id'], [])
                    t_ad = len(ins_at)
                    t_en = sum(p['nb_enfants'] for p in ins_at)
                    restantes = a['capacite_max'] - (t_ad + t_en)
                    cl_c = "alerte-complet" if restantes <= 0 else ""
                    verrou_icon = " 🔒" if is_verrouille(a) else ""
                    at_info_log = f"{a['date_atelier']} | {a['horaires']['libelle']} | {a['lieux']['nom']}"
                    badge_cat = badge_categorie(a)
                    requiert_enfants_adm = enfants_requis(a)
                    badge_enf_adm = f" <span class='compteur-badge'>👶 {t_en} enf.</span>" if requiert_enfants_adm else ""
                    badges_compteurs_adm = f"<span class='compteur-badge'>👤 {t_ad} AM</span>{badge_enf_adm} <span class='compteur-badge {cl_c}'>🏁 {restantes} pl.</span>"

                    # Ligne d'en-tête avec retour à la ligne
                    st.markdown(
                        f"""
                        <div style="white-space: normal; word-wrap: break-word; margin-bottom: 5px;">
                            {badge_cat}<strong>{format_date_fr_complete(a['date_atelier'])}</strong> | {a['titre']} |
                            <span class='lieu-badge' style='background-color:{c_l};'>{a['lieux']['nom']}</span> |
                            <span class='horaire-text'>{a['horaires']['libelle']}</span>{verrou_icon}
                            {badges_compteurs_adm}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    if ins_at:
                        ins_s = sorted(ins_at, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                        for p in ins_s:
                            n_f = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                            if requiert_enfants_adm:
                                cp1, cp2, cp3, cp4 = st.columns([0.45, 0.2, 0.2, 0.15])
                                cp1.write(f"• {n_f}")
                                new_nb = cp2.number_input("Enf.", 1, 10, int(p['nb_enfants']), key=f"adm_nb_{p['id']}", label_visibility="collapsed")
                                if cp3.button("✏️ Modifier", key=f"adm_mod_{p['id']}"):
                                    supabase.table("inscriptions").update({"nb_enfants": new_nb}).eq("id", p['id']).execute()
                                    enregistrer_log("Admin", "Modification (admin)", f"{n_f} → {new_nb} enfants - {at_info_log}")
                                    st.rerun()
                                if cp4.button("🗑️", key=f"adm_del_plan_{p['id']}"):
                                    confirm_unsubscribe_dialog(p['id'], n_f, at_info_log, "Admin")
                            else:
                                cp1, cp4 = st.columns([0.85, 0.15])
                                cp1.write(f"• {n_f}")
                                if cp4.button("🗑️", key=f"adm_del_plan_{p['id']}"):
                                    confirm_unsubscribe_dialog(p['id'], n_f, at_info_log, "Admin")

                    col_inscr_am, col_inscr_grp = st.columns(2)

                    with col_inscr_am:
                        with st.expander(f"➕ Inscrire une AM à cet atelier", expanded=False):
                            if requiert_enfants_adm:
                                ca1, ca2, ca3 = st.columns([2, 1, 1])
                                qui_adm = ca1.selectbox("AM à inscrire", ["Choisir..."] + liste_adh, key=f"adm_qui_{a['id']}")
                                id_adh_qui_adm = dict_adh.get(qui_adm)
                                default_nb_adm = dict_adh_defaut.get(id_adh_qui_adm, 1) if id_adh_qui_adm else 1
                                nb_adm = ca2.number_input("Enfants", 1, 10, default_nb_adm, key=f"adm_enf_{a['id']}_{id_adh_qui_adm or 'none'}")
                                bouton_inscr_adm = ca3
                            else:
                                ca1, ca3 = st.columns([3, 1])
                                qui_adm = ca1.selectbox("AM à inscrire", ["Choisir..."] + liste_adh, key=f"adm_qui_{a['id']}")
                                nb_adm = 0
                                bouton_inscr_adm = ca3
                            if bouton_inscr_adm.button("✅ Inscrire", key=f"adm_ins_{a['id']}", type="primary"):
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
                                            enregistrer_log("Admin", "Inscription (admin)", f"{qui_adm} inscrite" + (f" (+{nb_adm} enf.)" if requiert_enfants_adm else "") + f" - {at_info_log}")
                                            st.rerun()

                    with col_inscr_grp:
                        with st.expander("➕ Inscrire un groupe", expanded=False):
                            groupes_disponibles = load_groupes()
                            if not groupes_disponibles:
                                st.info("Aucun groupe créé. Rendez-vous dans l'onglet 👥➕ Groupes pour en créer un.")
                            else:
                                noms_groupes = [gr['nom'] for gr in groupes_disponibles]
                                groupe_choisi_nom = st.selectbox("Groupe à inscrire", noms_groupes, key=f"grp_choix_{a['id']}")
                                groupe_choisi = next(gr for gr in groupes_disponibles if gr['nom'] == groupe_choisi_nom)

                                lignes_apercu = []
                                for m in groupe_choisi['membres']:
                                    etat = " *(désactivée)*" if not m['est_actif'] else ""
                                    if requiert_enfants_adm:
                                        lignes_apercu.append(f"- {m['prenom']} {m['nom']} — {m['nb_enfants']} enfant(s){etat}")
                                    else:
                                        lignes_apercu.append(f"- {m['prenom']} {m['nom']}{etat}")
                                st.markdown("\n".join(lignes_apercu))

                                nb_am_actives = sum(1 for m in groupe_choisi['membres'] if m['est_actif'])
                                nb_enf_total = sum(m['nb_enfants'] for m in groupe_choisi['membres'] if m['est_actif']) if requiert_enfants_adm else 0
                                places_totales = nb_am_actives + nb_enf_total
                                suffixe_caption = f" · {nb_enf_total} enfants" if requiert_enfants_adm else ""
                                st.caption(f"{nb_am_actives} AM{suffixe_caption} → {places_totales} places nécessaires si toutes inscrites")

                                if st.button("✅ Inscrire le groupe", key=f"grp_ins_{a['id']}", type="primary"):
                                    deja_inscrits, inactifs, a_inscrire = [], [], []
                                    for m in groupe_choisi['membres']:
                                        nom_complet_m = f"{m['prenom']} {m['nom']}"
                                        if not m['est_actif']:
                                            inactifs.append(nom_complet_m)
                                            continue
                                        existing_m = next((ins for ins in ins_at if ins['adherent_id'] == m['adherent_id']), None)
                                        if existing_m:
                                            deja_inscrits.append(nom_complet_m)
                                            continue
                                        nb_e_m = m['nb_enfants'] if requiert_enfants_adm else 0
                                        a_inscrire.append({"adherent_id": m['adherent_id'], "nom_complet": nom_complet_m, "nb_enfants": nb_e_m})

                                    places_necessaires = sum(1 + x['nb_enfants'] for x in a_inscrire)
                                    if a_inscrire and places_necessaires > restantes:
                                        st.error(f"🚨 Capacité insuffisante : il manque {places_necessaires - restantes} place(s) pour inscrire tout le groupe ({places_necessaires} nécessaires, {restantes} disponibles). Aucune inscription n'a été effectuée.")
                                    else:
                                        if a_inscrire:
                                            rows_ins = [{"adherent_id": x['adherent_id'], "atelier_id": a['id'], "nb_enfants": x['nb_enfants']} for x in a_inscrire]
                                            supabase.table("inscriptions").insert(rows_ins).execute()
                                            noms_ajoutes = ", ".join(x['nom_complet'] for x in a_inscrire)
                                            enregistrer_log("Admin", "Inscription groupe", f"Groupe '{groupe_choisi['nom']}' inscrit : {noms_ajoutes} - {at_info_log}")
                                            st.success(f"✅ Groupe inscrit : {len(a_inscrire)} AM ajoutée(s).")
                                        else:
                                            st.info("Aucune nouvelle inscription à ajouter (toutes les AM actives du groupe sont déjà inscrites).")
                                        if deja_inscrits:
                                            st.info("ℹ️ Déjà inscrite(s), non modifiée(s) : " + ", ".join(deja_inscrits))
                                        if inactifs:
                                            st.warning("⚠️ Non inscrite(s) car plus active(s) : " + ", ".join(inactifs))
                                        st.rerun()
        
                    if index < len(ats_adm.data) - 1:
                        st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)
            else:
                st.info("Aucun atelier trouvé sur cette période.")

        with t5: # STATS
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
                    nb_ateliers_r = r['Nombre d\'ateliers']
                    pdf_stat_lines.append(f"{r['Assistante Maternelle']} : {nb_ateliers_r} atelier(s)")
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
                        
        with t6: # 👥 LISTE AM
            with st.form("add_am"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nom").upper().strip()
                pre = " ".join([w.capitalize() for w in c2.text_input("Prénom").split()]).strip()
                nb_defaut_nouveau = st.number_input(
                    "Nombre d'enfants par défaut", min_value=1, max_value=10, value=1,
                    help="Cette valeur pré-remplira automatiquement le nombre d'enfants lors des inscriptions de cette AM, partout dans le logiciel. Elle reste modifiable au cas par cas lors de chaque inscription."
                )
                if st.form_submit_button("➕ Ajouter"):
                    if nom and pre:
                        supabase.table("adherents").insert({"nom": nom, "prenom": pre, "est_actif": True, "nb_enfants_defaut": int(nb_defaut_nouveau)}).execute()
                        load_adherents.clear()
                        load_adherents_tous.clear()
                        st.rerun()

            st.markdown("---")
            filtre_am_statut = st.radio("Filtrer par statut :", ["Actifs", "Inactifs", "Tous"], index=0, horizontal=True, key="am_filtre_statut")

            tous_adh_am = load_adherents_tous()

            # Détection des doublons : même nom + prénom, tous statuts confondus
            compte_doublons = {}
            for u in tous_adh_am:
                cle_dbl = (str(u.get('nom', '')).strip().upper(), str(u.get('prenom', '')).strip().lower())
                compte_doublons[cle_dbl] = compte_doublons.get(cle_dbl, 0) + 1

            if filtre_am_statut == "Actifs":
                adh_affiches = [u for u in tous_adh_am if u.get('est_actif', True)]
            elif filtre_am_statut == "Inactifs":
                adh_affiches = [u for u in tous_adh_am if not u.get('est_actif', True)]
            else:
                adh_affiches = tous_adh_am

            if not adh_affiches:
                st.info("Aucune AM ne correspond à ce filtre.")

            for u in adh_affiches:
                c1, c_edit, c_del = st.columns([0.7, 0.15, 0.15])
                nb_defaut_affiche = int(u.get('nb_enfants_defaut', 1) or 1)
                cle_u = (str(u.get('nom', '')).strip().upper(), str(u.get('prenom', '')).strip().lower())
                est_doublon = compte_doublons.get(cle_u, 0) > 1
                badge_statut = "" if u.get('est_actif', True) else " <span style='color:#fff;background-color:#b71c1c;border-radius:4px;padding:1px 6px;font-size:0.75rem;margin-left:6px;'>🚫 Inactive</span>"

                style_nom = "background-color:#fff3b0; padding:2px 5px; border-radius:4px;" if est_doublon else ""
                ligne_nom = f"<span style='{style_nom}'><strong>{u.get('nom','')}</strong> {u.get('prenom','')}</span>{badge_statut}"
                if est_doublon:
                    ligne_nom += " <span style='color:#b8860b; font-size:0.8rem;'>⚠️ Doublon possible</span>"

                c1.markdown(
                    f"{ligne_nom}  \n<span style='color:#666;font-size:0.85rem;'>👶 {nb_defaut_affiche} enfant(s) par défaut</span>",
                    unsafe_allow_html=True
                )
                if c_edit.button("✏️ Modifier", key=f"am_edit_{u['id']}"): edit_am_dialog(u['id'], u['nom'], u['prenom'], nb_defaut_affiche)
                if c_del.button("🗑️", key=f"am_del_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t7: # 👥➕ GROUPES
            st.subheader("👥➕ Groupes")
            st.caption("Créez des groupes d'assistantes maternelles pour accélérer l'inscription aux ateliers gérés par le RPE. Une AM peut appartenir à plusieurs groupes, avec un nombre d'enfants différent selon le groupe. Modifier ou supprimer un groupe n'a aucune incidence sur les inscriptions déjà enregistrées.")

            # --- Création d'un nouveau groupe ---
            with st.expander("➕ Créer un groupe", expanded=False):
                nom_nouveau_groupe = st.text_input("Nom du groupe", key="nom_nouveau_groupe")

                nouveaux_membres = []
                for i in range(st.session_state['nb_slots_nouveau_groupe']):
                    cgm1, cgm2, cgm3 = st.columns([2, 1, 0.3])
                    am_choisie = cgm1.selectbox("Assistante maternelle", ["Choisir..."] + liste_adh, key=f"grp_new_am_{i}")
                    id_adh_slot = dict_adh.get(am_choisie)
                    default_nb_slot = dict_adh_defaut.get(id_adh_slot, 1) if id_adh_slot else 1
                    nb_enf_choisi = cgm2.number_input("Enfants", 1, 10, default_nb_slot, key=f"grp_new_enf_{i}_{id_adh_slot or 'none'}")
                    retirer_slot = cgm3.button("🗑️", key=f"grp_new_del_{i}")
                    nouveaux_membres.append((am_choisie, nb_enf_choisi))
                    if retirer_slot and st.session_state['nb_slots_nouveau_groupe'] > 1:
                        st.session_state['nb_slots_nouveau_groupe'] -= 1
                        st.rerun()

                if st.button("➕ Ajouter une AM au groupe", key="grp_new_add_slot"):
                    st.session_state['nb_slots_nouveau_groupe'] += 1
                    st.rerun()

                if st.button("💾 Créer le groupe", key="grp_new_create", type="primary"):
                    membres_valides = [(a, n) for a, n in nouveaux_membres if a != "Choisir..."]
                    ids_choisis = [dict_adh[a] for a, n in membres_valides]
                    if not nom_nouveau_groupe.strip():
                        st.error("Merci de donner un nom au groupe.")
                    elif not membres_valides:
                        st.error("Ajoutez au moins une assistante maternelle au groupe.")
                    elif len(ids_choisis) != len(set(ids_choisis)):
                        st.error("Une même AM ne peut pas être ajoutée deux fois dans le même groupe.")
                    else:
                        res_g = supabase.table("groupes").insert({"nom": nom_nouveau_groupe.strip()}).execute()
                        nouveau_groupe_id = res_g.data[0]['id']
                        lignes_membres = [{"groupe_id": nouveau_groupe_id, "adherent_id": dict_adh[a], "nb_enfants": n} for a, n in membres_valides]
                        supabase.table("groupe_membres").insert(lignes_membres).execute()
                        enregistrer_log("Admin", "Création groupe", f"Groupe '{nom_nouveau_groupe.strip()}' créé avec {len(lignes_membres)} AM")
                        # Prépare la réinitialisation du formulaire (nom du groupe + AM vides) pour le prochain rerun
                        st.session_state['nb_slots_a_nettoyer'] = st.session_state['nb_slots_nouveau_groupe']
                        st.session_state['reset_form_nouveau_groupe'] = True
                        st.session_state['nb_slots_nouveau_groupe'] = 1
                        load_groupes.clear()
                        st.success("Groupe créé avec succès !")
                        st.rerun()

            st.markdown("---")
            st.markdown("**Groupes existants**")

            groupes_existants = load_groupes()
            if not groupes_existants:
                st.info("Aucun groupe créé pour le moment.")

            for g in groupes_existants:
                if st.session_state['groupe_en_edition'] == g['id']:
                    # --- Formulaire d'édition inline ---
                    st.markdown(f"**✏️ Modification du groupe « {g['nom']} »**")
                    nouveau_nom_g = st.text_input("Nom du groupe", value=st.session_state['edition_nom_groupe'], key=f"edit_nom_{g['id']}")

                    membres_edit = st.session_state['edition_membres_groupe']
                    for m in membres_edit:
                        m.setdefault('nb_version', 0)

                    st.caption("Le nombre d'enfants de chaque AM est repris depuis le groupe. Vous pouvez le réinitialiser à la valeur par défaut de l'AM (définie dans 👥 Liste AM) si besoin — cette réinitialisation ne concerne que ce groupe et n'a aucune incidence sur les ateliers ni sur les inscriptions déjà enregistrées.")
                    if st.button("🔄 Réinitialiser tous les enfants selon les valeurs par défaut des AM", key=f"edit_reset_all_{g['id']}"):
                        for m in membres_edit:
                            if m['est_actif'] and m['am'] != "Choisir...":
                                aid = dict_adh.get(m['am'])
                                if aid is not None:
                                    m['nb_enfants'] = dict_adh_defaut.get(aid, 1)
                                    m['nb_version'] += 1
                        st.rerun()

                    idx_a_supprimer = None
                    for idx, m in enumerate(membres_edit):
                        cme1, cme2, cme3, cme4 = st.columns([2, 1, 0.3, 0.3])
                        if m['est_actif']:
                            options_am = ["Choisir..."] + liste_adh
                            valeur_defaut = m['am'] if m['am'] in options_am else "Choisir..."
                            am_val = cme1.selectbox("AM", options_am, index=options_am.index(valeur_defaut), key=f"edit_am_{g['id']}_{idx}", label_visibility="collapsed")
                        else:
                            cme1.markdown(f"🚫 {m['am']} *(AM désactivée)*")
                            am_val = m['am']
                        if am_val != "Choisir..." and am_val != m['am']:
                            # L'AM de ce slot vient de changer : on repart de son nombre d'enfants par défaut
                            default_nb_membre = dict_adh_defaut.get(dict_adh.get(am_val), 1)
                        else:
                            default_nb_membre = int(m['nb_enfants'])
                        nb_val = cme2.number_input("Enfants", 1, 10, default_nb_membre, key=f"edit_nb_{g['id']}_{idx}_{am_val}_{m['nb_version']}", label_visibility="collapsed")
                        if am_val != "Choisir..." and cme3.button("↻", key=f"edit_reset_one_{g['id']}_{idx}", help="Réinitialiser à la valeur par défaut de cette AM"):
                            aid = dict_adh.get(am_val)
                            if aid is not None:
                                membres_edit[idx]['am'] = am_val
                                membres_edit[idx]['nb_enfants'] = dict_adh_defaut.get(aid, 1)
                                membres_edit[idx]['nb_version'] += 1
                                st.rerun()
                        if cme4.button("🗑️", key=f"edit_rm_{g['id']}_{idx}"):
                            idx_a_supprimer = idx
                        membres_edit[idx]['am'] = am_val
                        membres_edit[idx]['nb_enfants'] = nb_val
                    if idx_a_supprimer is not None:
                        membres_edit.pop(idx_a_supprimer)
                        st.rerun()

                    if st.button("➕ Ajouter une AM", key=f"edit_add_{g['id']}"):
                        membres_edit.append({"adherent_id": None, "am": "Choisir...", "nb_enfants": 1, "est_actif": True, "nb_version": 0})
                        st.rerun()

                    cbtn1, cbtn2 = st.columns(2)
                    if cbtn1.button("💾 Enregistrer", key=f"edit_save_{g['id']}", type="primary"):
                        lignes, ids_vus, doublon = [], set(), False
                        for m in membres_edit:
                            if m['est_actif']:
                                if m['am'] == "Choisir...":
                                    continue
                                aid = dict_adh.get(m['am'])
                            else:
                                aid = m['adherent_id']
                            if aid is None:
                                continue
                            if aid in ids_vus:
                                doublon = True
                                break
                            ids_vus.add(aid)
                            lignes.append({"groupe_id": g['id'], "adherent_id": aid, "nb_enfants": int(m['nb_enfants'])})
                        if doublon:
                            st.error("Une même AM ne peut pas être ajoutée deux fois dans le même groupe.")
                        elif not nouveau_nom_g.strip() or not lignes:
                            st.error("Nom et au moins une AM sont requis.")
                        else:
                            supabase.table("groupes").update({"nom": nouveau_nom_g.strip()}).eq("id", g['id']).execute()
                            supabase.table("groupe_membres").delete().eq("groupe_id", g['id']).execute()
                            supabase.table("groupe_membres").insert(lignes).execute()
                            enregistrer_log("Admin", "Modification groupe", f"Groupe '{nouveau_nom_g.strip()}' modifié ({len(lignes)} AM)")
                            st.session_state['groupe_en_edition'] = None
                            load_groupes.clear()
                            st.success("Groupe modifié avec succès !")
                            st.rerun()
                    if cbtn2.button("Annuler", key=f"edit_cancel_{g['id']}"):
                        st.session_state['groupe_en_edition'] = None
                        st.rerun()
                    st.markdown("---")
                else:
                    # --- Affichage normal de la carte du groupe ---
                    cg1, cg2, cg3 = st.columns([0.7, 0.15, 0.15])
                    noms_membres = ", ".join(
                        f"{m['prenom']} {m['nom']} ({m['nb_enfants']} enf.)" + ("" if m['est_actif'] else " 🚫")
                        for m in g['membres']
                    )
                    cg1.markdown(f"**🧺 {g['nom']}** — {len(g['membres'])} AM  \n<span style='color:#666;font-size:0.9rem;'>{noms_membres}</span>", unsafe_allow_html=True)
                    if cg2.button("✏️ Modifier", key=f"grp_edit_{g['id']}"):
                        st.session_state['groupe_en_edition'] = g['id']
                        st.session_state['edition_nom_groupe'] = g['nom']
                        st.session_state['edition_membres_groupe'] = [
                            {"adherent_id": m['adherent_id'], "am": f"{m['prenom']} {m['nom']}", "nb_enfants": m['nb_enfants'], "est_actif": m['est_actif']}
                            for m in g['membres']
                        ]
                        st.rerun()
                    if cg3.button("🗑️ Supprimer", key=f"grp_del_{g['id']}"):
                        delete_groupe_dialog(g['id'], g['nom'])

        with t8: # 📍 LIEUX / HORAIRES
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

        with t9: # ⚙️ SÉCURITÉ
            with st.form("sec_form"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code or o == "0000":
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        get_secret_code.clear()
                        st.rerun()
                    else: st.error("Ancien code incorrect")
            if st.button("🚪 Déconnexion Super Admin"): st.session_state['super_access'] = False; st.rerun()

        with t10: # 📜 JOURNAL DES ACTIONS
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
                    # Conversion du fuseau horaire pour l'affichage
                    logs_df['created_at'] = pd.to_datetime(logs_df['created_at'], utc=True).dt.tz_convert("Europe/Paris").dt.strftime('%d/%m/%Y %H:%M')
                    # Nettoyage de la colonne 'details' : suppression du suffixe [date/heure]
                    logs_df['details'] = logs_df['details'].str.replace(r'\s*\[.*?\]$', '', regex=True)
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
