<template>
  <!-- ══ 界面管理 ══ -->
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span class="card-title">界面管理</span>
        <span class="card-sub">全站一套外观，改完所有人生效</span>
      </div>
    </template>

    <el-form :model="form" label-width="110px" size="default" class="ui-form">
      <el-form-item label="站点标题">
        <el-input v-model="form.siteTitle" maxlength="32" show-word-limit placeholder="侧边栏左上角显示的名称" />
      </el-form-item>

      <el-form-item label="主题模式">
        <el-radio-group v-model="form.theme">
          <el-radio-button value="light">浅色</el-radio-button>
          <el-radio-button value="dark">深色</el-radio-button>
        </el-radio-group>
        <span class="hint">走 Element Plus 自带的深色变量表，不另写一套颜色。</span>
      </el-form-item>

      <el-form-item label="主色">
        <div class="swatch-row">
          <button
            v-for="c in PRESET_COLORS"
            :key="c"
            type="button"
            class="swatch"
            :class="{ active: normalizeColor(form.primaryColor) === c }"
            :style="{ background: c }"
            :title="c"
            @click="form.primaryColor = c"
          />
          <el-color-picker v-model="form.primaryColor" :predefine="PRESET_COLORS" />
          <el-input v-model="form.primaryColor" class="color-hex" maxlength="7" placeholder="#409eff" />
        </div>
        <span class="hint">Element Plus 主色，卡片/按钮/链接一并跟随。</span>
      </el-form-item>

      <el-form-item label="表格密度">
        <el-radio-group v-model="form.density">
          <el-radio-button value="default">默认</el-radio-button>
          <el-radio-button value="small">紧凑</el-radio-button>
          <el-radio-button value="large">宽松</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="侧边栏默认折叠">
        <el-switch v-model="form.sidebarCollapse" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存外观配置</el-button>
        <el-button @click="reset">恢复默认</el-button>
      </el-form-item>
    </el-form>

    <el-divider content-position="left">效果预览</el-divider>
    <div class="preview" :class="form.theme">
      <div class="pv-card">
        <div class="pv-title">巡检报告 · 2026-09-24</div>
        <div class="pv-line"><span class="pv-label">CPU</span><span class="pv-val">均值 12% ｜ 峰值 31%</span></div>
        <div class="pv-actions">
          <el-button type="primary" size="small">生成报告</el-button>
          <el-button size="small">导出</el-button>
          <el-button type="danger" size="small" plain>删除</el-button>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { reactive, ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useUiStore, UI_DEFAULTS } from '@/store/ui'
import { useUserStore } from '@/store/user'

const ui = useUiStore()
const userStore = useUserStore()
const saving = ref(false)

const PRESET_COLORS = [
  '#409eff', '#67c23a', '#e6a23c', '#f56c6c',
  '#9a60b4', '#2f8fd6', '#00a8a8', '#c05a9e',
]

const form = reactive({
  siteTitle: UI_DEFAULTS.siteTitle,
  theme: UI_DEFAULTS.theme,
  primaryColor: UI_DEFAULTS.primaryColor,
  density: UI_DEFAULTS.density,
  sidebarCollapse: UI_DEFAULTS.sidebarCollapse,
})

const normalizeColor = (c) => String(c || '').toLowerCase()

// 边改边预览（只动本地 ui store，没保存就不会写库）
watch(form, () => {
  ui.apply({
    siteTitle: form.siteTitle,
    theme: form.theme,
    primaryColor: form.primaryColor,
    density: form.density,
    sidebarCollapse: form.sidebarCollapse,
  })
}, { deep: true })

onMounted(async () => {
  if (!ui.loaded) await ui.load()
  form.siteTitle = ui.siteTitle
  form.theme = ui.theme
  form.primaryColor = ui.primaryColor
  form.density = ui.density
  form.sidebarCollapse = ui.sidebarCollapse
})

const canEdit = () => userStore.hasPerm('manage_system')

const save = async () => {
  if (!canEdit()) {
    ElMessage.warning('只有系统管理员能改外观配置')
    return
  }
  if (form.primaryColor && !/^#[0-9a-fA-F]{3,8}$/.test(form.primaryColor)) {
    ElMessage.warning('主色要是十六进制色值，例如 #409eff')
    return
  }
  saving.value = true
  try {
    ui.apply({ ...form })
    await ui.save()
    ElMessage.success('外观配置已保存，全站生效')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const reset = () => {
  form.siteTitle = UI_DEFAULTS.siteTitle
  form.theme = UI_DEFAULTS.theme
  form.primaryColor = UI_DEFAULTS.primaryColor
  form.density = UI_DEFAULTS.density
  form.sidebarCollapse = UI_DEFAULTS.sidebarCollapse
}
</script>

<style lang="scss" scoped>
.card-header { display: flex; align-items: center; gap: 10px; }
.card-title { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.card-sub { font-size: 12px; color: var(--el-text-color-secondary); }

.ui-form { max-width: 640px; }
.hint { margin-left: 12px; font-size: 12px; color: var(--el-text-color-secondary); }

.swatch-row { display: flex; align-items: center; gap: 8px; }
.swatch {
  width: 24px; height: 24px; border-radius: 4px; border: 2px solid transparent;
  cursor: pointer; padding: 0;
  &.active { border-color: var(--el-text-color-primary); }
  &:hover { transform: scale(1.08); }
}
.color-hex { width: 120px; margin-left: 4px; }

.preview {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-fill-color-light);
  &.dark { background: var(--el-bg-color-page, #141414); }
}
.pv-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
}
.pv-title { font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 10px; }
.pv-line { display: flex; gap: 12px; font-size: 13px; margin-bottom: 12px; }
.pv-label { width: 40px; color: var(--el-text-color-regular); }
.pv-val { color: var(--el-text-color-primary); font-family: ui-monospace, Menlo, Consolas, monospace; }
.pv-actions { display: flex; gap: 8px; }
</style>
