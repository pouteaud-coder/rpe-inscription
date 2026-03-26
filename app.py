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

# STYLE CSS (CONSERVÉ)
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
    parts = clean.split(" ")
    if len(parts) < 4: return date_str
    d, m_str, y = parts[1], parts[2].lower(), parts[3]
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    try: m = months.index(m_str) + 1
    except: m = 1
    return f"{y}-{m:02d}-{int(d):02d}"

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
    st.write(f"Voulez-vous vraiment rendre inactif : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer"):
        if pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Statut mis à jour"); st.rerun()
        else: st.error("Code incorrect")

@st.dialog("⚠️ Suppression Atelier")
def delete_atelier_dialog(at_id, label, has_ins, current_code):
    st.error(f"Suppression définitive de : {label}")
    if has_ins: st.warning("Attention : Cet atelier contient des réservations qui seront supprimées.")
    pw = st.text_input("Code secret", type="password")
    if st.button("Supprimer définitivement", type="primary"):
        if pw == current_code:
            if has_ins: supabase.table("inscriptions").delete().eq("atelier_id", at_id).execute()
            supabase.table("ateliers").delete().eq("id", at_id).execute()
            st.rerun()
        else: st.error("Code incorrect")

@st.dialog("⚠️ Confirmer la désinscription")
def confirm_unsubscribe_dialog(ins_id, nom_complet):
    st.warning(f"Annuler la réservation de **{nom_complet}** ?")
    if st.button("Confirmer la désinscription", type="primary"):
        supabase.table("inscriptions").delete().eq("id", ins_id).execute(); st.rerun()

# --- INITIALISATION DATA ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS (VALIDÉE)
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions")
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    if user_principal != "Choisir...":
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            rest = at['capacite_max'] - total
            statut = f"✅ {rest} pl. libres" if rest > 0 else "🚨 COMPLET"
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | {statut}"):
                for i in res_ins.data:
                    c1, c2 = st.columns([0.88, 0.12])
                    n = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    c1.write(f"• {n} ({i['nb_enfants']} enf.)")
                    if c2.button("🗑️", key=f"del_{i['id']}"): confirm_unsubscribe_dialog(i['id'], n)
                st.markdown("---")
                c_q, c_e, c_v = st.columns([2, 1, 1])
                qui = c_q.selectbox("Assistante Maternelle", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                nb = c_e.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                if c_v.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_a = dict_adh[qui]
                        exist = next((ins for ins in res_ins.data if ins['adherent_id'] == id_a), None)
                        diff = (nb - exist['nb_enfants']) if exist else (1 + nb)
                        if rest - diff < 0: st.error("Plus de places")
                        else:
                            if exist: supabase.table("inscriptions").update({"nb_enfants": nb}).eq("id", exist['id']).execute()
                            else: supabase.table("inscriptions").insert({"adherent_id": id_a, "atelier_id": at['id'], "nb_enfants": nb}).execute()
                            st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP (VALIDÉE)
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    with t1:
        choix = st.multiselect("Filtrer par AM :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        if data.data:
            df = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Atelier": i['ateliers']['titre'], "Enfants": i['nb_enfants']} for i in data.data])
            c1, c2 = st.columns(2)
            c1.download_button("📥 Excel", export_to_excel(df), "suivi.xlsx")
            c2.download_button("📥 PDF", export_to_pdf("Suivi AM", [f"{r['AM']} - {r['Date']} - {r['Atelier']}" for r in df.to_dict('records')]), "suivi.pdf")
            curr = ""
            for i in data.data:
                nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom != curr: st.subheader(nom); curr = nom
                st.write(f"{format_date_fr_complete(i['ateliers']['date_atelier'])} — {i['ateliers']['titre']} ({i['nb_enfants']} enf.)")
    with t2:
        c1, c2 = st.columns(2); d_s = c1.date_input("Du", date.today()); d_e = c2.date_input("Au", date.today()+timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_s)).lte("date_atelier", str(d_e)).order("date_atelier").execute()
        for a in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} ({len(ins.data)} AM)")

