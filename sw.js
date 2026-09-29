// Portugal Radar: service worker mínimo para permitir instalar no ecrã principal.
// Não guarda nada em cache: tudo vem sempre da rede, para as notícias estarem sempre atualizadas.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
