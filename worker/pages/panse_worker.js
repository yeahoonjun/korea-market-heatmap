// Pages project `panse` (https://panse.pages.dev, AGENTS §3-26): every request goes to the Worker through the service binding API.
export default { async fetch(request, env) { return env.API.fetch(request); } };
