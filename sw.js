/* Service worker du Poste de pilotage.
   Objectif : la page se rouvre hors ligne (avion, tunnel, dossier OneDrive non synchronisé).
   Stratégie : « réseau d'abord » pour index.html (on veut toujours la dernière version),
   « cache d'abord » pour les ressources statiques (polices, icônes, xlsx). */

const VERSION = "pilotage-v1";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./assets/fonts/fonts.css",
  "./assets/fonts/instrument-sans-latin-400-normal.woff2",
  "./assets/fonts/instrument-sans-latin-600-normal.woff2",
  "./assets/fonts/instrument-sans-latin-700-normal.woff2",
  "./assets/fonts/jetbrains-mono-latin-400-normal.woff2",
  "./assets/fonts/jetbrains-mono-latin-700-normal.woff2",
  "./assets/img/favicon.svg",
  "./assets/img/favicon-32.png",
  "./assets/img/apple-touch-icon.png",
  "./assets/vendor/xlsx.full.min.js"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(VERSION)
      // addAll échoue en bloc si une seule ressource manque : on tolère les absences.
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;          // fichiers .json du projet : jamais mis en cache
  if (url.pathname.endsWith(".json")) return;

  const isDoc = req.mode === "navigate" || /\/index\.html$|\/$/.test(url.pathname);
  if (isDoc) {
    e.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(VERSION).then(c => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then(r => r || caches.match("./index.html")))
    );
    return;
  }

  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(res => {
      if (res && res.ok && res.type === "basic") {
        const copy = res.clone();
        caches.open(VERSION).then(c => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() => hit))
  );
});
