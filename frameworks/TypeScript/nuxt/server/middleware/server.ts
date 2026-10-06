export default defineEventHandler((event) => {
  setResponseHeader(event, "Server", "Nuxt")
})
