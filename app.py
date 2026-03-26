import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from supabase import create_client, Client
import re
import hashlib
import io

# 1. Configuration de la page
st.set_page_config(page_title="RPE Connect", page_icon="🌿", layout="wide")

# --- SYSTÈME DE COULEURS DYNAMIQUES PAR LIEU ---
def get_color(nom_lieu):
    hash_object = hashlib.md5(str(nom_lieu).upper().strip().encode())
    hex_hash = hash_object.hexdigest()
    return f"#{hex_hash[:6]}"

# --- STYLE CSS AMÉLIORÉ ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.05rem !important; }
    
    .lieu-badge { padding: 3px 10px; border-radius: 6px; color: white; font-weight: bold; font-size: 0.85rem; display: inline-block; margin: 2px 0; }
    .horaire-text { font-size: 0.9rem; color: #666; font-weight: 400; }
    
    /* Badges de compteurs avec alertes de seuil */
    .compteur-badge { 
        font-size: 0.85rem; 
        font-weight: 600; 
        padding: 2px 8px; 
        border-radius: 4px; 
        background-color: #f0f2f6; 
        color: #31333F;
        border: 1px solid #ddd;
        margin-left: 5px;
    }
    .alerte-orange { background-color: #fff3e0 !important; color: #ef6c00 !important; border-color: #ffe0b2 !important; }
    .alerte-rouge { background-color: #d32f2f !important; color: white !important; border-color: #b71c1c !important; }

    .separateur-atelier { border: 0; border-top: 1px solid #eee; margin: 15px 0; }
    
    .container-inscrits { margin-top: -8px; padding-top: 0; margin-bottom: 5px; }
    .liste-inscrits { 
        font-size: 0.95rem !important; 
        color: #555;
        margin-left: 20px;
        display: block; 
        line-height: 1.1;
    }
    .nb-enfants-focus { color: #2e7d32; font-weight: 600; }
    .stButton button { border-radius: 8px !important; }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

# --- FONCTIONS UTILITAIRES ---
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
    date_str = str(date_str).lower().replace("**", "").strip()
    mois_map = {"janvier":"01", "février":"02", "mars":"03", "avril":"04", "mai":"05", "juin":"06", "juillet":"07", "août":"08", "septembre":"09", "octobre":"10", "novembre":"11", "décembre":"12"}
    match = re.search(r"(\d{1,2})\s+([a-zéû.]+)\s+(\d{4})", date_str)
    if match:
        d, m, y = match.groups()
        return f"{y}-{mois_map.get(m, '01')}-{d.zfill(2)}"
    return str(date.today())

# --- INITIALISATION DES DONNÉES ---
current_code = get_secret_code()
res_adh = supabase.table("adherents").select("*").eq("est_actif", True).order("nom").order("prenom").execute()
dict_adh = {f"{a['prenom']} {a['nom']}": a['id'] for a in res_adh.data}
liste_adh = list(dict_adh.keys())

res_lieux = supabase.table("lieux").select("*").eq("est_actif", True).order("nom").execute()
liste_lieux = [l['nom'] for l in res_lieux.data]

# --- NAVIGATION ---
st.title("🌿 Système RPE Connect")
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
            total_occ = sum([(1 + i['nb_enfants']) for i in res_ins.data])
            restantes = at['capacite_max'] - total_occ
            
            statut_p = f"✅ {restantes} pl. libres" if restantes > 0 else "🚨 COMPLET"
            date_f = format_date_fr_complete(at['date_atelier'], gras=True)
            titre_label = f"{date_f} — {at['titre']} | {at['lieux']['nom']} | {statut_p}"
            
            with st.expander(titre_label):
                if res_ins.data:
                    ins_sorted = sorted(res_ins.data, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                    for i in ins_sorted:
                        c_nom, c_poub = st.columns([0.88, 0.12])
                        n_f = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                        c_nom.write(f"• {n_f} **({i['nb_enfants']} enf.)**")
                        if c_poub.button("🗑️", key=f"del_{i['id']}"):
                            supabase.table("inscriptions").delete().eq("id", i['id']).execute()
                            st.rerun()
                
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
                        diff = (1 + nb_e) - (1 + existing['nb_enfants'] if existing else 0)
                        
                        if restantes - diff < 0:
                            st.error(f"Plus que {restantes} places.")
                        else:
                            if existing: supabase.table("inscriptions").update({"nb_enfants": nb_e}).eq("id", existing['id']).execute()
                            else: supabase.table("inscriptions").insert({"adherent_id": id_adh, "atelier_id": at['id'], "nb_enfants": nb_e}).execute()
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
        data = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids).eq("ateliers.est_actif", True).order("adherent_id").execute()
        curr_u = ""
        for i in data.data:
            nom_u = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
            if nom_u != curr_u:
                st.markdown(f'<div style="color:#1b5e20; border-bottom:2px solid #1b5e20; padding-top:15px; margin-bottom:8px; font-weight:bold; font-size:1.2rem;">{nom_u}</div>', unsafe_allow_html=True)
                curr_u = nom_u
            at = i['ateliers']
            c_l = get_color(at['lieux']['nom'])
            st.write(f"{format_date_fr_complete(at['date_atelier'], gras=True)} — {at['titre']} <span class='lieu-badge' style='background-color:{c_l}'>{at['lieux']['nom']}</span> **({i['nb_enfants']} enf.)**", unsafe_allow_html=True)

    with t2:
        # FILTRES AVANCÉS
        c_f1, c_f2, c_f3 = st.columns([1, 1, 1])
        d_start = c_f1.date_input("Du", date.today(), format="DD/MM/YYYY")
        d_end = c_f2.date_input("Au", d_start + timedelta(days=30), format="DD/MM/YYYY")
        f_lieu = c_f3.multiselect("Lieu(x)", liste_lieux)
        
        # Requête avec filtre Lieu optionnel
        query = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(d_start)).lte("date_atelier", str(d_end))
        if f_lieu:
            # On récupère les IDs des lieux filtrés
            ids_l = [l['id'] for l in res_lieux.data if l['nom'] in f_lieu]
            query = query.in_("lieu_id", ids_l)
        
        ats_raw = query.order("date_atelier").execute()
        
        # Préparation de l'export Excel
        export_data = []
            
        for index, a in enumerate(ats_raw.data):
            c_l = get_color(a['lieux']['nom'])
            ins_at = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
            
            t_ad = len(ins_at.data); t_en = sum([p['nb_enfants'] for p in ins_at.data])
            t_occ = t_ad + t_en; rest = a['capacite_max'] - t_occ
            
            # Gestion visuelle des alertes
            classe_alerte = ""
            if rest <= 0: classe_alerte = "alerte-rouge"
            elif rest <= 3: classe_alerte = "alerte-orange"
            
            st.markdown(f"""
                **{format_date_fr_complete(a['date_atelier'])}** | <span class='lieu-badge' style='background-color:{c_l}'>{a['lieux']['nom']}</span> | <span class='horaire-text'>{a['horaires']['libelle']}</span>
                <span class='compteur-badge'>👤 {t_ad}</span> <span class='compteur-badge'>👶 {t_en}</span>
                <span class='compteur-badge {classe_alerte}'>🏁 {rest} pl. libres</span>
            """, unsafe_allow_html=True)
            
            if not ins_at.data: 
                st.markdown("<div class='container-inscrits'><span style='font-size:0.85rem; margin-left:20px; color:gray;'>Aucun inscrit</span></div>", unsafe_allow_html=True)
            else:
                ins_sorted = sorted(ins_at.data, key=lambda x: (x['adherents']['nom'], x['adherents']['prenom']))
                html_inscrits = "<div class='container-inscrits'>"
                for p in ins_sorted:
                    n_full = f"{p['adherents']['prenom']} {p['adherents']['nom']}"
                    html_inscrits += f'<span class="liste-inscrits">• {n_full} <span class="nb-enfants-focus">({p["nb_enfants"]} enfants)</span></span>'
                    export_data.append({"Date": a['date_atelier'], "Atelier": a['titre'], "Lieu": a['lieux']['nom'], "Adhérent": n_full, "Enfants": p['nb_enfants']})
                html_inscrits += "</div>"
                st.markdown(html_inscrits, unsafe_allow_html=True)
            
            if index < len(ats_raw.data) - 1: st.markdown('<hr class="separateur-atelier">', unsafe_allow_html=True)

        # BOUTON EXPORT
        if export_data:
            st.write("---")
            df_export = pd.DataFrame(export_data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Inscriptions')
            st.download_button(label="📥 Télécharger le récapitulatif (Excel)", data=output.getvalue(), file_name=f"RPE_Recap_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==========================================
# SECTION 🔐 ADMINISTRATION (Identique)
# ==========================================
elif menu == "🔐 Administration":
    # Le code de l'administration reste tel quel pour la gestion des données sources.
    pass
