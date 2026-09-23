<template>
  <el-dialog v-model="blockConfigVisible" title="配置封堵参数" width="560px">
    <el-form label-width="90px">
      <el-form-item label="封堵脚本">
        <el-select v-model="blockConfig.scriptId" placeholder="选择用于封堵的脚本（来自脚本执行）" style="width:100%">
          <el-option v-for="s in scriptOptions" :key="s.id" :label="`${s.name}（${s.script_type}）`" :value="s.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="参数模板">
        <el-input v-model="blockConfig.paramsTemplate" type="textarea" :rows="6"
          placeholder="每行一个 KEY=VALUE，值中可用 {ip} 代表当前封禁 IP。&#10;例：&#10;BLOCK_IP={ip}&#10;BLOCK_REASON=high_freq_attack" />
      </el-form-item>
    </el-form>
    <div class="block-tip">脚本内通过环境变量读取参数（如 os.environ.get('BLOCK_IP')）。封堵脚本需避开安全检查黑名单（os/subprocess 等），建议用 urllib 调用防火墙/封堵 API 实现。</div>
    <template #footer>
      <el-button @click="blockConfigVisible = false">取消</el-button>
      <el-button type="primary" @click="saveBlockConfig">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { useAddresses } from '../composables/useAddresses'

const {
  blockConfigVisible,
  blockConfig,
  scriptOptions,
  saveBlockConfig
} = useAddresses()
</script>

<style lang="scss" scoped>
.block-tip { font-size: 12px; color: var(--el-text-color-secondary); padding: 0 0 8px 90px; line-height: 1.6; }
</style>
