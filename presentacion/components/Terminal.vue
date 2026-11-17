<script setup lang="ts">
// Terminal real embebida: un iframe a ttyd, que levanta presentacion/levantar.sh.
// Cada slide abre su propia sesión de bash con el entorno de la demo ya cargado.
import { onMounted, ref } from 'vue'

const props = defineProps<{ cmd?: string; height?: string }>()
const url = 'http://localhost:7681'
const disponible = ref(true)

onMounted(async () => {
  try {
    await fetch(url, { mode: 'no-cors' })
  } catch {
    disponible.value = false
  }
})
</script>

<template>
  <div class="term" :style="{ height: props.height ?? '390px' }">
    <div class="term-bar">
      <span class="dot" /><span class="dot" /><span class="dot" />
      <span class="term-title">terminal · farmared_demo</span>
      <span v-if="props.cmd" class="term-cmd">escribí <code>{{ props.cmd }}</code></span>
    </div>
    <iframe v-if="disponible" :src="url" title="Terminal de la demo" />
    <div v-else class="term-off">
      <p>La terminal no está levantada.</p>
      <p>Corré <code>presentacion/levantar.sh</code> y recargá la página.</p>
    </div>
  </div>
</template>

<style scoped>
.term {
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  overflow: hidden;
  background: #0f1a18;
  box-shadow: 0 6px 24px rgba(19, 33, 31, 0.25);
}
.term-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #1b2b28;
  font-size: 11px;
  color: #bfd3cd;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #4a5a57;
}
.term-title {
  margin-left: 6px;
  font-family: 'JetBrains Mono', Menlo, monospace;
}
.term-cmd {
  margin-left: auto;
  color: #7fc8a0;
}
.term-cmd code {
  background: #0f1a18;
  color: #7fc8a0;
  padding: 1px 6px;
  border-radius: 4px;
}
iframe {
  flex: 1;
  width: 100%;
  border: 0;
  background: #0f1a18;
}
.term-off {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 6px;
  color: #bfd3cd;
  font-size: 14px;
}
.term-off code {
  color: #7fc8a0;
}
</style>
