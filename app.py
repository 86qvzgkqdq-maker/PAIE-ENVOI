"""PAIE-ENVOI — rapprochement bulletins de paie / relevés Thésée, fusion et envoi.

Lancement : .venv/bin/streamlit run app.py
"""

import io
import os
import re
import smtplib
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from paie.acces import verifier
from paie.clients import ErreurColonnes, charger_clients
from paie.config import (MDP_APPLICATION, detecter_smtp,
                         detecter_smtp_entreprise, enregistrer_env)
from paie.courrier import config_manquante, envoyer, tester_connexion
from paie.fusion import fusionner, nom_fichier_sur
from paie.journal import consigner, deja_envoyes, historique
from paie.rapprochement import clients_dans_texte, extraire_texte

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
JOURNAL_DB = DATA / "journal.db"
FICHIER_ENV = BASE / ".env"

load_dotenv(FICHIER_ENV)

# Déploiement Streamlit Cloud : la config vient du panneau « Secrets »
# (st.secrets). En local, le .env a priorité et ce bloc ne fait rien.
try:
    for _cle, _valeur in st.secrets.items():
        if isinstance(_valeur, str) and _cle not in os.environ:
            os.environ[_cle] = _valeur
except Exception:
    pass  # pas de fichier secrets en local

st.set_page_config(page_title="Paie & Relevés", page_icon="📨", layout="wide")

# ------------------------------------------------------------- accès protégé
MDP_HASH = os.getenv("APP_MDP_SHA256", "").strip()
if MDP_HASH and not re.fullmatch(r"[0-9a-fA-F]{64}", MDP_HASH):
    st.error(
        "⚠️ Configuration : le secret `APP_MDP_SHA256` est mal formé "
        "(il doit contenir exactement 64 caractères hexadécimaux, sans "
        "espaces ni « … »). Corrigez-le dans Manage app → Settings → Secrets."
    )
    st.stop()
if MDP_HASH and not st.session_state.get("authentifie"):
    st.title("🔒 Accès protégé")
    saisie = st.text_input("Mot de passe", type="password")
    if saisie:
        if verifier(saisie, MDP_HASH):
            st.session_state["authentifie"] = True
            st.rerun()
        else:
            time.sleep(1)  # freine les essais en rafale
            st.error("Mot de passe incorrect.")
    st.stop()

st.title("📨 Bulletins de paie + relevés Thésée → fusion → envoi")

AUCUN = "— aucun —"

SUJET_DEFAUT = "Vos documents de paie — {periode}"
CORPS_DEFAUT = (
    "Bonjour {prenom},\n\n"
    "Veuillez trouver ci-joint votre bulletin de paie ainsi que votre relevé "
    "mensuel pour la période : {periode}.\n\n"
    "Bien cordialement,"
)
SUJET_HEBDO = "Votre relevé hebdomadaire — {periode}"
CORPS_HEBDO = (
    "Bonjour {prenom},\n\n"
    "Veuillez trouver ci-joint votre relevé hebdomadaire pour la période : "
    "{periode}.\n\n"
    "Bien cordialement,"
)
SUJET_MULTI = "Vos documents — {periode}"
CORPS_MULTI = (
    "Bonjour {prenom},\n\n"
    "Veuillez trouver ci-joint vos documents pour la période : {periode}.\n\n"
    "Bien cordialement,"
)

# Libellés / défauts par mode d'envoi
MODE_LABELS = {
    "mensuel": "📅 Mensuel — bulletin + relevé (fusionnés)",
    "hebdo": "🗓️ Hebdomadaire — relevé seul",
    "multi": "📎 Multi-documents — plusieurs pièces par chauffeur",
}
DEFAUTS_EMAIL = {
    "mensuel": (SUJET_DEFAUT, CORPS_DEFAUT),
    "hebdo": (SUJET_HEBDO, CORPS_HEBDO),
    "multi": (SUJET_MULTI, CORPS_MULTI),
}
TITRE_ETAPE4 = {
    "mensuel": "4 · Fusion en un PDF par client",
    "hebdo": "4 · Préparation des relevés",
    "multi": "4 · Préparation des documents",
}
LIBELLE_PREP = {
    "mensuel": "Fusionner les dossiers complets",
    "hebdo": "Préparer les relevés",
    "multi": "Préparer les documents",
}


