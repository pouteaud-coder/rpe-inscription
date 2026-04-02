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
        if res.data:
            return res.data[0]['secret_code']
        return "1234"
    except:
        return "1234"

def enregistrer_log(utilisateur, action, details):
    try:
        supabase.table("logs").insert({
            "utilisateur": utilisateur,
            "action": action,
            "details": details
        }).execute()
    except:
        pass

def format_date_fr_complete(date_obj, gras=True):
    jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except:
            return date_obj
            
    resultat = f"{jours[date_obj.weekday()]} {date_obj.day} {mois[date_obj.month-1]} {date_obj.year}"
    return f"**{resultat}**" if gras else resultat

def parse_date_fr_to_iso(date_str):
    clean_date = str(date_str).replace("**", "").strip()
    parts = clean_date.split(" ")
    if len(parts) < 4:
        return date_str
    
    jour = parts[1]
    mois_str = parts[2].lower()
    annee = parts[3]
    
    mois_map = {
        "janvier": "01", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
    }
    
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
            st.success("Action effectuée avec succès !")
            st.rerun()
        else:
            st.error("Code secret incorrect.")

@st.dialog("✏️ Modifier une AM")
def edit_am_dialog(am_id, nom_actuel, prenom_actuel):
    new_nom = st.text_input("Nom de famille", value=nom_actuel).upper().strip()
    new_prenom = st.text_input("Prénom", value=prenom_actuel).strip()
    if st.button("Enregistrer les modifications"):
        if new_nom and new_prenom:
            supabase.table("adherents").update({"nom": new_nom, "prenom": new_prenom}).eq("id", am_id).execute()
            st.success("Modifié !")
            st.rerun()

@st.dialog("➕ Gestion forcée (Admin)")
def admin_force_inscription_dialog(at_id, titre, restantes, liste_adh, dict_adh, user_admin="Admin"):
    st.write(f"Gestion des inscriptions pour : **{titre}**")
    
    res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at_id).execute()
    if res_ins.data:
        st.write("Inscriptions actuelles :")
        for i in res_ins.data:
            c1, c2 = st.columns([0.8, 0.2])
            nom_am = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            c1.write(f"• {nom_am} ({i['nb_enfants']} enf.)")
            if c2.button("🗑️", key=f"frc_del_{i['id']}"):
                supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                st.rerun()
    
    st.markdown("---")
    st.write("Ajouter manuellement :")
    c1, c2 = st.columns([0.7, 0.3])
    qui = c1.selectbox("Sélectionner l'AM", ["Choisir..."] + liste_adh, key="frc_qui")
    nb_e = c2.number_input("Enfants", 1, 10, 1, key="frc_nb")
    
    if st.button("Forcer l'inscription", type="primary"):
        if qui != "Choisir...":
            id_adh = dict_adh[qui]
            supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at_id, "nb_enfants": nb_e}).execute()
            st.rerun()

@st.dialog("🔑 Super Administration")
def super_admin_dialog():
    sac = st.text_input("Code Super Admin", type="password")
    if st.button("Débloquer les accès"):
        if sac == "0000":
            st.session_state['super_access'] = True
            st.success("Accès débloqués")
            st.rerun()

# --- INITIALISATION DATA ---
if 'at_list_gen' not in st.session_state:
    st.session_state['at_list_gen'] = []
if 'super_access' not in st.session_state:
    st.session_state['super_access'] = False

current_code = get_secret_code()

res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

# ==========================================
# NAVIGATION
# ==========================================
menu = st.sidebar.radio("Navigation", ["📝 Inscriptions", "📊 Suivi & Récap", "🔐 Administration"])

