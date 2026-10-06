import { createSSRApp } from "vue"
import { renderToString } from "vue/server-renderer"
import { sql } from "../utils/db"
import Fortunes from "../templates/Fortunes.vue"

type Fortune = { id: number, message: string }

export default defineEventHandler(async (event) => {
  const fortunes: Fortune[] = [...await sql<Fortune[]>`SELECT id, message FROM fortune`]
  fortunes.push({ id: 0, message: "Additional fortune added at request time." })
  fortunes.sort((a, b) => (a.message < b.message ? -1 : a.message > b.message ? 1 : 0))

  const html = await renderToString(createSSRApp(Fortunes, { fortunes }))

  setResponseHeader(event, "Content-Type", "text/html; charset=utf-8")
  return "<!DOCTYPE html>" + html
})
