import Vue from "unplugin-vue/rollup"

export default defineNuxtConfig({
  compatibilityDate: "2026-10-01",
  devtools: { enabled: false },
  telemetry: false,
  nitro: {
    preset: "node-cluster",
    rollupConfig: {
      plugins: [Vue({ isProduction: true, ssr: true })],
    },
  },
})