# ==========================================
# SECTION 📝 INSCRIPTIONS
# ==========================================
if menu == "📝 Inscriptions":
    st.header("📍 Inscriptions aux Ateliers")
    user_principal = st.selectbox("👤 Sélectionnez votre nom :", ["Choisir..."] + liste_adh)
    
    if user_principal != "Choisir...":
        today_str = str(date.today())
        res_at = supabase.table("ateliers").select("*, lieux(nom, capacite_accueil), horaires(libelle)").eq("est_actif", True).gte("date_atelier", today_str).order("date_atelier").execute()
        
        if res_at.data:
            for at in res_at.data:
                # NOUVEAU : Récupération état verrouillé
                est_verrouille = at.get('est_verrouille', False)
                
                res_ins = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", at['id']).execute()
                total_occupants = sum([(1 + (i['nb_enfants'] if i['nb_enfants'] else 0)) for i in res_ins.data])
                restantes = at['capacite_max'] - total_occupants
                
                at_info_log = f"{at['date_atelier']} | {at['horaires']['libelle']} | {at['lieux']['nom']}"
                
                # Mise à jour du libellé selon verrouillage
                status_pl = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
                if est_verrouille:
                    status_pl = "🔒 Réservé Administration"
                
                titre_label = f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} | 📍 {at['lieux']['nom']} | {status_pl}"
                
                with st.expander(titre_label):
                    if est_verrouille:
                        st.warning("⚠️ Les inscriptions pour cet atelier sont gérées uniquement par le RPE.")
                    
                    if res_ins.data:
                        st.markdown("<div class='container-inscrits'>", unsafe_allow_html=True)
                        for i in res_ins.data:
                            c_nom, c_poub = st.columns([0.88, 0.12])
                            nom_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                            c_nom.markdown(f"<span class='liste-inscrits'>• {nom_f} <span class='nb-enfants-focus'>({i['nb_enfants']} enfants)</span></span>", unsafe_allow_html=True)
                            
                            # Suppression bloquée si verrouillé
                            if not est_verrouille:
                                if c_poub.button("🗑️", key=f"del_{i['id']}_{at['id']}"):
                                    enregistrer_log(user_principal, "Désinscription", f"Annulation pour {nom_f} - {at_info_log}")
                                    supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                                    st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.info("Aucune inscription pour le moment.")
                    
                    # Inscription bloquée si verrouillé
                    if not est_verrouille:
                        st.markdown("---")
                        c1, c2, c3 = st.columns([2, 1, 1])
                        qui = c1.selectbox("Qui inscrire ?", ["Choisir..."] + liste_adh, key=f"q_{at['id']}")
                        nb_e = c2.number_input("Nombre d'enfants", 1, 10, 1, key=f"e_{at['id']}")
                        
                        if c3.button("S'inscrire", key=f"btn_{at['id']}", type="primary"):
                            if qui != "Choisir...":
                                if restantes - (1 + nb_e) < 0:
                                    st.error("Désolé, il n'y a plus assez de places.")
                                else:
                                    id_adh = dict_adh[qui]
                                    supabase.table("inscriptions").insert({
                                        "adherent_id": id_adh,
                                        "atelier_id": at['id'],
                                        "nb_enfants": nb_e
                                    }).execute()
                                    enregistrer_log(user_principal, "Inscription", f"{qui} s'est inscrit - {at_info_log}")
                                    st.rerun()

# ==========================================
# SECTION 📊 SUIVI & RÉCAP
# ==========================================
elif menu == "📊 Suivi & Récap":
    st.header("🔎 Consultation des Inscriptions")
    tab1, tab2 = st.tabs(["👤 Par Assistante Maternelle", "📅 Par Atelier"])
    
    with tab1:
        choix_am = st.multiselect("Filtrer par AM :", liste_adh, key="pub_filter_am")
        ids_am = [dict_adh[n] for n in choix_am] if choix_am else list(dict_adh.values())
        
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids_am).eq("ateliers.est_actif", True).order("adherent_id").execute()
        
        if data.data:
            df_export = pd.DataFrame([{
                "AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}",
                "Date": i['ateliers']['date_atelier'],
                "Atelier": i['ateliers']['titre'],
                "Lieu": i['ateliers']['lieux']['nom'],
                "Enfants": i['nb_enfants']
            } for i in data.data])
            st.download_button("📥 Télécharger le suivi en Excel", data=export_to_excel(df_export), file_name="suivi_inscriptions.xlsx")
            
            current_user = ""
            for i in data.data:
                nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                if nom_u != current_user:
                    st.markdown(f"### {nom_u}")
                    current_user = nom_u
                at = i['ateliers']
                c_lieu = get_color(at['lieux']['nom'])
                st.markdown(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} <span class='lieu-badge' style='background-color:{c_lieu}'>{at['lieux']['nom']}</span>", unsafe_allow_html=True)
        else:
            st.info("Aucune inscription trouvée.")

    with tab2:
        c_d1, c_d2 = st.columns(2)
        d_start = c_d1.date_input("Du", date.today())
        d_end = c_d2.date_input("Au", d_start + timedelta(days=30))
        
        ats_raw = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end)).order("date_atelier").execute()
        
        if ats_raw.data:
            for index, a in enumerate(ats_raw.data):
                c_l = get_color(a['lieux']['nom'])
                ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                total_am = len(ins_at.data)
                total_enf = sum([p['nb_enfants'] for p in ins_at.data])
                
                c_head, c_btn = st.columns([0.8, 0.2])
                c_head.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> <span class='compteur-badge'>👤 {total_am} AM</span> <span class='compteur-badge'>👶 {total_enf} enfants</span>", unsafe_allow_html=True)
                
                lignes_pdf = [
                    f"Atelier : {a['titre']}",
                    f"Date : {format_date_fr_complete(a['date_atelier'], False)}",
                    f"Lieu : {a['lieux']['nom']}",
                    f"Horaires : {a['horaires']['libelle']}",
                    "---------------------------------------",
                    f"Total : {total_am} AM et {total_enf} enfants",
                    ""
                ]
                for p in ins_at.data:
                    lignes_pdf.append(f"- {p['adherents']['prenom']} {p['adherents']['nom']} : {p['nb_enfants']} enfants")
                
                c_btn.download_button(f"📄 PDF", data=export_to_pdf(f"Liste_{a['date_atelier']}", lignes_pdf), file_name=f"liste_{a['date_atelier']}.pdf", key=f"pdf_{a['id']}")

