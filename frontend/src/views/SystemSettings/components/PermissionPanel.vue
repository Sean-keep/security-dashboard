<template>
  <!-- ══ 权限管理 · 三权分立 ══
       矩阵落库，系统管理员可在下面勾选分配。三条底线勾不破：三权互斥、
       三权独占、三权必须有人接 —— 后端 validate_role_matrix 硬校验，这里
       的交互只是让它在点的当下就表现出来。 -->
  <el-card shadow="never" class="mb-16">
    <template #header>
      <div class="card-header">
        <span class="card-title">权限管理 · 三权分立</span>
        <el-tag v-if="canAssign" type="warning" size="small" effect="plain">系统管理员可勾选分配</el-tag>
        <el-tag v-else type="info" size="small" effect="plain">只读</el-tag>
        <span class="spacer" />
        <template v-if="canAssign">
          <el-button size="small" :disabled="!dirty" @click="resetDraft">还原</el-button>
          <el-button size="small" @click="restoreDefaults">恢复默认</el-button>
          <el-button size="small" type="primary" :loading="saving" :disabled="!dirty" @click="save">
            保存矩阵
          </el-button>
        </template>
      </div>
    </template>

    <el-alert type="info" :closable="false" class="mb-16">
      <template #title>
        账号管理 / 授权 / 审计 三项权力分别落在三个不同角色上，<b>任何用户都不能同时持有其中两项</b>。
        于是没有人能「建个号、给上权、再把痕迹抹掉」。
        <template v-if="canAssign">
          <br />三权三列<b>只能转移，不能空置也不能并存</b>：点一下就把钥匙挪到这个角色手上。
          系统配置 / 安全业务可随意勾。
        </template>
      </template>
    </el-alert>

    <div class="power-grid mb-16">
      <div v-for="p in powerDefs" :key="p.name" class="power-card">
        <div class="power-name">{{ p.label }}</div>
        <div class="power-holder">
          <el-tag :type="roleTag(holderOf(p.name)?.role)" size="small">
            {{ holderOf(p.name)?.label || '—' }}
          </el-tag>
        </div>
        <div class="power-desc">{{ plain(p.desc) }}</div>
      </div>
    </div>

    <el-table :data="rows" border size="small" class="matrix-table">
      <el-table-column prop="label" label="角色" width="130" fixed="left">
        <template #default="{ row }">
          <div class="role-cell">
            <el-tag :type="roleTag(row.role)" size="small">{{ row.label }}</el-tag>
            <span class="role-hint" v-if="row.isMine">（我）</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        v-for="p in permissionDefs"
        :key="p.name"
        :label="p.label"
        width="110"
        align="center"
      >
        <template #header>
          <div class="th-cell" :class="{ power: p.power }">
            <span>{{ p.label }}</span>
            <span class="th-star" v-if="p.power">三权</span>
          </div>
        </template>
        <template #default="{ row }">
          <!-- 三权列：勾上 = 把钥匙挪过来。已持有则禁用 —— 想交出去得去勾别的角色 -->
          <el-checkbox
            v-if="p.power"
            :model-value="granted(row.role, p.name)"
            :disabled="!canAssign || granted(row.role, p.name)"
            :title="granted(row.role, p.name) ? '钥匙在这个角色手上 —— 点别的角色把它挪走' : '点一下把这把钥匙挪过来'"
            @change="(v) => toggle(row.role, p.name, v)"
          />
          <!-- 其余两列：随意勾 -->
          <el-checkbox
            v-else-if="canAssign"
            :model-value="granted(row.role, p.name)"
            @change="(v) => toggle(row.role, p.name, v)"
          />
          <el-icon v-else-if="granted(row.role, p.name)" class="yes"><CircleCheckFilled /></el-icon>
          <el-icon v-else class="no"><Minus /></el-icon>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="说明" min-width="260" show-overflow-tooltip />
    </el-table>

    <div v-if="canAssign && dirty" class="dirty-note">
      有未保存的改动。改完记得点右上角「保存矩阵」—— 权限在下一次请求就生效，不用重启。
    </div>
  </el-card>

  <!-- 三权在任者 -->
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span class="card-title">三权在任者</span>
        <span class="card-sub">谁握着哪把钥匙</span>
      </div>
    </template>

    <el-empty v-if="!users.length" description="暂无可列出的用户（需要账号管理或授权权限）" />

    <div v-else class="holder-grid">
      <div v-for="p in powerDefs" :key="p.name" class="holder-block">
        <div class="holder-title">
          <el-tag :type="roleTag(holderOf(p.name)?.role)" size="small" effect="dark">{{ p.label }}</el-tag>
          <span class="holder-count">{{ holdersOf(p.name).length }} 人</span>
        </div>
        <div class="holder-list">
          <el-tag
            v-for="u in holdersOf(p.name)"
            :key="u.id"
            size="small"
            effect="plain"
            class="holder-tag"
          >
            {{ u.nickname || u.username }}
            <span class="holder-user" v-if="u.nickname">（{{ u.username }}）</span>
          </el-tag>
          <span v-if="!holdersOf(p.name).length" class="holder-empty">无人在任 —— 这把钥匙等于丢了</span>
        </div>
      </div>
    </div>
    <div v-if="!canSeeUsers" class="holder-note">
      当前角色无权列出用户，看不到具体在任者。矩阵本身如上表。
    </div>
  </el-card>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleCheckFilled, Minus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import { settings } from '@/api'
