document.addEventListener("click", (event) => {
  const onglet = event.target.closest('[data-role="onglet"]');
  if (!onglet) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  event.preventDefault();
  const groupe = onglet.dataset.groupe;
  const cle = onglet.dataset.cle;
  document.querySelectorAll(`[data-groupe="${groupe}"]`).forEach((el) => {
    const actif = el.dataset.cle === cle;
    if (el.dataset.role === "panneau") el.hidden = !actif;
    if (el.dataset.role === "onglet") el.setAttribute("aria-selected", actif ? "true" : "false");
  });
  const url = new URL(window.location.href);
  url.searchParams.set(groupe, cle);
  history.replaceState(null, "", url);
  document.querySelectorAll('[data-role="onglet"]').forEach((el) => {
    const href = new URL(el.getAttribute("href"), window.location.origin);
    href.searchParams.set(groupe, cle);
    el.setAttribute("href", `${href.pathname}${href.search}`);
  });
});

document.addEventListener("change", (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || !input.form || input.form.id !== "statut-form") return;
  if (input.name === "statut") {
    const traite = input.form.querySelector("[name=traite]");
    if (traite) traite.checked = false;
  }
  if (input.name === "traite" && input.checked) {
    const radio = input.form.querySelector("[name=statut]");
    if (radio) radio.checked = false;
  }
  input.form.requestSubmit();
});

let ligneSeq = 0;

function lireMontant(texte) {
  const nombre = Number(String(texte ?? "").replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(nombre) ? nombre : NaN;
}

function majTotalLigne(ligne) {
  if (!ligne) return;
  const affichage = ligne.querySelector("[data-role=total]");
  if (!affichage) return;
  const prix = lireMontant(ligne.querySelector("[name=prix_unitaire]")?.value);
  const quantite = lireMontant(ligne.querySelector("[name=quantite]")?.value);
  if (!Number.isFinite(prix) || !Number.isFinite(quantite)) {
    affichage.textContent = "—";
    return;
  }
  affichage.textContent = (prix * quantite).toFixed(2).replace(".", ",");
}

document.addEventListener("click", (event) => {
  const ajout = event.target.closest("[data-ajout-ligne]");
  if (ajout) {
    event.preventDefault();
    const panneau = ajout.closest('[data-role="panneau"]');
    const modele = panneau && panneau.querySelector("template");
    const ancre = ajout.closest("tr");
    if (!modele || !ancre) return;
    const fragment = modele.content.cloneNode(true);
    const ligneModele = fragment.querySelector("tr");
    if (!ligneModele) return;
    const identifiant = `ligne-nouvelle-${++ligneSeq}`;
    fragment.querySelectorAll("[data-form]").forEach((el) => {
      if (el.tagName === "FORM") el.id = identifiant;
      else el.setAttribute("form", identifiant);
    });
    ancre.before(fragment);
    const ligne = ancre.previousElementSibling;
    if (window.htmx) window.htmx.process(ligne);
    const premier = ligne.querySelector("select, input:not([type=hidden])");
    if (premier) premier.focus();
    majTotalLigne(ligne);
    return;
  }
  const retirer = event.target.closest("[data-retirer-ligne]");
  if (!retirer) return;
  event.preventDefault();
  retirer.closest("tr")?.remove();
});

document.addEventListener("change", (event) => {
  const champ = event.target;
  if (!(champ instanceof HTMLSelectElement) || champ.name !== "produit_id") return;
  const prix = champ.selectedOptions[0] && champ.selectedOptions[0].dataset.prix;
  const ligne = champ.closest("tr");
  const champPrix = ligne && ligne.querySelector("[name=prix_unitaire]");
  if (champPrix && prix) champPrix.value = prix.replace(".", ",");
  majTotalLigne(ligne);
});

document.addEventListener("input", (event) => {
  const champ = event.target;
  if (!(champ instanceof HTMLInputElement)) return;
  if (champ.name === "prix_unitaire" || champ.name === "quantite") {
    majTotalLigne(champ.closest("tr"));
    return;
  }
  if (champ.name !== "date_debut" && champ.name !== "date_fin") return;
  const ligne = champ.closest("tr");
  const affichage = ligne && ligne.querySelector("[data-role=nuits]");
  if (!affichage) return;
  const debut = ligne.querySelector("[name=date_debut]")?.value;
  const fin = ligne.querySelector("[name=date_fin]")?.value;
  if (!debut || !fin) {
    affichage.textContent = "—";
    return;
  }
  const nuits = Math.round((Date.parse(fin) - Date.parse(debut)) / 86400000);
  affichage.textContent = nuits > 0 ? String(nuits) : "—";
});