# ==========================================
# SECTION 🔐 ADMINISTRATION
# ==========================================
elif menu == "🔐 Administration":
    c_login1, c_login2 = st.columns([0.7, 0.3])
    pw_input = c_login1.text_input("Code secret administrateur", type="password")
    if c_login2.button("🔑 Mode Super Admin"):
        super_admin_dialog()
        
    if pw_input == current_code or st.session_state['super_access']:
        t1, t2, t3, t4, t5, t6, t7, t8 = st.tabs(["🏗️ Gestion Ateliers", "📊 Suivi AM", "📅 Planning Inscriptions", "📈 Statistiques", "👥 Liste AM", "📍 Lieux / Horaires", "⚙️ Sécurité", "📜 Journal"])
        
        with t1: # GESTION ATELIERS
            l_raw = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute().data
            h_raw = supabase.table("horaires").select("*").eq("est_actif", True).execute().data
            l_list = [l['nom'] for l in l_raw]
            h_list = [h['libelle'] for h in h_raw]
            map_l_cap = {l['nom']: l['capacite_accueil'] for l in l_raw}
            map_l_id = {l['nom']: l['id'] for l in l_raw}
            map_h_id = {h['libelle']: h['id'] for h in h_raw}
            
            admin_sub = st.radio("Mode d'administration", ["Générateur d'ateliers", "Répertoire existant"], horizontal=True)
            
            if admin_sub == "Générateur d'ateliers":
                c1, c2 = st.columns(2)
                d_deb = c1.date_input("Date de début", date.today())
                d_fin = c2.date_input("Date de fin", d_deb + timedelta(days=7))
                jours_choisis = st.multiselect("Jours de la semaine", ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"], default=["Lundi", "Jeudi"])
                
                if st.button("📊 Générer la liste"):
                    temp_at = []
                    curr = d_deb
                    while curr <= d_fin:
                        nom_jour = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][curr.weekday()]
                        if nom_jour in jours_choisis:
                            temp_at.append({
                                "Date": format_date_fr_complete(curr, False),
                                "Titre": "",
                                "Lieu": l_list[0] if l_list else "",
                                "Horaire": h_list[0] if h_list else "",
                                "Capacité": map_l_cap.get(l_list[0], 10) if l_list else 10,
                                "Verrouillé": False, # NOUVEAU
                                "Actif": True
                            })
                        curr += timedelta(days=1)
                    st.session_state['at_list_gen'] = temp_at
                
                if st.session_state['at_list_gen']:
                    df_gen = pd.DataFrame(st.session_state['at_list_gen'])
                    df_ed = st.data_editor(df_gen, num_rows="dynamic", column_config={
                        "Lieu": st.column_config.SelectboxColumn(options=l_list, required=True),
                        "Horaire": st.column_config.SelectboxColumn(options=h_list, required=True),
                        "Verrouillé": st.column_config.CheckboxColumn("🔒 Admin") # NOUVEAU
                    }, use_container_width=True)
                    
                    if st.button("💾 Enregistrer tous les ateliers"):
                        to_insert = []
                        for _, row in df_ed.iterrows():
                            to_insert.append({
                                "date_atelier": parse_date_fr_to_iso(row['Date']),
                                "titre": row['Titre'],
                                "lieu_id": map_l_id[row['Lieu']],
                                "horaire_id": map_h_id[row['Horaire']],
                                "capacite_max": int(row['Capacité']),
                                "est_verrouille": bool(row['Verrouillé']), # NOUVEAU
                                "est_actif": bool(row['Actif'])
                            })
                        if to_insert:
                            supabase.table("ateliers").insert(to_insert).execute()
                            st.session_state['at_list_gen'] = []
                            st.success("Ateliers enregistrés avec succès !")
                            st.rerun()

            elif admin_sub == "Répertoire existant":
                cf1, cf2 = st.columns(2)
                f_deb = cf1.date_input("Filtrer du", date.today() - timedelta(days=30))
                f_fin = cf2.date_input("au", f_deb + timedelta(days=60))
                
                rep_at = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(f_deb)).lte("date_atelier", str(f_fin)).order("date_atelier", desc=True).execute().data
                
                if rep_at:
                    for at in rep_at:
                        c1, c2, c3, c4 = st.columns([0.6, 0.1, 0.1, 0.2])
                        c1.write(f"**{format_date_fr_complete(at['date_atelier'])}** | {at['titre']} ({at['lieux']['nom']})")
                        
                        # NOUVEAU : Bouton Verrouillage
                        v_ico = "🔒" if at.get('est_verrouille', False) else "🔓"
                        if c2.button(v_ico, key=f"v_at_{at['id']}", help="Verrouiller/Déverrouiller l'accès public"):
                            supabase.table("ateliers").update({"est_verrouille": not at.get('est_verrouille', False)}).eq("id", at['id']).execute()
                            st.rerun()
                        
                        # Bouton Actif/Inactif
                        st_ico = "🟢" if at['est_actif'] else "🔴"
                        if c3.button(st_ico, key=f"st_at_{at['id']}"):
                            supabase.table("ateliers").update({"est_actif": not at['est_actif']}).eq("id", at['id']).execute()
                            st.rerun()
                        
                        if c4.button("🗑️ Supprimer", key=f"del_at_{at['id']}"):
                            secure_delete_dialog("ateliers", at['id'], at['titre'], current_code)

        with t2: # SUIVI AM (Identique v10)
            choix_am_adm = st.multiselect("Filtrer par Assistante Maternelle :", liste_adh, key="adm_filter_am")
            ids_am_adm = [dict_adh[n] for n in choix_am_adm] if choix_am_adm else list(dict_adh.values())
            
            data_adm = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids_am_adm).eq("ateliers.est_actif", True).order("adherent_id").execute()
            
            if data_adm.data:
                current_user = ""
                for i in data_adm.data:
                    nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    if nom_u != current_user:
                        st.markdown(f"### {nom_u}")
                        current_user = nom_u
                    at = i['ateliers']
                    c_lieu = get_color(at['lieux']['nom'])
                    st.markdown(f"{format_date_fr_complete(at['date_atelier'])} — {at['titre']} <span class='lieu-badge' style='background-color:{c_lieu}'>{at['lieux']['nom']}</span> **({i['nb_enfants']} enfants)**", unsafe_allow_html=True)

        with t3: # PLANNING INSCRIPTIONS (Identique v10)
            st.subheader("📅 Gestion des inscriptions par Atelier")
            c1p, c2p = st.columns(2)
            d_p_s = c1p.date_input("Du", date.today(), key="p_s")
            d_p_e = c2p.date_input("Au", d_p_s + timedelta(days=30), key="p_e")
            
            ats_p = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_p_s)).lte("date_atelier", str(d_p_e)).order("date_atelier").execute()
            
            if ats_p.data:
                for a in ats_p.data:
                    c_l = get_color(a['lieux']['nom'])
                    ins_p = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                    total_am = len(ins_p.data)
                    total_enf = sum([p['nb_enfants'] for p in ins_p.data])
                    rest = a['capacite_max'] - (total_am + total_enf)
                    
                    st.markdown(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> <span class='compteur-badge'>👤 {total_am} AM</span> <span class='compteur-badge'>👶 {total_enf} enf.</span>", unsafe_allow_html=True)
                    
                    if st.button(f"➕ Gérer / Inscrire : {a['titre']}", key=f"btn_adm_ins_{a['id']}"):
                        admin_force_inscription_dialog(a['id'], a['titre'], rest, liste_adh, dict_adh)
                    
                    if ins_p.data:
                        for p in ins_p.data:
                            st.markdown(f"<span class='liste-inscrits'>• {p['adherents']['prenom']} {p['adherents']['nom']} ({p['nb_enfants']} enfants)</span>", unsafe_allow_html=True)
                    st.markdown("---")

        with t4: # STATISTIQUES (Identique v10)
            st.subheader("📈 Participation par AM")
            cs1, cs2 = st.columns(2)
            d_st_1 = cs1.date_input("Début période", date.today().replace(day=1))
            d_st_2 = cs2.date_input("Fin période", date.today())
            
            stats_in = supabase.table("inscriptions").select("*, adherents(nom, prenom), ateliers!inner(date_atelier)").gte("ateliers.date_atelier", str(d_st_1)).lte("ateliers.date_atelier", str(d_st_2)).execute()
            
            if stats_in.data:
                res_st = []
                for n in liste_adh:
                    count = sum(1 for x in stats_in.data if f"{x['adherents']['prenom']} {x['adherents']['nom']}" == n)
                    res_st.append({"Assistante Maternelle": n, "Nombre d'ateliers": count})
                st.table(pd.DataFrame(res_st).sort_values("Nombre d'ateliers", ascending=False))

        with t5: # LISTE AM (Identique v10)
            st.subheader("👥 Gestion des Assistantes Maternelles")
            with st.form("add_am_form"):
                c1, c2 = st.columns(2)
                n_am = c1.text_input("Nom de famille").upper().strip()
                p_am = c2.text_input("Prénom").strip()
                if st.form_submit_button("➕ Ajouter l'AM"):
                    if n_am and p_am:
                        supabase.table("adherents").insert({"nom": n_am, "prenom": p_am, "est_actif": True}).execute()
                        st.success("AM ajoutée avec succès !")
                        st.rerun()
            
            for u in res_adh.data:
                c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                if c2.button("✏️", key=f"ed_am_{u['id']}"):
                    edit_am_dialog(u['id'], u['nom'], u['prenom'])
                if c3.button("🗑️", key=f"dl_am_{u['id']}"):
                    secure_delete_dialog("adherents", u['id'], u['nom'], current_code)

        with t6: # LIEUX / HORAIRES (Identique v10)
            cl1, cl2 = st.columns(2)
            with cl1:
                st.subheader("📍 Lieux")
                for l in l_raw:
                    ca, cb = st.columns([0.8, 0.2])
                    ca.write(f"• {l['nom']} (Cap: {l['capacite_accueil']})")
                    if cb.button("🗑️", key=f"lx_{l['id']}"):
                        secure_delete_dialog("lieux", l['id'], l['nom'], current_code)
                with st.form("add_lx"):
                    nl, nc = st.text_input("Nouveau Lieu"), st.number_input("Capacité", 1, 50, 10)
                    if st.form_submit_button("Ajouter"):
                        supabase.table("lieux").insert({"nom": nl, "capacite_accueil": nc, "est_actif": True}).execute()
                        st.rerun()
            with cl2:
                st.subheader("📅 Horaires")
                for h in h_raw:
                    cc, cd = st.columns([0.8, 0.2])
                    cc.write(f"• {h['libelle']}")
                    if cd.button("🗑️", key=f"hx_{h['id']}"):
                        secure_delete_dialog("horaires", h['id'], h['libelle'], current_code)
                with st.form("add_hx"):
                    nh = st.text_input("Nouvel Horaire")
                    if st.form_submit_button("Ajouter"):
                        supabase.table("horaires").insert({"libelle": nh, "est_actif": True}).execute()
                        st.rerun()

        with t7: # SÉCURITÉ (Identique v10)
            st.subheader("⚙️ Paramètres de sécurité")
            with st.form("sec_form"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code:
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code modifié avec succès !")
                        st.rerun()
            if st.button("🚪 Déconnexion Super Admin"):
                st.session_state['super_access'] = False
                st.rerun()

        with t8: # JOURNAL (Identique v10)
            st.subheader("📜 Journal des actions")
            cj1, cj2 = st.columns(2)
            dj_s = cj1.date_input("Depuis le", date.today() - timedelta(days=7), format="DD/MM/YYYY", key="log_d1")
            dj_e = cj2.date_input("Jusqu'au", date.today(), format="DD/MM/YYYY", key="log_d2")
            
            start_date = dj_s.strftime("%Y-%m-%d") + "T00:00:00"
            end_date = dj_e.strftime("%Y-%m-%d") + "T23:59:59"
            
            try:
                res_logs = supabase.table("logs").select("*").gte("created_at", start_date).lte("created_at", end_date).order("created_at", desc=True).execute()
                if res_logs.data:
                    logs_df = pd.DataFrame(res_logs.data)
                    logs_df['created_at'] = pd.to_datetime(logs_df['created_at']).dt.strftime('%d/%m/%Y %H:%M')
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
                st.error(f"Erreur lors du chargement du journal.")

    else:
        st.info("Veuillez saisir le code secret administrateur pour accéder à cette section.")
