<template>
  <!-- density（表格密度）走 el-config-provider，不能写死在 app.use(ElementPlus, { size }) ——
       那个只在启动时读一次，改了不生效。 -->
  <el-config-provider :size="ui.density">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { useUiStore } from '@/store/ui'

const ui = useUiStore()
</script>
