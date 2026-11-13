// Stand-in for the Pages project `panse` (worker/pages/panse_worker.js): every request — WebSocket upgrades included —
// goes to the Worker through the service binding API. Used only to check that an Upgrade survives the binding (realtime.md §4-3).
export default { async fetch(request, env) { return env.API.fetch(request); } };
