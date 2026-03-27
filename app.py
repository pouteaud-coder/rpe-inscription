# ==========================================
# SECTION 🔐 ADMINISTRATION (MODIFIÉE)
# ==========================================
elif menu == "🔐 Administration":
    pw = st.text_input("Code secret", type="password")
    if pw == current_code:
        # MISE À JOUR : Ajout des onglets Suivi et Récap
        t1, t2, t3, t4, t5, t6 = st.tabs(["🏗️ Ateliers", "👥 Assistantes Maternelles", "📊 Suivi AM", "📅 Planning Ateliers", "📍 Lieux/Horaires", "⚙️ Sécurité"])
        
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

                if st.session_state['at_list_gen']:
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
                ft = cf3.selectbox("Statut Filtre", ["Tous", "Actifs", "Inactifs"])
                rep = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").gte("date_atelier", str(fs)).lte("date_atelier", str(fe)).order("date_atelier").execute().data
                for a in rep:
                    if ft == "Actifs" and not a['est_actif']: continue
                    if ft == "Inactifs" and a['est_actif']: continue
                    c_a, c_stat, c_b = st.columns([0.7, 0.15, 0.15])
                    c_a.write(f"**{format_date_fr_complete(a['date_atelier'])}** | {a['horaires']['libelle']} | {a['titre']} ({a['lieux']['nom']})")
                    
                    # NOUVEAUTÉ : Bouton pour changer le statut actif/inactif
                    btn_label = "🔴 Désactiver" if a['est_actif'] else "🟢 Activer"
                    if c_stat.button(btn_label, key=f"stat_{a['id']}"):
                        supabase.table("ateliers").update({"est_actif": not a['est_actif']}).eq("id", a['id']).execute()
                        st.rerun()
                        
                    if c_b.button("🗑️", key=f"at_del_{a['id']}"):
                        cnt_res = supabase.table("inscriptions").select("id", count="exact").eq("atelier_id", a['id']).execute()
                        cnt = cnt_res.count if cnt_res.count is not None else 0
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
                c1, c_edit, c2 = st.columns([0.7, 0.15, 0.15])
                c1.write(f"**{u['nom']}** {u['prenom']}")
                
                # NOUVEAUTÉ : Bouton Modifier
                if c_edit.button("✏️ Modifier", key=f"am_edit_{u['id']}"):
                    edit_am_dialog(u['id'], u['nom'], u['prenom'])
                    
                if c2.button("🗑️", key=f"am_del_{u['id']}"): 
                    secure_delete_dialog("adherents", u['id'], f"{u['prenom']} {u['nom']}", current_code)

        with t3: # NOUVEL ONGLET : SUIVI AM (Reprise des fonctionnalités de l'onglet général)
            choix_admin = st.multiselect("Filtrer AM (Admin) :", liste_adh, key="admin_sel_am")
            ids_admin = [dict_adh[n] for n in choix_admin] if choix_admin else list(dict_adh.values())
            data_admin = supabase.table("inscriptions").select("*, ateliers!inner(*, lieux(nom), horaires(libelle)), adherents(nom, prenom)").in_("adherent_id", ids_admin).eq("ateliers.est_actif", True).order("adherent_id").execute()
            if data_admin.data:
                df_adm = pd.DataFrame([{"AM": f"{i['adherents']['prenom']} {i['adherents']['nom']}", "Date": i['ateliers']['date_atelier'], "Titre": i['ateliers']['titre'], "Enfants": i['nb_enfants']} for i in data_admin.data])
                st.download_button("📥 Export Excel Suivi", data=export_to_excel(df_adm), file_name="admin_suivi.xlsx")
                curr_adm = ""
                for i in data_admin.data:
                    nom_adm = f"{i['adherents']['prenom']} {i['adherents']['nom']}"
                    if nom_adm != curr_adm:
                        st.subheader(nom_adm)
                        curr_adm = nom_adm
                    st.write(f"- {i['ateliers']['date_atelier']} : {i['ateliers']['titre']} ({i['nb_enfants']} enfants)")

        with t4: # NOUVEL ONGLET : PLANNING ATELIERS (Reprise des fonctionnalités)
            c_adm_d1, c_adm_d2 = st.columns(2)
            start_adm = c_adm_d1.date_input("Du", date.today(), key="adm_start", format="DD/MM/YYYY")
            end_adm = c_adm_d2.date_input("Au", start_adm + timedelta(days=30), key="adm_end", format="DD/MM/YYYY")
            ats_adm = supabase.table("ateliers").select("*, lieux(nom), horaires(libelle)").eq("est_actif", True).gte("date_atelier", str(start_adm)).lte("date_atelier", str(end_adm)).order("date_atelier").execute()
            for a in ats_adm.data:
                ins_adm = supabase.table("inscriptions").select("*, adherents(nom, prenom)").eq("atelier_id", a['id']).execute()
                st.markdown(f"**{a['date_atelier']}** - {a['titre']} ({len(ins_adm.data)} AM)")
                for p in ins_adm.data:
                    st.write(f"   └ {p['adherents']['prenom']} {p['adherents']['nom']} ({p['nb_enfants']} enf.)")

        with t5: # LIEUX / HORAIRES
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

        with t6: # SÉCURITÉ
            with st.form("sec_form"):
                o, n = st.text_input("Ancien code", type="password"), st.text_input("Nouveau code", type="password")
                if st.form_submit_button("Changer le code"):
                    if o == current_code: 
                        supabase.table("configuration").update({"secret_code": n}).eq("id", "main_config").execute()
                        st.success("Code mis à jour"); st.rerun()
                    else: st.error("Ancien code incorrect")
    else: st.info("Saisissez le code secret.")
