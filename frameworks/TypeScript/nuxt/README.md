# Nuxt Benchmarking Test

### Test Type Implementation Source Code

* [JSON](server/routes/json.ts)
* [DB](server/routes/db.ts)
* [FORTUNES](server/routes/fortunes.ts), rendered from [Fortunes.vue](server/templates/Fortunes.vue)

## Important Libraries

The tests were run with:

* [Nuxt](https://nuxt.com/) 4.6 on the Nitro `node-cluster` preset
* [Vue](https://vuejs.org/) and `vue/server-renderer`
* [Postgres.js](https://github.com/porsager/postgres)

## Implementation Notes

Every test is a Nitro server route. Nuxt pages wrap their output in `<div id="__nuxt">`, which the fortunes spec doesn't allow, so the fortunes route renders a Vue single-file component with `vue/server-renderer` and returns the whole HTML document itself. `unplugin-vue` compiles the component for the Nitro build.

Nitro's cluster preset forks one worker per CPU. `RC_WORKERS` sets the worker count and `RC_DB_POOL` sets the Postgres pool per worker (10 when unset).

## Test URLs

### JSON

http://localhost:8080/json

### DB

http://localhost:8080/db

### FORTUNES

http://localhost:8080/fortunes
