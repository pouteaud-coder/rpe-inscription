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

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    if isinstance(date_obj, str):
        try: date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except: return date_obj
    res = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{res}**" if gras else res

def parse_date_fr_to_iso(date_str):
    clean = date_str.replace("**", "").strip()
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
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def export_to_pdf(title, data_list):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, title, ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    for line in data_list:
        # Encodage latin-1 pour FPDF standard (évite les erreurs sur les caractères spéciaux)
        pdf.multi_cell(0, 10, txt=line.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# --- DIALOGUES ---
@st.dialog("⚠️ Confirmation")
def secure_delete_dialog(table, item_id, label, current_code):
    st.write(f"Voulez-vous vraiment désactiver/supprimer : **{label}** ?")
    pw = st.text_input("Code secret admin", type="password")
    if st.button("Confirmer", type="primary"):
        if pw == current_code:
            supabase.table(table).update({"est_actif": False}).eq("id", item_id).execute()
            st.success("Opération réussie"); st.rerun()
        else: st.error("Code incorrect")

@st.dialog("⚠️ Confirmer la désinscription")
def confirm_unsubscribe_dialog(ins_id, nom_complet):
    st.warning(f"Souhaitez-vous vraiment annuler la réservation de **{nom_complet}** ?")
    c1, c2 = st.columns(2)
    if c1.button("Oui, désinscrire", type="primary"):
        supabase.table("inscriptions").delete().eq("id", ins_id).execute(); st.rerun()
    if c2.button("Non, conserver"): st.rerun()

# --- CHARGEMENT DES DONNÉES GLOBALES ---
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
    user_principal = st.selectbox("👤 Vous êtes :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        for at in res_at.data:
            res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
            total_occ = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            date_f = format_date_fr_complete(at['date_atelier'], gras=True)
            titre_label = f"{date_f} — {at['titre']}\n📍 {at['lieux']['nom']} | ⏰ {at['horaires']['libelle']} | {statut_p}"
            
            with st.expander(titre_label):
                if res_ins.data:
                    for i in res_ins.data:
                        c_nom, c_poub = st.columns([0.88, 0.12])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_nom.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_poub.button("🗑️", key=f"del_{i['id']}"): confirm_unsubscribe_dialog(i['id'], n_f)
                
                st.markdown("---")
                try: idx_def = (liste_adh.index(user_principal) + 1)
                except: idx_def = 0
                c1, c2, c3 = st.columns([2, 1, 1])
                qui = c1.selectbox("Qui ?", ["Choisir..."] + liste_adh, index=idx_def, key=f"q_{at['id']}")
                nb_e = c2.number_input("Enfants", 1, 10, 1, key=f"e_{at['id']}")
                
                if c3.button("Valider", key=f"v_{at['id']}", type="primary"):
                    if qui != "Choisir...":
                        id_adh = dict_adh[qui]
                        existing = next((ins for ins in res_ins.data if ins['adherent_id'] == id_adh), None)
                        if existing:
                            diff = nb_e - existing['nb_enfants']
                            if restantes - diff < 0: st.error(f"Manque de places ({restantes} restantes)")
                            else: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute(); st.rerun()
                        else:
                            if restantes - (1 + nb_e) < 0: st.error(f"Manque de places ({restantes} restantes)")
                            else: supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute(); st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation")
    t1, t2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    
    with t1:
        choix = st.multiselect("Filtrer par assistante maternelle :", liste_adh)
        ids = [dict_adh[n] for n in choix] if choix else list(dict_adh.values())
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        
        if data.data:
            # Préparation des données pour l'export
            df_export = pd.DataFrame([{
                "Assistante Maternelle": f"{i['adherents']['prenom']} {i['adherents']['nom']}",
                "Date": i['ateliers']['date_atelier'],
                "Atelier": i['ateliers']['titre'],
                "Lieu": i['ateliers']['lieux']['nom'],
                "Nb Enfants": i['nb_enfants']
            } for i in data.data])

            c_btn1, c_btn2 = st.columns(2)
            c_btn1.download_button("📥 Excel - Assistantes", data=export_to_excel(df_export), file_name="suivi_am.xlsx")
            
            pdf_data = [f"{row['Assistante Maternelle']} - {row['Date']} - {row['Atelier']} ({row['Nb Enfants']} enf.)" for _, row in df_export.iterrows()]
            c_btn2.download_button("📥 PDF - Assistantes", data=export_to_pdf("Recapitulatif par Assistante Maternelle", pdf_data), file_name="suivi_am.pdf")

            curr_u = ""
            for i in data.data:
                nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom_u != curr_u:
                    st.markdown(f'<div style="color:#1b5e20; border-bottom:2px solid #1b5e20; padding-top:15px; margin-bottom:8px; font-weight:bold; font-size:1.2rem;">{nom_u}</div>', unsafe_allow_html=True)
                    curr_u = nom_u
                at = i['ateliers']
                c_l = get_color(at['lieux']['nom'])
                st.write(f"{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> <span class='horaire-text'>({at['horaires']['libelle']})</span> **({i['nb_enfants']} enf.)**", unsafe_allow_html=True)

    with t2:
        c_d1, c_d2 = st.columns(2)
        d_start = c_d1.date_input("Du", date.today(), format="DD/MM/YYYY")
        d_end = c_d2.date_input("Au", d_start + timedelta(days=30), format="DD/MM/YYYY")
        
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end)).order("date_atelier").execute()
        
        if ats_raw.data:
            # Préparation des données pour l'export planning
            planning_data = []
            for a in ats_raw.data:
                ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                for p in ins_at.data:
                    planning_data.append({
                        "Date": a['date_atelier'],
                        "Atelier": a['titre'],
                        "Lieu": a['lieux']['nom'],
                        "AM": f"{p['adherents']['prenom']} {p['adherents']['nom']}",
                        "Enfants": p['nb_enfants']
                    })
            
            if planning_data:
                df_plan = pd.DataFrame(planning_data)
                c_btn3, c_btn4 = st.columns(2)
                c_btn3.download_button("📥 Excel - Planning", data=export_to_excel(df_plan), file_name="planning_RPE.xlsx")
                
                pdf_plan = [f"{r['Date']} | {r['Atelier']} | {r['AM']} ({r['Enfants']} enf.)" for r in planning_data]
                c_btn4.download_button("📥 PDF - Planning", data=export_to_pdf("Planning des Ateliers", pdf_plan), file_name="planning_RPE.pdf")

            for index, a in enumerate(ats_raw.data):
                c_l = get_color(a['lieux']['nom'])
                ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                t_ad, t_en = len(ins_at.data), sum([p['nb_enfants'] for p in ins_at.data])
                restantes = a['capacite_max'] - (t_ad + t_en)
                classe_complet = "alerte-complet" if restantes <= 0 else ""
                
                st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> | <span class='horaire-text'>{a['horaires']['libelle']}</span> <span class='compteur-badge'>👤 {t_ad} AM</span> <span class='compteur-badge'>👶 {t_en} enf.</span> <span class='compteur-badge {classe_complet}'>🏁 {restantes} pl.</span>", unsafe_allow_html=True)
                
                if not ins_at.data: st.markdown("<div class='container-inscrits'><span style='font-size:0.85rem; margin-left:20px; color:gray;'>Aucun inscrit</span></div>", unsafe_allow_html=True)
                else:
                    ins_sorted = sorted(ins_at.data, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                    html = "<div class='container-inscrits'>"
                    for p in ins_sorted: html += f'<span class="liste-inscrits">• {p["adherents"]["prenom"]} {p["adherents"]["nom"]} <span class="nb-enfants-focus">({p["nb_enfants"]} enfants)</span></span>'
                    st.markdown(html + "</div>", unsafe_allow_html=True)
                if index < len(ats_raw.data) - 1: st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)

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
            map_l_cap = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}; map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            sub = st.radio("Mode", ["Générateur", "Répertoire", "Actions groupées"], horizontal=True)
            
            if sub == "Générateur":
                c1, c2 = st.columns(2)
                d1 = c1.date_input("Début", date.today(), format="DD/MM/YYYY")
                d2 = c2.date_input("Fin", date.today() + timedelta(days=7), format="DD/MM/YYYY")
                jours = st.multiselect("Jours", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer les lignes"):
                    tmp, curr = [], d1
                    while curr <= d2:
                        js_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
                        if js_fr[curr.weekday()] in jours:
                            loc = l_list[0] if l_list else ""
                            tmp.append({
                                "Date": format_date_fr_complete(curr, False), 
                                "Titre": "", 
                                "Lieu": loc, 
                                "Horaire": h_list[0] if h_list else "", 
                                "Capacité": map_l_cap.get(loc, 10), 
                                "Actif": True
                            })
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = tmp

                if 'at_list_gen' in st.session_state and st.session_state['at_list_gen']:
                    # Utilisation d'un DataFrame pour l'éditeur
                    df_ed = st.data_editor(
                        pd.DataFrame(st.session_state['at_list_gen']), 
                        num_rows="dynamic", 
                        column_config={
                            "Lieu": st.column_config.SelectboxColumn(options=l_list, required=True),
                            "Horaire": st.column_config.SelectboxColumn(options=h_list, required=True),
                            "Actif": st.column_config.CheckboxColumn(default=True)
                        }, 
                        use_container_width=True,
                        key="editor_ateliers"
                    )
                    
                    if st.button("💾 Enregistrer les ateliers"):
                        to_db = []
                        for _, r in df_ed.iterrows():
                            # Ajustement dynamique de la capacité si non modifiée manuellement
                            cap_finale = r['Capacité']
                            if r['Lieu'] in map_l_cap and r['Capacité'] == 10: 
                                cap_finale = map_l_cap[r['Lieu']]

                            if r['Actif'] and not str(r['Titre']).strip():
                                st.error(f"Titre obligatoire pour le {r['Date']}"); st.stop()
                            
                            to_db.append({
                                "date_atelier": parse_date_fr_to_iso(r['Date']),
                                "titre": r['Titre'], 
                                "lieu_id": map_l_id[r['Lieu']], 
                                "horaire_id": map_h_id[r['Horaire']],
                                "capacite_max": int(cap_finale), 
                                "est_actif": bool(r['Actif'])
                            })
                        if to_db: 
                            supabase.table("ateliers").insert(to_db).execute()
                            st.success(f"{len(to_db)} ateliers enregistrés.")
                            st.session_state['at_list_gen'] = []
                            st.rerun()

            elif sub == "Répertoire":
                cf1, cf2, cf3 = st.columns(3)
                fs = cf1.date_input("Du", date.today()-timedelta(days=60), format="DD/MM/YYYY")
                fe = cf2.date_input("Au", date.today()+timedelta(days=60), format="DD/MM/YYYY")
                ft = cf3.selectbox("Statut", ["Tous", "Actifs", "Inactifs"])
                rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(fs)).lte("date_atelier", str(fe)).order("date_atelier").execute().data
                for a in rep:
                    if ft == "Actifs" and not a['est_actif']: continue
                    if ft == "Inactifs" and a['est_actif']: continue
                    c_a, c_b = st.columns([0.85, 0.15])
                    c_a.write(f"{'🟢' if a['est_actif'] else '🔴'} **{format_date_fr_complete(a['date_atelier'])}** | {a['horaires']['libelle']} | {a['titre']} ({a['lieux']['nom']})")
                    if c_b.button("🗑️", key=f"at_del_{a['id']}"):
                        cnt = supabase.table("inscriptions").select("id", count="exact").eq("atelier_id", a['id']).execute().count
                        delete_atelier_dialog(a['id'], a['titre'], cnt > 0, current_code)

            elif sub == "Actions groupées":
                with st.form("bulk_form"):
                    bs = st.date_input("Début", format="DD/MM/YYYY")
                    be = st.date_input("Fin", format="DD/MM/YYYY")
                    action = st.radio("Action", ["Activer", "Désactiver"], horizontal=True)
                    if st.form_submit_button("Appliquer"):
                        supabase.table("ateliers").update({"est_actif": (action=="Activer")}).gte("date_atelier", str(bs)).lte("date_atelier", str(be)).execute()
                        st.rerun()

        with t2: # ASSISTANTES MATERNELLES
            with st.form("add_am"):
                c1, c2 = st.columns(2)
                nom = c1.text_input("Nom").upper().strip()
                pre = " ".join([w.capitalize() for w in c2.text_input("Prénom").split()]).strip()
                if st.form_submit_button("➕ Ajouter l'Assistante Maternelle"):
                    if nom and pre: 
                        supabase.table("adherents").insert({"nom": nom, "prenom": pre, "est_actif": True}).execute()
                        st.rerun()
            for u in res_adh.data:
                c1, c2 = st.columns([0.85, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("🗑️", key=f"am_del_{u['id']}"): secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t3: # LIEUX / HORAIRES
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("Lieux")
                for l in l_raw:
                    ca, cb = st.columns([0.8, 0.2])
                    ca.markdown(f"<span class='lieu-badge' style='background-color:{get_color(l['nom'])}'>{l['nom']} (Cap: {l['capacite_accueil']})</span>", unsafe_allow_html=True)
                    if cb.button("🗑️", key=f"lx_del_{l['id']}"): secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("add_lx"):
                    nl, cp = st.text_input("Nouveau Lieu"), st.number_input("Capacité", 1, 50, 10)
                    if st.form_submit_button("Ajouter Lieux"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": cp, "est_actif": True}).execute(); st.rerun()
            with cl2:
                st.subheader("Horaires")
                for h in h_raw:
                    cc, cd = st.columns([0.8, 0.2]); cc.write(f"• {h['libelle']}")
                    if cd.button("🗑️", key=f"hx_del_{h['id']}"): secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("add_hx"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter Horaire"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute(); st.rerun()

        with t4: # SÉCURITÉ
            with st.form("sec_form"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code: 
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code mis à jour"); st.rerun()
                    else: st.error("Ancien code incorrect")
    else: st.info("Saisissez le code secret.")
