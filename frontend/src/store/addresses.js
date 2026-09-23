import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

// 地址列表共享状态。原先散落在 useAddresses.js 模块作用域（非 Pinia），
// multipleSelection 会跨路由残留，批量操作可能打到用户已看不到的行。
// 这里集中到 Pinia，loadData 每次开始时清空 multipleSelection。
export const useAddressesStore = defineStore('addresses', () => {
  const tableRef = ref()
  const tableData = ref([])
  const total = ref(0)
  const multipleSelection = ref([])
  const loading = ref(false)
  const error = ref(null)

  const dialogVisible = ref(false)
  const saveLoading = ref(false)
  const isEdit = ref(false)
  const editId = ref(null)
  const formRef = ref()

  const filterForm = reactive({ keyword: '', severity: '', status: '' })
  const timePreset = ref('today')
  const pagination = reactive({ page: 1, page_size: 20 })
  const sortMeta = reactive({ sort_field: 'created_at', sort_order: 'desc' })
  // 用普通对象记录正在查询的 IP（key=IP, val=true），替换而非修改，保证 Vue 响应式
  const countryLoadingMap = reactive({})  // { '1.2.3.4': true }

  const form = ref({
    ip_address: '', country: '', domain: '',
    start_time: '', end_time: '',
    attack_count: 0, duration: 0,
    severity: 'medium', status: 'active',
    source: '', remark: ''
  })

  const countryQueryLoading = ref(false)

  // ── 封禁功能状态 ──
  const blockConfigVisible = ref(false)
  const blockResultVisible = ref(false)
  const blockRunning = ref(false)
  const blockResults = ref([])
  const scriptOptions = ref([])
  const blockConfig = reactive({ scriptId: null, paramsTemplate: '' })

  return {
    tableRef, tableData, total, multipleSelection, loading, error,
    dialogVisible, saveLoading, isEdit, editId, formRef,
    filterForm, timePreset, pagination, sortMeta, countryLoadingMap,
    form, countryQueryLoading,
    blockConfigVisible, blockResultVisible, blockRunning, blockResults,
    scriptOptions, blockConfig
  }
})
