import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="RPE Connect", layout="wide", initial_sidebar_state="collapsed")

# Design Doux (Dégradé Vert/Bleu)
st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #f5fcf9 0%, #e1f5fe 100%); }
    .stButton>button { border-radius: 12px; transition: 0.3s; }
    .atelier-card { background: white; padding: 20px; border-radius: 15px; border-left: 5px solid #4CAF50; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); margin-bottom: 15px; }
    @media print { .no-print { display: none !important; } .stApp { background: white !important; } }
    </style>
    """, unsafe_allow_html=True)

# Connexion Supabase
@st.cache_resource
def init_connection():
    return create_client(st.secrets["supabase_url"], st.secrets["supabase_key"])

supabase = init_connection()

# --- FONCTIONS DE DONNÉES ---
def get_ateliers_actifs():
    return supabase.table("ateliers").select("*, lieux(nom, capacite_standard), horaires(libelle)").eq("est_actif", True).order("date_atelier").execute().data

def get_inscriptions_details(atelier_id):
    return supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", atelier_id).execute().data

# --- INTERFACE ---
st.title("🌿 RPE Connect")
tabs = st.tabs(["📅 Planning & Inscriptions", "🔍 Vue Globale & Impression", "⚙️ Administration"])

# IDENTIFICATION
membres = supabase.table("adherents").select("*").eq("est_actif", True).execute().data
noms_map = {f"{m['nom']} {m['prenom']}": m['id'] for m in membres}

with st.sidebar:
    st.markdown("### Connexion")
    user_label = st.selectbox("Qui êtes-vous ?", ["Choisir..."] + list(noms_map.keys()))

if user_label == "Choisir...":
    st.info("Veuillez sélectionner votre nom dans la barre latérale pour continuer.")
    st.stop()

user_id = noms_map[user_label]

# --- ONGLET 1 : PLANNING ---
with tabs[0]:
    ateliers = get_ateliers_actifs()
    for atl in ateliers:
        inscrits = get_inscriptions_details(atl['id'])
        total_presents = sum(i['total_participants'] for i in inscrits)
        capa_max = atl['capacite_reelle'] or atl['lieux']['capacite_standard']
        places_libres = capa_max - total_presents
        
        st.markdown(f"""<div class="atelier-card">
            <h4>{atl['titre']}</h4>
            <p>📅 {atl['date_atelier']} | ⏰ {atl['horaires']['libelle']} | 📍 {atl['lieux']['nom']}</p>
        </div>""", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([2, 1, 1])
        color = "green" if places_libres > 3 else "orange" if places_libres > 0 else "red"
        c1.markdown(f"**Places :** :{color}[{places_libres} / {capa_max}]")
        
        if places_libres > 0:
            with c2.popover("S'inscrire"):
                nb_e = st.select_slider("Nb enfants :", options=[1, 2, 3, 4], key=f"s_{atl['id']}")
                if st.button("Confirmer", key=f"reg_{atl['id']}"):
                    supabase.table("inscriptions").insert({
                        "atelier_id": atl['id'], "adherent_id": user_id, 
                        "nb_enfants": nb_e, "total_participants": nb_e + 1, "inscrit_par_nom": user_label
                    }).execute()
                    st.rerun()
        
        with st.expander("Voir les collègues inscrites"):
            for ins in inscrits:
                col_n, col_d = st.columns([4, 1])
                col_n.write(f"• {ins['adherents']['nom']} {ins['adherents']['prenom']} (+{ins['nb_enfants']})")
                if col_d.button("Retirer", key=f"del_{ins['id']}"):
                    supabase.table("inscriptions").delete().eq("id", ins['id']).execute()
                    st.rerun()

# --- ONGLET 2 : VUE GLOBALE & IMPRESSION ---
with tabs[1]:
    mode = st.radio("Type de vue :", ["Par Atelier (Liste d'émargement)", "Par Assistante Maternelle (Planning)"], horizontal=True)
    
    if mode == "Par Atelier (Liste d'émargement)":
        ateliers_list = get_ateliers_actifs()
        for a in ateliers_list:
            presents = get_inscriptions_details(a['id'])
            st.markdown(f"### {a['date_atelier']} - {a['titre']}")
            if presents:
                df = pd.DataFrame([{"Nom": f"{p['adherents']['nom']} {p['adherents']['prenom']}", "Enfants": p['nb_enfants']} for p in presents])
                st.table(df)
    
    else:
        selected_ams = st.multiselect("Choisir les AM :", list(noms_map.keys()))
        if selected_ams:
            ids = [noms_map[name] for name in selected_ams]
            resas = supabase.table("inscriptions").select("*, ateliers(*), adherents(*)").in_("adherent_id", ids).execute().data
            data = [{"AM": f"{r['adherents']['nom']} {r['adherents']['prenom']}", "Date": r['ateliers']['date_atelier'], "Atelier": r['ateliers']['titre']} for r in resas if r['ateliers']['est_actif']]
            if data:
                st.table(pd.DataFrame(data))

    if st.button("🖨️ Préparer l'impression (Papier ou PDF)"):
        st.components.v1.html("<script>window.print();</script>", height=0)

# --- ONGLET 3 : ADMIN ---
# --- SECTION ADMINISTRATION ---
if menu == "Administration":
    st.header("🔐 Espace Administration")
    
    # Barre latérale pour le code
    password = st.sidebar.text_input("Code d'accès", type="password")
    
    if password == "1234":
        st.success("Accès autorisé")
        
        # Onglets pour organiser les formulaires
        tab1, tab2, tab3 = st.tabs(["🏗️ Créer un Atelier", "👥 Gérer les Adhérents", "📍 Lieux & Horaires"])
        
        with tab1:
            st.subheader("Nouvel Atelier")
            with st.form("form_atelier"):
                titre = st.text_input("Nom de l'atelier (ex: Éveil Musical)")
                date_at = st.date_input("Date de l'atelier")
                
                # Récupération dynamique des lieux et horaires depuis la base
                lieux_df = supabase.table("lieux").select("*").execute()
                horaires_df = supabase.table("horaires").select("*").execute()
                
                lieu_options = {l['nom']: l['id'] for l in lieux_df.data}
                horaire_options = {h['libelle']: h['id'] for h in horaires_df.data}
                
                choix_lieu = st.selectbox("Lieu", options=list(lieu_options.keys()))
                choix_horaire = st.selectbox("Horaire", options=list(horaire_options.keys()))
                
                if st.form_submit_button("Publier l'atelier"):
                    supabase.table("ateliers").insert({
                        "titre": titre, 
                        "date_atelier": str(date_at),
                        "lieu_id": lieu_options[choix_lieu],
                        "horaire_id": horaire_options[choix_horaire],
                        "est_actif": True
                    }).execute()
                    st.balloons()
                    st.success("Atelier créé !")

        with tab2:
            st.subheader("Ajouter une assistante maternelle")
            with st.form("form_adherent"):
                nouveau_nom = st.text_input("Nom de famille")
                nouveau_prenom = st.text_input("Prénom")
                if st.form_submit_button("Ajouter à la liste"):
                    supabase.table("adherents").insert({
                        "nom": nouveau_nom.upper(), 
                        "prenom": nouveau_prenom.capitalize(),
                        "est_actif": True
                    }).execute()
                    st.success(f"{nouveau_prenom} a été ajouté(e).")

        with tab3:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Ajouter un Lieu")
                nouveau_lieu = st.text_input("Nom du lieu (ex: Maison des Associations)")
                if st.button("Ajouter le Lieu"):
                    supabase.table("lieux").insert({"nom": nouveau_lieu}).execute()
                    st.success(f"{nouveau_lieu} a été ajouté.")
            with col2:
                st.subheader("Ajouter un Horaire")
                nouvel_horaire = st.text_input("Créneau (ex: 9h30 - 11h30)")
                if st.button("Ajouter l'Horaire"):
                    supabase.table("horaires").insert({"libelle": nouvel_horaire}).execute()
                    st.success(f"{nouvel_horaire} a été ajouté.")

    else:
        st.warning("⚠️ Accès sécurisé : Veuillez entrer le code d'accès dans la barre latérale pour afficher les formulaires.")