import {
  PERMISSION_DEFS, ROLE_LABELS, ROLE_PERMISSIONS, roleTag,
} from '@/config/roles'

const userStore = useUserStore()
const users = ref([])
const backendRows = ref([])
const defaults = ref({})

// 草稿：{ role: [permissionName, ...] }。整张矩阵一次提交 —— 三权独占是跨角色约束。
const draft = ref(null)
const baseline = ref('')
const saving = ref(false)

const permissionDefs = PERMISSION_DEFS
const powerDefs = PERMISSION_DEFS.filter(p => p.power)

// 说明文案里的 ** 只是书写记号，渲染时去掉。不走 v-html —— 那是给自己挖洞。
const plain = (s) => String(s || '').replace(/\*\*/g, '')

const canSeeUsers = computed(() => userStore.hasPerm('manage_accounts', 'manage_authz'))
// 系统管理员（manage_accounts）和安全管理员（manage_authz）都能改岗位职责表
const canAssign = computed(() => userStore.hasPerm('manage_accounts', 'manage_authz'))

const serialize = (d) => JSON.stringify(
  Object.keys(d).sort().map(r => [r, [...(d[r] || [])].sort()])
)
const dirty = computed(() => {
  if (!draft.value || !baseline.value) return false
  return serialize(draft.value) !== baseline.value
})

const granted = (role, name) => (draft.value?.[role] || []).includes(name)

// 后端矩阵是事实来源；拉不到时用本地默认先渲染成可编辑的草稿
const rows = computed(() => {
  const mine = userStore.role
  const src = backendRows.value.length
    ? backendRows.value.map(r => ({
        role: r.role,
        label: r.label,
        description: r.description,
      }))
    : Object.keys(ROLE_LABELS).map(role => ({
        role,
        label: ROLE_LABELS[role],
        description: '',
      }))
  return src.map(r => ({ ...r, isMine: r.role === mine }))
})

const applyMatrix = (rolesArr) => {
  const d = {}
  for (const r of rolesArr) {
    d[r.role] = (r.permissions || []).filter(p => p.granted).map(p => p.name)
  }
  // 后端必须给全角色，缺的补空，免得 toggle 时写到 undefined 上
  for (const role of Object.keys(ROLE_LABELS)) {
    if (!d[role]) d[role] = []
  }
  draft.value = d
  baseline.value = serialize(d)
}

