<script setup>
defineProps({ fortunes: { type: Array, required: true } })
</script>

<template>
  <html>
    <head><title>Fortunes</title></head>
    <body>
      <table>
        <tbody>
          <tr><th>id</th><th>message</th></tr>
          <tr v-for="fortune in fortunes" :key="fortune.id">
            <td>{{ fortune.id }}</td>
            <td>{{ fortune.message }}</td>
          </tr>
        </tbody>
      </table>
    </body>
  </html>
</template>
