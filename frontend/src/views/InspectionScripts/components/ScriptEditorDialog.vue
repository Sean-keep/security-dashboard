<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑脚本' : '新增脚本'"
    width="80%"
    top="5vh"
    destroy-on-close
    class="script-dialog"
  >
    <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="脚本名称" prop="name">
            <el-input v-model="form.name" placeholder="输入脚本名称" size="large" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="脚本类型" prop="script_type">
            <el-select v-model="form.script_type" style="width:100%" size="large">
              <el-option value="python" label="Python" />
              <el-option value="shell" label="Shell" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="脚本描述">
        <el-input v-model="form.description" placeholder="描述脚本功能" size="large" />
      </el-form-item>
      <el-form-item label="代码内容" prop="content">
        <div class="code-editor-wrapper">
          <div class="code-toolbar">
            <span class="code-lang">{{ form.script_type === 'python' ? 'Python' : 'Shell' }}</span>
            <el-button text size="small" @click="formatCode">格式化</el-button>
          </div>
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="20"
            placeholder="# 在此编写代码..."
            class="code-textarea"
          />
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="large" @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" size="large" :loading="saveLoading" @click="submitForm">
        <el-icon><Check /></el-icon> 保存脚本
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import { useScripts } from '../composables/useScripts'

const emit = defineEmits(['saved'])

const { createScript, updateScript } = useScripts()

const dialogVisible = ref(false)
const saveLoading = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const form = reactive({ name: '', script_type: 'python', description: '', content: '' })
const formRules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入代码内容', trigger: 'blur' }]
}

const openCreate = () => {
  isEdit.value = false; editingId.value = null
  Object.assign(form, { name: '', script_type: 'python', description: '', content: '' })
  dialogVisible.value = true
}

const editScript = (row) => {
  isEdit.value = true; editingId.value = row.id
  Object.assign(form, { name: row.name, script_type: row.script_type, description: row.description, content: row.content })
  dialogVisible.value = true
}

const formatCode = () => {
  // 简单的代码格式化提示
  ElMessage.info('代码格式化功能开发中')
}

const submitForm = async () => {
  try {
    await formRef.value.validate()
    saveLoading.value = true
    if (isEdit.value) {
      await updateScript(editingId.value, form)
      ElMessage.success('脚本已更新')
    } else {
      await createScript(form)
      ElMessage.success('脚本已创建')
    }
    dialogVisible.value = false
    emit('saved')
  } catch (e) {} finally { saveLoading.value = false }
}

defineExpose({ openCreate, editScript })
</script>

<style scoped>
/* 代码编辑器 */
.code-editor-wrapper {
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
}

.code-editor-wrapper.large {
  border-width: 2px;
}

.code-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
}

.code-lang {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.code-textarea :deep(.el-textarea__inner) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  padding: 16px;
  border: none;
  border-radius: 0;
  resize: none;
}

.code-textarea :deep(.el-textarea__inner):focus {
  box-shadow: none;
}

/* 脚本编辑对话框 */
.script-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
}
</style>
