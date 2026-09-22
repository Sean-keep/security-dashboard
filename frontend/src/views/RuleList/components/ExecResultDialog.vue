<template>
  <el-dialog
    :model-value="modelValue"
    title="执行结果"
    width="600px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="result" class="execute-result">
      <el-result :icon="result.written > 0 ? 'success' : 'info'" :title="result.msg">
        <template #sub-title>
          <p>查询记录：{{ result.total }} 条</p>
          <p>写入MySQL：{{ result.written }} 条</p>
        </template>
      </el-result>
    </div>
  </el-dialog>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  result: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue'])
</script>

<style lang="scss" scoped>
.execute-result { }
</style>
