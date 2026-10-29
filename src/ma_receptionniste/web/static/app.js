document.addEventListener("click", (event) => {
  const onglet = event.target.closest("[data-tab]");
  if (onglet) {
    const groupe = onglet.closest("[data-tabs]");
    const racine = groupe.closest("[data-onglets]");
    groupe.querySelectorAll("[data-tab]").forEach((bouton) => {
      bouton.setAttribute("aria-selected", bouton === onglet ? "true" : "false");
    });
    racine.querySelectorAll("[data-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.panel !== onglet.dataset.tab;
    });
  }

  const ouvre = event.target.closest("[data-ouvre]");
  if (ouvre) {
    document.getElementById(ouvre.dataset.ouvre)?.showModal();
  }

  const ligne = event.target.closest("tr[data-href]");
  if (ligne && !event.target.closest("a, button, input, select, textarea")) {
    window.location = ligne.dataset.href;
  }
});

document.addEventListener("input", (event) => {
  const zone = event.target;
  if (zone.dataset.pastille) {
    const pastille = document.querySelector(`[data-tab="${zone.dataset.pastille}"] .pastille`);
    if (pastille) pastille.hidden = !zone.value.trim();
  }
  filtrer(zone);
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && document.getElementById("fiche-champs")) {
    event.preventDefault();
    document.getElementById("confirmer")?.click();
    return;
  }
  if (event.key !== "Escape") return;
  const modal = document.querySelector("dialog[open]");
  if (modal) {
    event.preventDefault();
    modal.close();
    return;
  }
  const dialogue = document.getElementById("dialogue");
  if (dialogue && dialogue.childElementCount) {
    event.preventDefault();
    dialogue.replaceChildren();
    return;
  }
  if (document.getElementById("fiche-champs")) {
    event.preventDefault();
    document.getElementById("abandon")?.click();
  }
}, true);

document.body.addEventListener("client-ajoute", () => {
  document.getElementById("form-client")?.reset();
});

document.body.addEventListener("htmx:afterSwap", () => {
  document.querySelectorAll("[data-filtre]").forEach((input) => {
    if (input.value.trim()) filtrer(input);
  });
});

function filtrer(zone) {
  if (!zone.dataset || !zone.dataset.filtre) return;
  const table = document.getElementById(zone.dataset.filtre);
  if (!table) return;
  const recherche = zone.value.trim().toLowerCase();
  let visibles = 0;
  table.querySelectorAll("tbody tr[data-filtre-ligne]").forEach((ligne) => {
    const visible = ligne.innerText.toLowerCase().includes(recherche);
    ligne.hidden = !visible;
    if (visible) visibles += 1;
  });
  const vide = document.getElementById(`${zone.dataset.filtre}-vide`);
  if (vide) vide.hidden = recherche === "" || visibles !== 0;
}
