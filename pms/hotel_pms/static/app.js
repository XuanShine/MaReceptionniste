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

function filtrerMoyens(valeur) {
  const q = valeur.trim().toLowerCase();
  document.querySelectorAll("[data-moyen]").forEach((el) => {
    el.hidden = q.length > 0 && !el.dataset.moyen.toLowerCase().includes(q);
  });
}