def _texte_document(fichier_upload) -> str:
    """Texte extrait d'un PDF uploadé, mis en cache dans la session."""
    cache = st.session_state.setdefault("textes_pdf", {})
    cle = (fichier_upload.name, fichier_upload.size)
    if cle not in cache:
        cache[cle] = extraire_texte(io.BytesIO(fichier_upload.getvalue()))
    return cache[cle]


def _auto_choix(client, fichiers) -> tuple[str, int]:
    """(nom du fichier retenu, nombre de candidats) pour un client donné."""
    candidats = []
    for f in fichiers:
        contenu = _texte_document(f) or f.name
        if clients_dans_texte(contenu, [client]):
            candidats.append(f.name)
    return (candidats[0] if candidats else AUCUN), len(candidats)


# ---------------------------------------------------------------- barre latérale
with st.sidebar:
    st.header("Paramètres")
    periode = st.text_input("Période", placeholder="ex. Juin 2026 · Semaine 28")

    if config_manquante():
        st.warning("Envoi d'emails non configuré : renseignez votre adresse "
                   "dans l'onglet **⚙️ Mon email**.")
    else:
        st.success(f"Envois via {os.getenv('SMTP_USER')} ✔")

    st.divider()
    st.caption(
        "Tout reste en local : les documents ne partent que vers vos "
        "destinataires, via votre propre serveur d'email."
    )

onglet_envois, onglet_config = st.tabs(["📨 Envoi des documents", "⚙️ Mon email"])

