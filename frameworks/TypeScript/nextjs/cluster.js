const cluster = require("node:cluster")

const workers = Number(process.env.RC_WORKERS)

if (workers && cluster.isPrimary) {
  for (let i = 0; i < workers; i++) {
    cluster.fork()
  }

  cluster.on("exit", () => {
    process.exit(1)
  })
} else {
  require("./.next/standalone/server.js")
}
