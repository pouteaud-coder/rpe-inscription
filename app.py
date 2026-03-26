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
    clean = str(date_str).replace("**", "").strip()
    # Format attendu : "Lundi 26 mars 2026"
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
        df.to_excel(writer, index=False)
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
    st.write(f"Voulez-vous vraiment désactiver : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer la désactivation", type="primary"):
        if pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Désactivé avec succès"); st.rerun()
        else: st.error("Code incorrect")

@st.dialog("⚠️ Suppression Atelier")
def delete_atelier_dialog(at_id, label, has_inscriptions, current_code):
    st.error(f"Suppression définitive de : {label}")
    if has_inscriptions:
        st.warning("❗ Cet atelier contient des réservations. Elles seront également supprimées.")
    pw = st.text_input("Code secret pour suppression", type="password")
    if st.button("Confirmer la suppression", type="primary"):
        if pw == current_code:
            if has_inscriptions:
                supabase.table("inscriptions").delete().eq("atelier_id", at_id).execute()
            supabase.table("ateliers").delete().eq("id", at_id).execute()
            st.success("Atelier supprimé"); st.rerun()
        else: st.error("Code incorrect")

@st.dialog("⚠️ Confirmer la désinscription")
def confirm_unsubscribe_dialog(ins_id, nom_complet):
    st.warning(f"Annuler la réservation de **{nom_complet}** ?")
    c1, c2 = st.columns(2)
    if c1.button("Oui", type="primary"):
        supabase.table("inscriptions").delete().eq("id", ins_id).execute(); st.rerun()
    if c2.button("Non"): st.rerun()

