<template>
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px" destroy-on-close>
    <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
      <el-form-item label="攻击地址" prop="ip_address">
        <el-input v-model="form.ip_address" placeholder="例：1.2.3.4" />
      </el-form-item>
      <el-form-item label="所属国家">
        <div style="display:flex;gap:8px;align-items:center">
          <el-input v-model="form.country" placeholder="手动修改或点击查询，如：中国、美国" style="flex:1" />
          <el-button size="small" @click="queryCountryForForm" :loading="countryQueryLoading" :disabled="!form.ip_address">查询归属</el-button>
        </div>
      </el-form-item>
      <el-form-item label="攻击域名">
        <el-input v-model="form.domain" placeholder="例：example.com" />
      </el-form-item>
      <el-form-item label="首次攻击时间">
        <el-date-picker v-model="form.start_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" />
      </el-form-item>
      <el-form-item label="最近攻击时间">
        <el-date-picker v-model="form.end_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" />
      </el-form-item>
      <el-form-item label="攻击次数">
        <el-input-number v-model="form.attack_count" :min="0" style="width:100%" />
      </el-form-item>
      <el-form-item label="持续时间(秒)">
        <el-input-number v-model="form.duration" :min="0" style="width:100%" />
      </el-form-item>
      <el-form-item label="威胁等级">
        <el-select v-model="form.severity" style="width:100%">
          <el-option label="低危" value="low" />
          <el-option label="中危" value="medium" />
          <el-option label="高危" value="high" />
          <el-option label="严重" value="critical" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" style="width:100%">
          <el-option label="活跃" value="active" />
          <el-option label="已封禁" value="blocked" />
          <el-option label="白名单" value="whitelist" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源">
        <el-input v-model="form.source" placeholder="来源说明" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="备注信息" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saveLoading" @click="submitForm">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { useAddresses } from '../composables/useAddresses'

const {
  dialogVisible,
  dialogTitle,
  form,
  formRules,
  formRef,
  saveLoading,
  countryQueryLoading,
  queryCountryForForm,
  submitForm
} = useAddresses()
</script>
