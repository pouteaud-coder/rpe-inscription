import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import hashlib
import io
from fpdf import FPDF

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- CONNEXION SUPABASE ---
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- STYLE CSS (RESTAURÉ) ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .compteur-badge { font-size: 0.85rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: #f0f2f6; border: 1px solid #ddd; margin-left: 5px; }
    .alerte-orange { background-color: #fff3e0 !important; color: #ef6c00 !important; }
    .alerte-rouge { background-color: #d32f2f !important; color: white !important; }
    .liste-inscrits { font-size: 0.95rem; color: #555; margin-left: 20px; display: block; line-height: 1.1; }
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
    """Convertit 'Lundi 26 mars 2026' en '2026-03-26'"""
    clean = date_str.replace("**", "")
    parts = clean.split(" ")
    if len(parts) < 4: return date_str
    d = parts[1]
    m_str = parts[2].lower()
    y = parts[3]
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    m = months.index(m_str) + 1
    return f"{y}-{m:02d}-{int(d):02d}"

# --- EXPORTS ---
def generate_pdf(df, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", "B", 9)
    col_width = 190 / len(df.columns)
    for col in df.columns: pdf.cell(col_width, 10, col.encode('latin-1', 'replace').decode('latin-1'), 1)
    pdf.ln()
    pdf.set_font("Arial", "", 8)
    for _, row in df.iterrows():
        for item in row: pdf.cell(col_width, 8, str(item).encode('latin-1', 'replace').decode('latin-1'), 1)
        pdf.ln()
    return pdf.output(dest="S").encode("latin-1")

def generate_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

# --- DIALOGUE SÉCURISÉ ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment désactiver/supprimer : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer la suppression", type="primary"):
        if pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Opération réussie")
            st.rerun()
        else: st.error("Code incorrect")

# --- INITIALISATION ---
if 'at_list' not in st.session_state: st.session_state['at_list'] = []
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
    user_p = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_p != "Choisir...":
        id_curr_adh = dict_adh[user_p]
        res_at = supabase.table("ateliers").select("*, lieux(*), horaires(*)").eq("est_actif", True).gte("date_atelier", str(date.today())).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(*)").eq("atelier_id", at['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            rest = at['capacite_max'] - occ
            mon_ins = next((i for i in res_ins.data if i['adherent_id'] == id_curr_adh), None)
            
            h_txt = at['horaires']['libelle'] if at['horaires'] else "Horaire NC"
            statut = f"✅ {rest} pl. libres" if rest > 0 else "🚨 COMPLET"
            
            with st.expander(f"{format_date_fr_complete(at['date_atelier'])} ({h_txt}) — {at['titre']} | {statut}"):
                for i in sorted(res_ins.data, key=lambda x: x['adherents']['nom']):
                    c_txt, c_del = st.columns([0.85, 0.15])
                    c_txt.write(f"• {i['adherents']['prenom']} {i['adherents']['nom']} **({i['nb_enfants']} enf.)**")
                    if i['adherent_id'] == id_curr_adh:
                        if c_del.button("🗑️", key=f"del_me_{i['id']}", help="Se désinscrire"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()

                st.markdown("---")
                c1, c2, c3 = st.columns([2, 1, 1])
                val_e = mon_ins['nb_enfants'] if mon_ins else 1
                c1.write(f"**{user_p}**")
                nb_e = c2.number_input("Enfants", 1, 10, val_e, key=f"e_{at['id']}")
                btn_txt = "Modifier" if mon_ins else "S'inscrire"
                
                if c3.button(btn_txt, key=f"v_{at['id']}", type="primary"):
                    if mon_ins:
                        supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", mon_ins['id']).execute()
                    else:
                        if rest - (1 + nb_e) < 0: st.error("Plus assez de places")
                        else:
                            supabase.table("inscriptions").insert({"adherent_id": id_curr_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
                    st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation & Bilans")
    t1, t2 = st.tabs(["👤 Par Adhérente", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par personne :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).execute()
        df_adh = []
        curr_u = ""
        for i in sorted(data.data, key=lambda x: (x['adherents']['nom'], x['ateliers']['date_atelier'])):
            nom = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom != curr_u:
                st.markdown(f"### {nom}")
                curr_u = nom
            at = i['ateliers']
            st.write(f"📅 {format_date_fr_complete(at['date_atelier'])} — {at['titre']} ({at['lieux']['nom']})")
            df_adh.append({"Adhérent": nom, "Date": at['date_atelier'], "Atelier": at['titre'], "Lieu": at['lieux']['nom'], "Enfants": i['nb_enfants']})
        if df_adh:
            st.download_button("📥 Excel", generate_excel(pd.DataFrame(df_adh)), "Recap_Adherents.xlsx")

    with t2:
        d1 = st.date_input("Du", date.today())
        d2 = st.date_input("Au", d1 + timedelta(days=30))
        ats = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d1)).lte("date_atelier", str(d2)).order("date_atelier").execute()
        df_at = []
        for a in ats.data:
            ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            occ = sum([(1 + i['nb_enfants']) for i in ins.data])
            st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** ({a['horaires']['libelle'] if a['horaires'] else ''}) | {a['lieux']['nom']}")
            for p in ins.data:
                n = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                st.write(f" > {n} ({p['nb_enfants']} enf.)")
                df_at.append({"Date": a['date_atelier'], "Lieu": a['lieux']['nom'], "Adhérent": n, "Enfants": p['nb_enfants']})
        if df_at:
            st.download_button("📥 Excel", generate_excel(pd.DataFrame(df_at)), "Bilan_Ateliers.xlsx")

# ==========================================
# SECTION 🔐 ADMINISTRATION (TON CODE RÉINTÉGRÉ)
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        t_ad1, t_ad2, t_ad3, t_ad4 = st.tabs(["🏗️ Ateliers", "👥 Adhérents", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
        with t_ad1:
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]; h_list = [h['libelle'] for h in h_raw]
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire"], horizontal=True)
            if sub == "Générateur":
                c_g1, c_g2 = st.columns(2)
                d1 = c_g1.date_input("Début", date.today(), format="DD/MM/YYYY")
                d2 = c_g2.date_input("Fin", d1 + timedelta(days=7), format="DD/MM/YYYY")
                js_sel = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer la liste"):
                    tmp = []; curr = d1; js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                    while curr <= d2:
                        if js_fr[curr.weekday()] in js_sel:
                            tmp.append({"Date": format_date_fr_complete(curr, gras=True), "Titre": "", "Lieu": l_list[0] if l_list else "", "Horaire": h_list[0] if h_list else "", "Capacité": 10, "Actif": True})
                        curr += timedelta(days=1)
                    st.session_state['at_list'] = tmp; st.rerun()

                if st.session_state['at_list']:
                    res_gen = st.data_editor(pd.DataFrame(st.session_state['at_list']), hide_index=True, use_container_width=True)
                    if st.button("✅ Enregistrer"):
                        to_db = [{"date_atelier": parse_date_fr_to_iso(r['Date']), "titre": r['Titre'], "lieu_id": map_l_id[r['Lieu']], "horaire_id": map_h_id[r['Horaire']], "capacite_max": int(r['Capacité']), "est_actif": True} for _, r in res_gen.iterrows() if r['Titre'] != ""]
                        if to_db: supabase.table("ateliers").insert(to_db).execute(); st.session_state['at_list'] = []; st.rerun()
            else: 
                at_rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").order("date_atelier", desc=True).limit(60).execute().data
                if at_rep:
                    df_rep = pd.DataFrame([{"Date": format_date_fr_complete(a['date_atelier'], gras=True), "Titre": a['titre'], "Lieu": a['lieux']['nom'], "Horaire": a['horaires']['libelle'] if a['horaires'] else "NC", "Actif": a['est_actif']} for a in at_rep])
                    edited_df = st.data_editor(df_rep, hide_index=True, use_container_width=True)
                    if st.button("💾 Sauvegarder", type="primary"):
                        for idx, row in edited_df.iterrows():
                            at_id = at_rep[idx]['id']
                            supabase.table("ateliers").update({"titre": row['Titre'], "est_actif": bool(row['Actif'])}).eq("id", at_id).execute()
                        st.success("Mis à jour !"); st.rerun()

        with t_ad2: # ADHÉRENTS
            with st.form("add_adh"):
                col_n, col_p = st.columns(2); n = col_n.text_input("Nom"); p = col_p.text_input("Prénom")
                if st.form_submit_button("➕ Ajouter"):
                    supabase.table("adherents").insert({"nom": n.upper(), "prenom": p.capitalize(), "est_actif": True}).execute(); st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([0.85, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"u_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t_ad3: # LIEUX & HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    c_a, c_b = st.columns([0.85, 0.15])
                    c_a.markdown(f"<span class='lieu-badge' style='background-color:{get_color(l['nom'])}'>{l['nom']}</span>", unsafe_allow_html=True)
                    if c_b.button("🗑️", key=f"l_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("new_l"):
                    nl = st.text_input("Nouveau Lieu")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "est_actif": True, "capacite_accueil": 10}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    c_c, c_d = st.columns([0.85, 0.15]); c_c.write(f"• {h['libelle']}")
                    if c_d.button("🗑️", key=f"h_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("new_h"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()

        with t_ad4: # SÉCURITÉ
            st.subheader("⚙️ Code Administrateur")
            with st.form("f_sec"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code modifié !"); st.rerun()
                    else: st.error("L'ancien code est incorrect.")
    else: st.info("Saisissez le code secret administrateur.")