const toggle = (role, name, checked) => {
  if (!draft.value) return
  const def = PERMISSION_DEFS.find(p => p.name === name)
  const next = { ...draft.value }

  if (checked) {
    next[role] = [...(next[role] || []), name]
    // 三权独占：挪钥匙 = 把别人手上的同一把先收回来
    if (def?.power) {
      for (const r of Object.keys(next)) {
        if (r !== role) next[r] = (next[r] || []).filter(p => p !== name)
      }
    }
  } else {
    // 三权不能空置。想交出去就去点别的角色，那样会自动从这里收走
    if (def?.power) {
      ElMessage.warning('三权每项必须有且仅有一个在任者 —— 点别的角色把钥匙挪过去')
      return
    }
    next[role] = (next[role] || []).filter(p => p !== name)
  }
  draft.value = next
}

const resetDraft = () => {
  if (backendRows.value.length) applyMatrix(backendRows.value)
  else applyMatrix(Object.entries(ROLE_PERMISSIONS).map(([role, names]) => ({
    role,
    permissions: names.map(n => ({ name: n, granted: true })),
  })))
}

const restoreDefaults = () => {
  const src = defaults.value && Object.keys(defaults.value).length
    ? defaults.value
    : ROLE_PERMISSIONS
  const d = {}
  for (const role of Object.keys(ROLE_LABELS)) {
    d[role] = [...(src[role] || [])]
  }
  draft.value = d
  ElMessage.info('已填入默认矩阵 —— 点「保存矩阵」才真正写库')
}

// 「三权」的独占角色：以草稿为准，点到哪算哪
const holderOf = (power) => {
  const role = Object.keys(draft.value || {}).find(r => (draft.value[r] || []).includes(power))
  if (!role) return null
  return { role, label: ROLE_LABELS[role] || role }
}

const LEGACY = { admin: 'sys_admin' }
const normalize = (r) => (ROLE_LABELS[r] ? r : (LEGACY[r] || 'viewer'))

const holdersOf = (power) => {
  const role = holderOf(power)?.role
  if (!role) return []
  return users.value.filter(u => normalize(u.role) === role)
}

const save = async () => {
  saving.value = true
  try {
    const res = await settings.savePermissions(draft.value)
    const rolesArr = res.data?.roles
    if (rolesArr) {
      backendRows.value = rolesArr
      applyMatrix(rolesArr)
    } else {
      baseline.value = serialize(draft.value)
    }
    ElMessage.success('权限矩阵已保存，下一次请求生效')
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const res = await settings.getPermissions()
    backendRows.value = res.data?.roles || []
    defaults.value = res.data?.defaults || {}
  } catch { /* 本地副本兜底 */ }
  resetDraft()

  if (!canSeeUsers.value) return
  try {
    users.value = (await settings.users()).data || []
  } catch { /* 看不到就只显示矩阵 */ }
})
</script>

<style lang="scss" scoped>
.mb-16 { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.card-title { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.card-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.spacer { flex: 1; }
.dirty-note {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-color-warning);
}

.power-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.power-card {
  border: 1px solid var(--el-color-warning-light-5);
  border-left: 3px solid var(--el-color-warning);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--el-color-warning-light-9);
}
.power-name { font-weight: 700; font-size: 14px; color: var(--el-text-color-primary); margin-bottom: 8px; }
.power-holder { margin-bottom: 8px; }
.power-desc { font-size: 12px; line-height: 1.6; color: var(--el-text-color-regular); }

.matrix-table {
  :deep(.th-cell) {
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    &.power { color: var(--el-color-warning); font-weight: 700; }
  }
  .th-star { font-size: 10px; font-weight: 400; color: var(--el-color-warning); }
  .role-cell { display: flex; align-items: center; gap: 4px; }
  .role-hint { font-size: 11px; color: var(--el-color-primary); }
  .yes { color: var(--el-color-success); font-size: 16px; }
  .no  { color: var(--el-text-color-placeholder); font-size: 14px; }
  :deep(.el-checkbox) {
    height: 22px; // 表格行里别把行高顶开
  }
}

.holder-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.holder-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
}
.holder-title { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.holder-count { font-size: 12px; color: var(--el-text-color-secondary); }
.holder-list { display: flex; flex-wrap: wrap; gap: 6px; }
.holder-user { color: var(--el-text-color-secondary); font-size: 11px; margin-left: 2px; }
.holder-empty { font-size: 12px; color: var(--el-color-danger); }
.holder-note { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>
