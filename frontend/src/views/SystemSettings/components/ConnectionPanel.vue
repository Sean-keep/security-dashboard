<template>
  <div>
    <!-- ══ 连接设置（预览列表模式） ══ -->

    <!-- ES -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <div class="card-header">
          <span class="card-title">Elasticsearch</span>
          <div class="header-right">
            <el-tag :type="esTestResult?.connected ? 'success' : esTestResult ? 'danger' : 'info'" size="small">
              {{ esTestResult ? (esTestResult.connected ? '已连接' : '未连接') : '未测试' }}
            </el-tag>
            <el-button v-if="!editingEs" type="primary" link size="small" @click="startEditEs">编辑</el-button>
            <template v-else>
              <el-button type="default" size="small" @click="cancelEditEs">取消</el-button>
              <el-button type="primary" size="small" :loading="esSaving" @click="saveEs">保存</el-button>
            </template>
          </div>
        </div>
      </template>
      <!-- 预览模式 -->
      <div v-if="!editingEs" class="conn-preview">
        <div class="preview-row"><span class="preview-label">主机</span><span class="preview-val mono">{{ esForm.es_scheme }}://{{ esForm.es_host || '未配置' }}:{{ esForm.es_port }}</span></div>
        <div class="preview-row"><span class="preview-label">默认索引</span><span class="preview-val mono">{{ esForm.es_index || '未配置' }}</span></div>
        <div class="preview-row"><span class="preview-label">用户名</span><span class="preview-val">{{ esForm.es_user || '-' }}</span></div>
        <div class="preview-row"><span class="preview-label">密码</span><span class="preview-val">{{ secretSet.es_password ? '已配置' : '未配置' }}</span></div>
        <div class="preview-row"><span class="preview-label">忽略证书</span><span class="preview-val">{{ esForm.es_verify_certs === 'false' ? '是' : '否' }}</span></div>
      </div>
      <!-- 编辑模式 -->
      <el-form v-else :model="esForm" label-width="100px" size="default">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="主机地址"><el-input v-model="esForm.es_host" placeholder="35.241.110.62" /></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="协议"><el-select v-model="esForm.es_scheme" style="width:100%"><el-option label="HTTPS" value="https" /><el-option label="HTTP" value="http" /></el-select></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="端口"><el-input-number v-model="esForm.es_port" :min="1" :max="65535" style="width:100%" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="默认索引"><el-input v-model="esForm.es_index" placeholder="security-logs-*" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="用户名"><el-input v-model="esForm.es_user" placeholder="elastic" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="密码"><el-input v-model="esForm.es_password" type="password" show-password :placeholder="secretPlaceholder('es_password', '密码')" /></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="忽略证书"><el-switch v-model="esForm.es_verify_certs" active-value="false" inactive-value="true" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <div v-if="editingEs" class="card-footer">
        <el-button size="small" :loading="esTesting" @click="testEs">测试连接</el-button>
        <span v-if="esTestResult" class="test-msg" :class="esTestResult.connected ? 'ok' : 'fail'">{{ esTestResult.connected ? `连接成功 (${esTestResult.latency_ms ?? '?'}ms)` : `失败: ${esTestResult.error}` }}</span>
      </div>
    </el-card>

    <!-- MySQL -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <div class="card-header">
          <span class="card-title">MySQL</span>
          <div class="header-right">
            <el-tag :type="mysqlTestResult?.connected ? 'success' : mysqlTestResult ? 'danger' : 'info'" size="small">
              {{ mysqlTestResult ? (mysqlTestResult.connected ? '已连接' : '未连接') : '未测试' }}
            </el-tag>
            <el-button v-if="!editingMysql" type="primary" link size="small" @click="startEditMysql">编辑</el-button>
            <template v-else>
              <el-button type="default" size="small" @click="cancelEditMysql">取消</el-button>
              <el-button type="primary" size="small" :loading="mysqlSaving" @click="saveMysql">保存</el-button>
            </template>
          </div>
        </div>
      </template>
      <div v-if="!editingMysql" class="conn-preview">
        <div class="preview-row"><span class="preview-label">主机</span><span class="preview-val mono">{{ mysqlForm.mysql_host || '未配置' }}:{{ mysqlForm.mysql_port }}</span></div>
        <div class="preview-row"><span class="preview-label">数据库</span><span class="preview-val mono">{{ mysqlForm.mysql_database || '未配置' }}</span></div>
        <div class="preview-row"><span class="preview-label">用户名</span><span class="preview-val">{{ mysqlForm.mysql_user || '-' }}</span></div>
        <div class="preview-row"><span class="preview-label">密码</span><span class="preview-val">{{ secretSet.mysql_password ? '已配置' : '未配置' }}</span></div>
      </div>
      <el-form v-else :model="mysqlForm" label-width="100px" size="default">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="主机地址"><el-input v-model="mysqlForm.mysql_host" placeholder="localhost" /></el-form-item></el-col>
          <el-col :span="4"><el-form-item label="端口"><el-input-number v-model="mysqlForm.mysql_port" :min="1" :max="65535" style="width:100%" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="数据库名"><el-input v-model="mysqlForm.mysql_database" placeholder="security_dashboard" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="用户名"><el-input v-model="mysqlForm.mysql_user" placeholder="root" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="密码"><el-input v-model="mysqlForm.mysql_password" type="password" show-password :placeholder="secretPlaceholder('mysql_password', '密码')" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <div v-if="editingMysql" class="card-footer">
        <el-button size="small" :loading="mysqlTesting" @click="testMysql">测试连接</el-button>
        <span v-if="mysqlTestResult" class="test-msg" :class="mysqlTestResult.connected ? 'ok' : 'fail'">{{ mysqlTestResult.connected ? `连接成功 (${mysqlTestResult.latency_ms ?? '?'}ms)` : `失败: ${mysqlTestResult.error}` }}</span>
      </div>
    </el-card>

    <!-- Grafana -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <div class="card-header">
          <span class="card-title">Grafana</span>
          <div class="header-right">
            <el-tag :type="grafanaTestResult?.connected ? 'success' : grafanaTestResult ? 'danger' : 'info'" size="small">
              {{ grafanaTestResult ? (grafanaTestResult.connected ? '已连接' : '未连接') : '未测试' }}
            </el-tag>
            <el-button v-if="!editingGrafana" type="primary" link size="small" @click="startEditGrafana">编辑</el-button>
            <template v-else>
              <el-button type="default" size="small" @click="cancelEditGrafana">取消</el-button>
              <el-button type="primary" size="small" :loading="grafanaSaving" @click="saveGrafana">保存</el-button>
            </template>
          </div>
        </div>
      </template>
      <div v-if="!editingGrafana" class="conn-preview">
        <div class="preview-row"><span class="preview-label">服务地址</span><span class="preview-val mono">{{ grafanaForm.grafana_url || '未配置' }}</span></div>
        <div class="preview-row"><span class="preview-label">认证方式</span><span class="preview-val">{{ grafanaForm.grafana_auth_mode === 'apikey' ? 'API Key' : '用户名+密码' }}</span></div>
        <div v-if="grafanaForm.grafana_auth_mode === 'apikey'" class="preview-row"><span class="preview-label">API Key</span><span class="preview-val">{{ secretSet.grafana_api_key ? '已配置' : '未配置' }}</span></div>
        <div v-else class="preview-row"><span class="preview-label">密码</span><span class="preview-val">{{ secretSet.grafana_password ? '已配置' : '未配置' }}</span></div>
      </div>
      <el-form v-else :model="grafanaForm" label-width="100px" size="default">
        <el-form-item label="服务地址"><el-input v-model="grafanaForm.grafana_url" placeholder="http://localhost:3000" /></el-form-item>
        <el-form-item label="认证方式">
          <el-radio-group v-model="grafanaForm.grafana_auth_mode" size="default">
            <el-radio value="apikey">API Key（推荐）</el-radio>
            <el-radio value="basic">用户名 + 密码</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="grafanaForm.grafana_auth_mode === 'apikey'">
          <el-form-item label="API Key"><el-input v-model="grafanaForm.grafana_api_key" :placeholder="secretPlaceholder('grafana_api_key', 'Grafana API Key')" type="password" show-password /></el-form-item>
        </template>
        <template v-else>
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="用户名"><el-input v-model="grafanaForm.grafana_user" placeholder="Grafana 用户名" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="密码"><el-input v-model="grafanaForm.grafana_password" type="password" show-password :placeholder="secretPlaceholder('grafana_password', 'Grafana 密码')" /></el-form-item></el-col>
          </el-row>
        </template>
      </el-form>
      <div v-if="editingGrafana" class="card-footer">
        <el-button size="small" :loading="grafanaTesting" @click="testGrafana">测试连接</el-button>
        <span v-if="grafanaTestResult" class="test-msg" :class="grafanaTestResult.connected ? 'ok' : 'fail'">
          {{ grafanaTestResult.connected
            ? `连接成功${grafanaTestResult.version ? ` (v${grafanaTestResult.version})` : ''}`
            : `失败: ${grafanaTestResult.stage === 'auth_invalid' ? 'Token无效（请检查Key是否过期）' : grafanaTestResult.stage === 'auth_forbidden' ? '代理/CDN拦截（建议直接IP访问）' : (grafanaTestResult.error || '连接失败')}` }}
        </span>
      </div>
    </el-card>

  </div>
