/**
 * 界面外观（UI 管理）。全站一套，不是个人偏好 —— 存在后端 system_config 的
 * ui_* 键里，改完所有人生效。
 *
 * 配色基准仍是 Element Plus 浅色主题：这里只**换**主色 / 主题模式 / 密度，
 * 不引入第二套十六进制调色板。深色模式走 Element Plus 自带的 `html.dark`
 * 变量表，不在组件里写死深色颜色。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settings } from '@/api'

export const UI_DEFAULTS = {
  theme: 'light',
  primaryColor: '#409eff',
  density: 'default',
  sidebarCollapse: false,
  siteTitle: '安全巡检平台',
}

/** Element Plus 主色的 9 级派生表（light-3/5/7/8/9 + dark-2）。 */
function hexToRgb(hex) {
  const h = String(hex || '').replace('#', '')
  const n = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  if (!/^[0-9a-fA-F]{6}$/.test(n)) return [64, 158, 235]
  const int = parseInt(n, 16)
  return [(int >> 16) & 255, (int >> 8) & 255, int & 255]
}

function rgbToHex([r, g, b]) {
  const clamp = v => Math.round(Math.max(0, Math.min(255, v)))
  return '#' + [r, g, b].map(v => clamp(v).toString(16).padStart(2, '0')).join('')
}

/** `ratio` 是 `other` 所占的权重（不是主色的）。 */
function blend(hex, other, ratio) {
  const a = hexToRgb(hex)
  const b = hexToRgb(other)
  return rgbToHex(a.map((v, i) => v * (1 - ratio) + b[i] * ratio))
}

/**
 * Element Plus 的主色 9 级派生。对齐 `mix(白, 主色, N*10%)`：
 *
 *   light-N = N*10% 白 + (100-N)*10% 主色   →  N 越大越淡
 *   dark-2  = 20% 黑 + 80% 主色             →  更深
 *
 * 以默认主色 #409eff 验证：light-9 ≈ #ecf5ff（几乎白），light-3 ≈ #79bbff。
 *
 * 这里踩过一次：N 的比例写成了 (100-N)，整张表的明暗档全反了 —— light-9
 * 变成「几乎全主色」。而侧栏 `.is-active` / `el-button plain` 正是拿 light-9
 * 当底色再配主色文字，于是点一下就是蓝底蓝字，什么都看不清。
 */
export function primaryPalette(hex) {
  return {
    '--el-color-primary': hex,
    '--el-color-primary-light-3': blend(hex, '#ffffff', 0.3),
    '--el-color-primary-light-5': blend(hex, '#ffffff', 0.5),
    '--el-color-primary-light-7': blend(hex, '#ffffff', 0.7),
    '--el-color-primary-light-8': blend(hex, '#ffffff', 0.8),
    '--el-color-primary-light-9': blend(hex, '#ffffff', 0.9),
    '--el-color-primary-dark-2': blend(hex, '#000000', 0.2),
  }
}

export const useUiStore = defineStore('ui', () => {
  const theme = ref(UI_DEFAULTS.theme)
  const primaryColor = ref(UI_DEFAULTS.primaryColor)
  const density = ref(UI_DEFAULTS.density)
  const sidebarCollapse = ref(UI_DEFAULTS.sidebarCollapse)
  const siteTitle = ref(UI_DEFAULTS.siteTitle)
  const loaded = ref(false)

  function applyTheme() {
    document.documentElement.classList.toggle('dark', theme.value === 'dark')
  }

  function applyPrimary() {
    const vars = primaryPalette(primaryColor.value)
    for (const [k, v] of Object.entries(vars)) {
      document.documentElement.style.setProperty(k, v)
    }
  }

  function applyAll() {
    applyTheme()
    applyPrimary()
    // density 走 <el-config-provider :size>，由 App.vue 响应；标题由 MainLayout 读
  }

  function apply(cfg) {
    if (!cfg) return
    if (cfg.theme) theme.value = cfg.theme === 'dark' ? 'dark' : 'light'
    if (cfg.primaryColor && /^#[0-9a-fA-F]{3,8}$/.test(cfg.primaryColor)) {
      primaryColor.value = cfg.primaryColor
    }
    if (cfg.density) density.value = cfg.density
    if (cfg.sidebarCollapse !== undefined) sidebarCollapse.value = !!cfg.sidebarCollapse
    if (cfg.siteTitle) siteTitle.value = cfg.siteTitle
    applyAll()
  }

  function applySidebarCollapsed(v) {
    sidebarCollapse.value = !!v
  }

  async function load() {
    try {
      const res = await settings.getConfig()
      const flat = {}
      Object.values(res.data || {}).forEach(arr => arr.forEach(item => { flat[item.key] = item.value }))
      apply({
        theme: flat.ui_theme,
        primaryColor: flat.ui_primary_color,
        density: flat.ui_density,
        sidebarCollapse: String(flat.ui_sidebar_collapse).toLowerCase() === 'true',
        siteTitle: flat.ui_site_title,
      })
    } catch {
      // 未登录或接口不可用时用默认值；不要因为外观配置失败卡住启动
      applyAll()
    } finally {
      loaded.value = true
    }
  }

  async function save() {
    await settings.saveConfig({
      ui_theme: theme.value,
      ui_primary_color: primaryColor.value,
      ui_density: density.value,
      ui_sidebar_collapse: String(!!sidebarCollapse.value),
      ui_site_title: siteTitle.value,
    })
    applyAll()
  }

  return {
    theme, primaryColor, density, sidebarCollapse, siteTitle, loaded,
    apply, applyAll, applySidebarCollapsed, load, save,
  }
})