# ---------------------------------------------------------------- onglet : mon email
# (rendu en premier dans le code : l'onglet Envois peut interrompre le script)
with onglet_config:
    st.subheader("Compte email pour les envois")
    st.caption("Enregistré uniquement sur cet ordinateur (fichier `.env` du projet).")

    if st.session_state.pop("config_enregistree", False):
        st.success("Configuration enregistrée ✔ — vous pouvez tester la connexion.")

    email_conf = st.text_input(
        "Votre adresse email", value=os.getenv("SMTP_USER", ""),
        placeholder="vous@entreprise.fr",
    )
    detection = detecter_smtp(email_conf) if email_conf else None

    mdp_conf = st.text_input("Mot de passe", type="password",
                             value=os.getenv("SMTP_PASSWORD", ""))
    if detection and detection[0] in MDP_APPLICATION:
        st.info(
            "Ce fournisseur exige un **mot de passe d'application** (à générer "
            "dans les réglages de sécurité du compte), pas votre mot de passe habituel."
        )

    # valeurs initiales des champs serveur (remplissables par la détection)
    st.session_state.setdefault("champ_hote", os.getenv("SMTP_HOST", ""))
    st.session_state.setdefault("champ_port", int(os.getenv("SMTP_PORT") or 587))

    # adresse d'entreprise (domaine propre) : détection via DNS / sondage
    if email_conf and not detection and not st.session_state["champ_hote"]:
        st.warning("Fournisseur non reconnu automatiquement — probablement une "
                   "adresse d'entreprise. Essayez la détection ci-dessous.")
        if st.button("🔍 Détecter le serveur de mon entreprise"):
            with st.spinner("Interrogation du domaine…"):
                trouve = detecter_smtp_entreprise(email_conf)
            if trouve:
                st.session_state["champ_hote"] = trouve[0]
                st.session_state["champ_port"] = trouve[1]
                st.success(f"Serveur détecté : **{trouve[0]}** (port {trouve[1]}, "
                           f"{trouve[2]}). Vérifiez dans les réglages avancés, "
                           "puis enregistrez et testez la connexion.")
            else:
                st.error(
                    "Détection impossible pour ce domaine. Demandez à votre "
                    "service informatique (ou à l'hébergeur de votre site web / "
                    "messagerie) : **serveur SMTP**, **port**, et si un mot de "
                    "passe spécifique est requis — puis saisissez-les dans les "
                    "réglages avancés ci-dessous."
                )

    ouvrir_avances = bool(email_conf and not detection)
    with st.expander("Réglages avancés (serveur SMTP)", expanded=ouvrir_avances):
        hote_conf = st.text_input(
            "Serveur SMTP", key="champ_hote",
            placeholder=detection[0] if detection else "smtp.exemple.fr",
        )
        port_conf = st.number_input(
            "Port", min_value=1, max_value=65535, key="champ_port",
        )
        expediteur_conf = st.text_input(
            "Adresse d'expéditeur si différente (optionnel)",
            value=os.getenv("SMTP_FROM", ""),
        )

    col_save, col_test = st.columns(2)

    if col_save.button("💾 Enregistrer", type="primary"):
        # serveur : champ avancé s'il est rempli, sinon détection automatique
        if hote_conf.strip():
            hote_final, port_final = hote_conf.strip(), int(port_conf)
        elif detection:
            hote_final, port_final = detection
        else:
            hote_final, port_final = "", 0

        if not (email_conf.strip() and mdp_conf and hote_final):
            st.error("Il faut au minimum : adresse email, mot de passe, et un "
                     "serveur SMTP (détecté automatiquement ou saisi dans les "
                     "réglages avancés).")
        else:
            enregistrer_env(FICHIER_ENV, {
                "SMTP_HOST": hote_final,
                "SMTP_PORT": str(port_final),
                "SMTP_USER": email_conf.strip(),
                "SMTP_PASSWORD": mdp_conf,
                "SMTP_FROM": expediteur_conf.strip(),
            })
            st.session_state["config_enregistree"] = True
            st.rerun()

    if col_test.button("🔌 Tester la connexion", disabled=bool(config_manquante())):
        try:
            with st.spinner("Connexion au serveur email…"):
                tester_connexion()
        except smtplib.SMTPAuthenticationError:
            st.error(
                "Le serveur répond, mais **refuse le mot de passe**. "
                "Vérifiez le mot de passe de votre boîte email (celui du "
                "webmail), corrigez-le ci-dessus, enregistrez, puis retestez. "
                "Pour Gmail/iCloud/Yahoo, il faut un mot de passe d'application."
            )
        except Exception as e:
            st.error(f"Échec de connexion : {e}")
        else:
            st.success("Connexion réussie ✔ — l'envoi est opérationnel.")

