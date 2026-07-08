"""PAIE-ENVOI — rapprochement bulletins de paie / relevés Thésée, fusion et envoi.

Lancement : .venv/bin/streamlit run app.py
"""

import io
import os
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
MDP_HASH = os.getenv("APP_MDP_SHA256", "")
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
    periode = st.text_input("Période", placeholder="ex. Juin 2026")

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
    st.header("2 · Documents PDF")
    col_bp, col_rel = st.columns(2)
    with col_bp:
        bulletins = st.file_uploader(
            "Bulletins de paie", type=["pdf"], accept_multiple_files=True, key="bp"
        )
    with col_rel:
        releves = st.file_uploader(
            "Relevés mensuels (Thésée)", type=["pdf"], accept_multiple_files=True, key="rel"
        )

    # --- étape 3 : rapprochement
    st.header("3 · Rapprochement par nom / prénom")

    if not (clients and bulletins and releves):
        st.info("Chargez le fichier clients, des bulletins et des relevés pour continuer.")
        st.stop()

    options_bp = [AUCUN] + [f.name for f in bulletins]
    options_rel = [AUCUN] + [f.name for f in releves]

    st.caption(
        "Le nom de chaque client est recherché dans le texte des PDF "
        "(à défaut, dans le nom du fichier). Corrigez manuellement si besoin."
    )

    selection = {}
    en_tete = st.columns([3, 4, 4, 2])
    for col, titre in zip(en_tete, ["**Client**", "**Bulletin de paie**", "**Relevé**", "**État**"]):
        col.markdown(titre)

    for client in clients:
        auto_bp, nb_bp = _auto_choix(client, bulletins)
        auto_rel, nb_rel = _auto_choix(client, releves)
        c1, c2, c3, c4 = st.columns([3, 4, 4, 2])
        c1.write(f"{client.affichage}\n\n`{client.email}`")
        choix_bp = c2.selectbox(
            "Bulletin", options_bp, index=options_bp.index(auto_bp),
            key=f"bp_{client.cle}", label_visibility="collapsed",
        )
        choix_rel = c3.selectbox(
            "Relevé", options_rel, index=options_rel.index(auto_rel),
            key=f"rel_{client.cle}", label_visibility="collapsed",
        )
        if choix_bp != AUCUN and choix_rel != AUCUN:
            etat = "✅"
            if nb_bp > 1 or nb_rel > 1:
                etat = "⚠️ plusieurs candidats"
        else:
            etat = "❌ incomplet"
        c4.write(etat)
        selection[client.cle] = (client, choix_bp, choix_rel)

    complets = [(c, bp, rel) for c, bp, rel in selection.values()
                if bp != AUCUN and rel != AUCUN]
    st.write(f"**{len(complets)} / {len(clients)}** dossiers complets.")

    # --- étape 4 : fusion
    st.header("4 · Fusion en un PDF par client")

    if not periode:
        st.info("Indiquez la période dans la barre latérale (elle nomme les fichiers et l'email).")
        st.stop()

    if st.button("Fusionner les dossiers complets", type="primary", disabled=not complets):
        fichiers_par_nom = {f.name: f for f in list(bulletins) + list(releves)}
        dossier_sortie = DATA / "fusions" / nom_fichier_sur(periode)
        fusions = []
        barre = st.progress(0.0)
        for i, (client, nom_bp, nom_rel) in enumerate(complets):
            sources = [io.BytesIO(fichiers_par_nom[nom_bp].getvalue()),
                       io.BytesIO(fichiers_par_nom[nom_rel].getvalue())]
            destination = dossier_sortie / (
                f"{nom_fichier_sur(client.affichage)}_{nom_fichier_sur(periode)}.pdf"
            )
            fusionner(sources, destination)
            fusions.append({"client": client, "chemin": destination})
            barre.progress((i + 1) / len(complets))
        st.session_state["fusions"] = fusions
        st.success(f"{len(fusions)} PDF fusionné(s) dans `{dossier_sortie}`.")

    fusions = st.session_state.get("fusions", [])
    if fusions:
        with st.expander(f"Télécharger les {len(fusions)} PDF fusionnés"):
            for f in fusions:
                st.download_button(
                    f["chemin"].name,
                    data=f["chemin"].read_bytes(),
                    file_name=f["chemin"].name,
                    mime="application/pdf",
                    key=f"dl_{f['chemin'].name}",
                )

    # --- étape 5 : envoi
    st.header("5 · Envoi par email")

    if not fusions:
        st.info("Fusionnez d'abord les documents.")
        st.stop()

    if config_manquante():
        st.error("Renseignez votre email dans l'onglet **⚙️ Mon email** avant d'envoyer.")
        st.stop()

    sujet_modele = st.text_input("Sujet", value=SUJET_DEFAUT)
    corps_modele = st.text_area("Message", value=CORPS_DEFAUT, height=160)
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
                        _rendre(corps_modele, exemple["client"]), [exemple["chemin"]])
            except Exception as e:
                st.error(f"Échec du test : {e}")
            else:
                st.success(f"Test envoyé à {email_test} (dossier de {exemple['client'].affichage}).")

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
            client, chemin = f["client"], f["chemin"]
            try:
                envoyer(client.email, _rendre(sujet_modele, client),
                        _rendre(corps_modele, client), [chemin])
            except Exception as e:
                echoues += 1
                consigner(JOURNAL_DB, periode, client.affichage, client.email,
                          chemin.name, "échec", str(e))
                zone.error(f"{client.affichage} ({client.email}) : {e}")
            else:
                reussis += 1
                consigner(JOURNAL_DB, periode, client.affichage, client.email,
                          chemin.name, "envoyé")
                zone.write(f"✅ {client.affichage} → {client.email}")
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