</template>

<script setup>
import { useSystemSettings } from '../composables/useSystemSettings'

const {
  esForm,
  mysqlForm,
  grafanaForm,
  secretSet,
  secretPlaceholder,
  esSaving,
  esTesting,
  esTestResult,
  mysqlSaving,
  mysqlTesting,
  mysqlTestResult,
  grafanaSaving,
  grafanaTesting,
  grafanaTestResult,
  editingEs,
  editingMysql,
  editingGrafana,
  startEditEs,
  cancelEditEs,
  startEditMysql,
  cancelEditMysql,
  startEditGrafana,
  cancelEditGrafana,
  saveEs,
  testEs,
  saveMysql,
  testMysql,
  saveGrafana,
  testGrafana
} = useSystemSettings()
</script>

<style lang="scss" scoped>
.mb-16 { margin-bottom: 16px; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.conn-preview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px 24px;
}
.preview-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.preview-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  min-width: 56px;
  flex-shrink: 0;
}
.preview-val {
  font-size: 13px;
  color: var(--el-text-color-primary);
  word-break: break-all;
}
.preview-val.mono {
  font-family: 'Courier New', monospace;
  color: var(--el-color-primary);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.test-msg {
  font-size: 13px;
  margin-left: 4px;
  &.ok { color: var(--el-color-success); }
  &.fail { color: var(--el-color-danger); }
}
</style>