# ==========================================
# SECTION 🔐 ADMINISTRATION (MISE À JOUR)
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t1, t2, t3, t4 = st.tabs(["🏗️ Ateliers", "👥 Assistantes Maternelles", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t1: # ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_names = [l['nom'] for l in l_raw]; h_names = [h['libelle'] for h in h_raw]
            l_caps = {l['nom']: l['capacite_accueil'] for l in l_raw}
            l_ids = {l['nom']: l['id'] for l in l_raw}; h_ids = {h['libelle']: h['id'] for h in h_raw}

            sub = st.radio("Mode", ["Générateur", "Répertoire", "Actions groupées"], horizontal=True)
            
            if sub == "Générateur":
                c1, c2 = st.columns(2)
                d1 = c1.date_input("Début", date.today())
                d2 = c2.date_input("Fin", d1 + timedelta(days=7))
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer les lignes"):
                    tmp, curr = [], d1
                    while curr <= d2:
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        if js_fr[curr.weekday()] in jours:
                            loc = l_names[0] if l_names else ""
                            tmp.append({"Date": format_date_fr_complete(curr, False), "Titre": "", "Lieu": loc, "Horaire": h_names[0] if h_names else "", "Capacité": l_caps.get(loc, 10), "Actif": True})
                        curr += timedelta(days=1)
                    st.session_state['gen_ateliers'] = tmp

                if 'gen_ateliers' in st.session_state:
                    edited_df = st.data_editor(pd.DataFrame(st.session_state['gen_ateliers']), num_rows="dynamic", column_config={
                        "Lieu": st.column_config.SelectboxColumn(options=l_names, required=True),
                        "Horaire": st.column_config.SelectboxColumn(options=h_names, required=True),
                        "Actif": st.column_config.CheckboxColumn(default=True)
                    }, use_container_width=True)
                    
                    if st.button("💾 Enregistrer tous les ateliers"):
                        to_ins = []
                        for _, r in edited_df.iterrows():
                            if r['Actif'] and not str(r['Titre']).strip():
                                st.error(f"Titre obligatoire pour l'atelier du {r['Date']}"); st.stop()
                            to_ins.append({
                                "date_atelier": parse_date_fr_to_iso(r['Date']),
                                "titre": r['Titre'], "lieu_id": l_ids[r['Lieu']], "horaire_id": h_ids[r['Horaire']],
                                "capacite_max": int(r['Capacité']), "est_actif": bool(r['Actif'])
                            })
                        if to_ins: supabase.table("ateliers").insert(to_ins).execute()
                        st.session_state['gen_ateliers'] = []; st.rerun()

            elif sub == "Répertoire":
                c1, c2, c3 = st.columns(3)
                f_s, f_e = c1.date_input("Du", date.today()-timedelta(days=60)), c2.date_input("Au", date.today()+timedelta(days=60))
                f_t = c3.selectbox("Statut", ["Tous", "Actifs", "Inactifs"])
                q = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(f_s)).lte("date_atelier", str(f_e)).order("date_atelier")
                if f_t == "Actifs": q = q.eq("est_actif", True)
                elif f_t == "Inactifs": q = q.eq("est_actif", False)
                for a in q.execute().data:
                    col1, col2 = st.columns([0.85, 0.15])
                    col1.write(f"{'🟢' if a['est_actif'] else '🔴'} **{format_date_fr_complete(a['date_atelier'])}** - {a['titre']}")
                    if col2.button("🗑️", key=f"at_del_{a['id']}"):
                        cnt = supabase.table("inscriptions").select("id", count="exact").eq("atelier_id", a['id']).execute().count
                        delete_atelier_dialog(a['id'], a['titre'], cnt > 0, current_code)

            elif sub == "Actions groupées":
                with st.form("bulk"):
                    b_s, b_e = st.date_input("Début"), st.date_input("Fin")
                    act = st.radio("Action", ["Activer", "Désactiver"], horizontal=True)
                    if st.form_submit_button("Appliquer"):
                        supabase.table("ateliers").update({"est_actif": (act=="Activer")}).gte("date_atelier", str(b_s)).lte("date_atelier", str(b_e)).execute()
                        st.rerun()

        with t2: # ASSISTANTES MATERNELLES
            with st.form("add_am"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nom").upper()
                pre = c2.text_input("Prénom").title()
                if st.form_submit_button("Ajouter l'Assistante Maternelle"):
                    if nom and pre: supabase.table("adherents").insert({"nom": nom, "prenom": pre, "est_actif": True}).execute(); st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([0.85, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"am_del_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t3: # LIEUX / HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    c_a, c_b = st.columns([0.8, 0.2]); c_a.write(l['nom'])
                    if c_b.button("🗑️", key=f"lx_del_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("add_lx"):
                    nl, cp = st.text_input("Nouveau Lieu"), st.number_input("Capacité", 1, 50, 10)
                    if st.form_submit_button("Ajouter Lieu"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp, "est_actif": True}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    c_c, c_d = st.columns([0.8, 0.2]); c_c.write(h['libelle'])
                    if c_d.button("🗑️", key=f"hx_del_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("add_hx"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter Horaire"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()

        with t4: # SÉCURITÉ
            with st.form("f_sec"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code: supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute(); st.rerun()
                    else: st.error("Ancien code incorrect")
    else: st.info("Saisissez le code secret.")
