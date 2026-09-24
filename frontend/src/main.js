import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
// 深色变量表。界面管理切到 dark 时给 <html> 加 .dark，整套 --el-* 随之翻转。
// 不引入：切换时只剩组件局部样式会变成「半深不浅」的一片。
import 'element-plus/theme-chalk/dark/css-vars.css'
// 全局 token 与 Element Plus 覆盖。必须在 element-plus 样式之后引入，
// 这里的 --el-* 用法与 .el-card / .el-table 覆盖才能压过默认值。
// （此前该文件从未被 import，等于一整份全局样式是死代码。）
import './assets/styles/global.scss'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import router from './router'
import App from './App.vue'

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn, size: 'default', zIndex: 3000 })
app.mount('#app')