# ---------------------------------------------------------------- onglet : envois
with onglet_envois:
    mode = st.radio(
        "Type d'envoi", list(MODE_LABELS),
        format_func=lambda k: MODE_LABELS[k], horizontal=True,
    )

    # --- étape 1 : clients
    st.header("1 · Fichier clients (Excel)")
    fichier_excel = st.file_uploader(
        "Fichier .xlsx avec colonnes Nom, Prénom, Email", type=["xlsx"]
    )

    clients = []
    if fichier_excel:
        try:
            clients = charger_clients(io.BytesIO(fichier_excel.getvalue()))
        except ErreurColonnes as e:
            st.error(str(e))
        else:
            st.success(f"{len(clients)} client(s) chargé(s).")
            with st.expander("Voir la liste"):
                st.dataframe(
                    [{"Nom": c.nom, "Prénom": c.prenom, "Email": c.email}
                     for c in clients],
                    use_container_width=True,
                )

    # --- étape 2 : documents
    # `colonnes_docs` = liste de (libellé, [fichiers]) commune aux 3 modes.
    # `exiger_tous` : mensuel/hebdo exigent chaque type ; multi = au moins un.
    st.header("2 · Documents PDF")
    if mode == "multi":
        st.caption("Un type de document par lot (bulletin, relevé, attestation…). "
                   "Chaque chauffeur reçoit, dans un seul email, tous les documents "
                   "qui le concernent, en pièces jointes séparées.")
        nb_lots = st.number_input(
            "Nombre de types de documents", min_value=2, max_value=8, value=2, key="multi_nb"
        )
        lots = []
        for i in range(int(nb_lots)):
            col_nom, col_fic = st.columns([1, 3])
            label = col_nom.text_input(
                f"Nom du document {i + 1}", value=f"Document {i + 1}",
                key=f"multi_label_{i}",
            )
            fichiers = col_fic.file_uploader(
                label or f"Document {i + 1}", type=["pdf"],
                accept_multiple_files=True, key=f"multi_lot_{i}",
            )
            lots.append((label.strip() or f"Document {i + 1}", fichiers or []))
        colonnes_docs = [(lbl, fics) for lbl, fics in lots if fics]
        exiger_tous = False
    elif mode == "hebdo":
        releves = st.file_uploader(
            "Relevés hebdomadaires (Thésée)", type=["pdf"],
            accept_multiple_files=True, key="rel_hebdo",
        )
        colonnes_docs = [("Relevé", releves or [])]
        exiger_tous = True
    else:  # mensuel
        col_bp, col_rel = st.columns(2)
        with col_bp:
            bulletins = st.file_uploader(
                "Bulletins de paie", type=["pdf"], accept_multiple_files=True, key="bp"
            )
        with col_rel:
            releves = st.file_uploader(
                "Relevés mensuels (Thésée)", type=["pdf"], accept_multiple_files=True, key="rel"
            )
        colonnes_docs = [("Bulletin de paie", bulletins or []), ("Relevé", releves or [])]
        exiger_tous = True

    # --- étape 3 : rapprochement
    st.header("3 · Rapprochement par nom / prénom")

    a_des_docs = any(fics for _, fics in colonnes_docs)
    docs_suffisants = (all(fics for _, fics in colonnes_docs) and bool(colonnes_docs)
                       if exiger_tous else a_des_docs)
    if not (clients and docs_suffisants):
        if mode == "multi":
            st.info("Chargez le fichier clients et au moins un lot de documents pour continuer.")
        elif mode == "hebdo":
            st.info("Chargez le fichier clients et les relevés pour continuer.")
        else:
            st.info("Chargez le fichier clients, des bulletins et des relevés pour continuer.")
        st.stop()

    options_par_col = [[AUCUN] + [f.name for f in fics] for _, fics in colonnes_docs]

    st.caption(
        "Le nom de chaque client est recherché dans le texte des PDF "
        "(à défaut, dans le nom du fichier). Corrigez manuellement si besoin."
    )

    # homonymes (même nom+prénom, emails différents) : le rapprochement par
    # nom ne peut pas les distinguer -> à contrôler à la main
    par_cle = {}
    for c in clients:
        par_cle.setdefault(c.cle, []).append(c)
    homonymes = [groupe for groupe in par_cle.values() if len(groupe) > 1]
    if homonymes:
        st.warning(
            "⚠️ Homonymes dans la liste clients (même nom et prénom, emails "
            "différents) : "
            + " ; ".join(g[0].affichage for g in homonymes)
            + " — le rapprochement automatique ne peut pas les distinguer, "
            "vérifiez leurs documents à la main ci-dessous."
        )

    n_cols = len(colonnes_docs)
    largeurs = [3] + [max(3, 8 // n_cols)] * n_cols + [2]
    titres = ["**Client**"] + [f"**{lbl}**" for lbl, _ in colonnes_docs] + ["**État**"]
    for col, titre in zip(st.columns(largeurs), titres):
        col.markdown(titre)

    selection = {}
    for i, client in enumerate(clients):
        ligne = st.columns(largeurs)
        ligne[0].write(f"{client.affichage}\n\n`{client.email}`")
        choix, plusieurs = [], False
        for j, (lbl, fics) in enumerate(colonnes_docs):
            auto, nb = _auto_choix(client, fics)
            opts = options_par_col[j]
            c = ligne[1 + j].selectbox(
                lbl, opts, index=opts.index(auto),
                key=f"doc_{i}_{j}", label_visibility="collapsed",
            )
            choix.append(c)
            if nb > 1:
                plusieurs = True
        retenus = [c for c in choix if c != AUCUN]
        complet = (len(retenus) == n_cols) if exiger_tous else (len(retenus) >= 1)
        if complet:
            etat = f"✅ {len(retenus)} doc" if mode == "multi" else "✅"
            if plusieurs:
                etat = "⚠️ plusieurs candidats"
        else:
            etat = "❌ incomplet" if exiger_tous else "❌ aucun"
        ligne[-1].write(etat)
        selection[i] = (client, choix, complet)

    complets = [(c, choix) for c, choix, ok in selection.values() if ok]
    st.write(f"**{len(complets)} / {len(clients)}** dossiers à envoyer.")

    # --- étape 4 : préparation des PDF
    st.header(TITRE_ETAPE4[mode])

    if not periode:
        st.info("Indiquez la période dans la barre latérale (elle nomme les fichiers "
                "et l'email) — ex. « Semaine 28 » en hebdo, « Juin 2026 » en mensuel.")
        st.stop()

    if st.button(LIBELLE_PREP[mode], type="primary", disabled=not complets):
        fichiers_par_nom = {f.name: f for _, fics in colonnes_docs for f in fics}
        dossier_sortie = DATA / "fusions" / nom_fichier_sur(periode)
        base_periode = nom_fichier_sur(periode)
        prepares = []
        barre = st.progress(0.0)
        for i, (client, choix) in enumerate(complets):
            base_client = nom_fichier_sur(client.affichage)
            if mode == "multi":
                # une pièce jointe par document, sans fusion
                chemins = []
                for (lbl, _), nom in zip(colonnes_docs, choix):
                    if nom == AUCUN:
                        continue
                    dest = (dossier_sortie / base_client /
                            f"{base_client}_{nom_fichier_sur(lbl)}_{base_periode}.pdf")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(fichiers_par_nom[nom].getvalue())
                    chemins.append(dest)
            else:
                # fusion des documents retenus en un seul PDF
                noms = [n for n in choix if n != AUCUN]
                sources = [io.BytesIO(fichiers_par_nom[n].getvalue()) for n in noms]
                dest = dossier_sortie / f"{base_client}_{base_periode}.pdf"
                fusionner(sources, dest)
                chemins = [dest]
            prepares.append({"client": client, "chemins": chemins})
            barre.progress((i + 1) / len(complets))
        # mémorisés avec leur contexte : pas d'envoi croisé entre modes/périodes
        st.session_state["fusions"] = {"mode": mode, "periode": periode,
                                       "items": prepares}
        total = sum(len(p["chemins"]) for p in prepares)
        st.success(f"{total} PDF prêt(s) pour {len(prepares)} chauffeur(s) "
                   f"dans `{dossier_sortie}`.")

    paquet = st.session_state.get("fusions")
    fusions = (paquet["items"]
               if isinstance(paquet, dict) and paquet.get("mode") == mode
               and paquet.get("periode") == periode
               else [])
    if fusions:
        total_pdf = sum(len(f["chemins"]) for f in fusions)
        with st.expander(f"Télécharger les {total_pdf} PDF préparés"):
            for f in fusions:
                for chemin in f["chemins"]:
                    st.download_button(
                        chemin.name,
                        data=chemin.read_bytes(),
                        file_name=chemin.name,
                        mime="application/pdf",
                        key=f"dl_{chemin}",
                    )

    # --- étape 5 : envoi
    st.header("5 · Envoi par email")

    if not fusions:
        st.info("Préparez d'abord les documents à l'étape 4 (pour ce mode et "
                "cette période).")
        st.stop()

    if config_manquante():
        st.error("Renseignez votre email dans l'onglet **⚙️ Mon email** avant d'envoyer.")
        st.stop()

    sujet_defaut, corps_defaut = DEFAUTS_EMAIL[mode]
    sujet_modele = st.text_input("Sujet", value=sujet_defaut)
    corps_modele = st.text_area("Message", value=corps_defaut, height=160)
    st.caption("Champs disponibles : `{prenom}`, `{nom}`, `{periode}`")

    def _rendre(modele: str, client) -> str:
        return modele.format(prenom=client.prenom, nom=client.nom, periode=periode)

    # --- test vers soi-même
    with st.expander("Envoyer un email de test (recommandé avant l'envoi groupé)"):
        email_test = st.text_input("Adresse de test", value=os.getenv("SMTP_USER", ""))
        if st.button("Envoyer le test", disabled=not email_test):
            exemple = fusions[0]
            try:
                envoyer(email_test, "[TEST] " + _rendre(sujet_modele, exemple["client"]),
                        _rendre(corps_modele, exemple["client"]), exemple["chemins"])
            except Exception as e:
                st.error(f"Échec du test : {e}")
            else:
                st.success(f"Test envoyé à {email_test} — {len(exemple['chemins'])} "
                           f"pièce(s) jointe(s) (dossier de {exemple['client'].affichage}).")

    # --- envoi groupé
    servis = deja_envoyes(JOURNAL_DB, periode)
    a_envoyer = [f for f in fusions if f["client"].email not in servis]
    deja = len(fusions) - len(a_envoyer)
    if deja:
        st.info(f"{deja} client(s) déjà servi(s) pour « {periode} » — ils seront ignorés.")

    st.write(f"**{len(a_envoyer)} email(s)** à envoyer.")
    confirmation = st.checkbox(
        f"Je confirme l'envoi de {len(a_envoyer)} email(s) avec pièces jointes "
        f"pour la période « {periode} »."
    )

    if st.button(f"📤 Tout envoyer en une fois ({len(a_envoyer)} emails)", type="primary",
                 disabled=not (confirmation and a_envoyer)):
        barre = st.progress(0.0)
        zone = st.container()
        reussis, echoues = 0, 0
        for i, f in enumerate(a_envoyer):
            client, chemins = f["client"], f["chemins"]
            noms = " ; ".join(c.name for c in chemins)
            try:
                envoyer(client.email, _rendre(sujet_modele, client),
                        _rendre(corps_modele, client), chemins)
            except Exception as e:
                echoues += 1
                consigner(JOURNAL_DB, periode, client.affichage, client.email,
                          noms, "échec", str(e))
                zone.error(f"{client.affichage} ({client.email}) : {e}")
            else:
                reussis += 1
                consigner(JOURNAL_DB, periode, client.affichage, client.email,
                          noms, "envoyé")
                zone.write(f"✅ {client.affichage} → {client.email} "
                           f"({len(chemins)} pièce(s))")
            barre.progress((i + 1) / len(a_envoyer))
            time.sleep(1)  # ménage le serveur SMTP (limites anti-spam)
        if echoues:
            st.warning(f"{reussis} envoyé(s), {echoues} échec(s) — voir le journal.")
        else:
            st.success(f"Tous les emails envoyés ({reussis}).")

    # --- journal
    with st.expander("Journal des envois"):
        lignes = historique(JOURNAL_DB)
        if lignes:
            st.dataframe(
                [{"Date": l[0], "Période": l[1], "Client": l[2], "Email": l[3],
                  "Fichier": l[4], "Statut": l[5], "Erreur": l[6] or ""} for l in lignes],
                use_container_width=True,
            )
        else:
            st.caption("Aucun envoi pour l'instant.")