# --- DATA ---
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
    user_principal = st.selectbox("👤 Assistante Maternelle :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            statut = f"✅ {restantes} pl." if restantes > 0 else "🚨 COMPLET"
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | {statut}"):
                for i in res_ins.data:
                    c_n, c_d = st.columns([0.85, 0.15])
                    n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    c_n.write(f"• {n_f} ({i['nb_enfants']} enf.)")
                    if c_d.button("🗑️", key=f"del_{i['id']}"): confirm_unsubscribe_dialog(i['id'], n_f)
                
                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("AM", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_adh = dict_adh[qui]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_adh), None)
                        diff = (nb_e - existing['nb_enfants']) if existing else (1 + nb_e)
                        if restantes - diff < 0: st.error("Plus de places disponibles")
                        else:
                            if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                            else: supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                            st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    with t1:
        choix = st.multiselect("Filtrer par Assistante Maternelle :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        if data.data:
            df = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Titre": i['ateliers']['titre'], "Enfants": i['nb_enfants']} for i in data.data])
            st.download_button("Excel", export_to_excel(df), "recap_am.xlsx")
            curr = ""
            for i in data.data:
                nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom != curr: st.subheader(nom); curr = nom
                st.write(f"{format_date_fr_complete(i['ateliers']['date_atelier'])} - {i['ateliers']['titre']} ({i['nb_enfants']} enf.)")
    with t2:
        d_s, d_e = st.columns(2); start = d_s.date_input("Du", date.today()); end = d_e.date_input("Au", date.today()+timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(start)).lte("date_atelier", str(end)).order("date_atelier").execute()
        for a in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            t_am, t_en = len(ins.data), sum([p['nb_enfants'] for p in ins.data])
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} ({t_am} AM, {t_en} enf.)")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Assistantes Maternelles", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1: # ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]; h_list = [h['libelle'] for h in h_raw]
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_l_cap = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire", "Actions groupées"], horizontal=True)
            
            if sub == "Générateur":
                c_g1, c_g2 = st.columns(2)
                d_deb = c_g1.date_input("Date début", date.today())
                d_fin = c_g2.date_input("Date fin", d_deb + timedelta(days=7))
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer les lignes"):
                    tmp, curr = [], d_deb
                    js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    while curr <= d_fin:
                        if js_fr[curr.weekday()] in jours:
                            l_def = l_list[0] if l_list else ""
                            tmp.append({
                                "Date": format_date_fr_complete(curr, gras=False),
                                "Titre": "",
                                "Lieu": l_def,
                                "Horaire": h_list[0] if h_list else "",
                                "Capacité": map_l_cap.get(l_def, 10),
                                "Actif": True
                            })
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = tmp
                
                if 'at_list' in st.session_state and st.session_state['at_list']:
                    df_gen = pd.DataFrame(st.session_state['at_list'])
                    res_ed = st.data_editor(df_gen, num_rows="dynamic", use_container_width=True, column_config={
                        "Lieu": st.column_config.SelectboxColumn(options=l_list, required=True),
                        "Horaire": st.column_config.SelectboxColumn(options=h_list, required=True),
                        "Date": st.column_config.TextColumn("Date (format français)", required=True),
                        "Actif": st.column_config.CheckboxColumn(default=True)
                    })
                    
                    if st.button("✅ Enregistrer les ateliers"):
                        to_db = []
                        for _, r in res_ed.iterrows():
                            if r['Actif'] and not str(r['Titre']).strip():
                                st.error(f"Le titre est obligatoire pour l'atelier du {r['Date']}"); st.stop()
                            to_db.append({
                                "date_atelier": parse_date_fr_to_iso(r['Date']),
                                "titre": r['Titre'],
                                "lieu_id": map_l_id[r['Lieu']],
                                "horaire_id": map_h_id[r['Horaire']],
                                "capacite_max": int(r['Capacité']),
                                "est_actif": bool(r['Actif'])
                            })
                        if to_db: supabase.table("ateliers").insert(to_db).execute()
                        st.session_state['at_list'] = []; st.rerun()

            elif sub == "Répertoire":
                c_f1, c_f2, c_f3 = st.columns(3)
                f_deb = c_f1.date_input("Du", date.today() - timedelta(days=60))
                f_fin = c_f2.date_input("Au", date.today() + timedelta(days=60))
                f_statut = c_f3.selectbox("Statut", ["Tous", "Actifs", "Inactifs"])
                
                query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(f_deb)).lte("date_atelier", str(f_fin)).order("date_atelier")
                if f_statut == "Actifs": query = query.eq("est_actif", True)
                elif f_statut == "Inactifs": query = query.eq("est_actif", False)
                rep = query.execute().data
                
                for a in rep:
                    c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
                    status_icon = "🟢" if a['est_actif'] else "🔴"
                    c1.write(f"{status_icon} **{format_date_fr_complete(a['date_atelier'])}** - {a['titre']} ({a['lieux']['nom']})")
                    if c2.button("Modifier", key=f"mod_{a['id']}"): st.info("Utilisez l'éditeur global ci-dessous")
                    if c3.button("🗑️", key=f"sup_{a['id']}"):
                        ins_count = supabase.table("inscriptions").select("id", count="exact").eq("atelier_id", a['id']).execute()
                        delete_atelier_dialog(a['id'], a['titre'], (ins_count.count > 0), current_code)

            elif sub == "Actions groupées":
                with st.form("bulk_action"):
                    st.write("Activer/Désactiver une plage de dates")
                    b_deb = st.date_input("Début")
                    b_fin = st.date_input("Fin")
                    action = st.radio("Action", ["Activer", "Désactiver"], horizontal=True)
                    if st.form_submit_button("Appliquer"):
                        val = True if action == "Activer" else False
                        supabase.table("ateliers").update({"est_actif": val}).gte("date_atelier", str(b_deb)).lte("date_atelier", str(b_fin)).execute()
                        st.success("Mise à jour effectuée"); st.rerun()

        with t2: # ASSISTANTES MATERNELLES
            with st.form("add_am"):
                c_n, c_p = st.columns(2)
                nom = c_n.text_input("Nom de l'Assistante Maternelle").upper()
                prenom = c_p.text_input("Prénom").title()
                if st.form_submit_button("Ajouter l'AM"):
                    if nom and prenom:
                        supabase.table("adherents").insert({"nom": nom, "prenom": prenom, "est_actif": True}).execute()
                        st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([0.85, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"am_{u['id']}"):
                    secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t3: # LIEUX / HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    ca, cb = st.columns([0.8, 0.2]); ca.write(l['nom'])
                    if cb.button("🗑️", key=f"lx_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("f_l"):
                    nl = st.text_input("Nouveau lieu")
                    cap = st.number_input("Capacité par défaut", 1, 50, 10)
                    if st.form_submit_button("Ajouter Lieu"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cap, "est_actif": True}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    cc, cd = st.columns([0.8, 0.2]); cc.write(h['libelle'])
                    if cd.button("🗑️", key=f"hx_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("f_h"):
                    nh = st.text_input("Nouvel horaire")
                    if st.form_submit_button("Ajouter Horaire"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()

        with t4: # SÉCURITÉ
            with st.form("f_sec"):
                o = st.text_input("Ancien code", type="password")
                n = st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code mis à jour"); st.rerun()
                    else: st.error("Ancien code incorrect")
    else: st.info("Veuillez saisir le code secret administration.")
