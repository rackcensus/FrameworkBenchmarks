import { sql } from "../utils/db"

export default defineEventHandler(async () => {
  const id = 1 + Math.floor(Math.random() * 10000)
  const [world] = await sql`SELECT id, randomnumber FROM world WHERE id = ${id}`

  return { id: world.id, randomNumber: world.randomnumber }
})
