<template>
  <div class="p-6 max-w-6xl mx-auto">
    <!-- 页头 -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-bold" style="color: var(--text-primary)">用户管理</h1>
        <p class="text-sm mt-1" style="color: var(--text-secondary)">管理系统用户账号、角色和权限</p>
      </div>
      <el-button type="primary" @click="openCreateDialog"
                 style="background: linear-gradient(135deg, #3b82f6, #6366f1); border: none">
        <el-icon class="mr-1"><Plus /></el-icon>
        新增用户
      </el-button>
    </div>

    <!-- 搜索栏 -->
    <div class="mb-4">
      <el-input v-model="searchText" placeholder="搜索姓名、部门、企微ID..." clearable
                prefix-icon="Search" style="max-width: 360px"
                @input="handleSearch" />
    </div>

    <!-- 用户表格 -->
    <div class="rounded-xl overflow-hidden" style="background: var(--bg-card); border: 1px solid var(--border-subtle)">
      <el-table :data="users" v-loading="loading" style="width: 100%"
                :header-cell-style="{ background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontWeight: 600 }"
                :cell-style="{ color: 'var(--text-primary)' }">
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="department" label="部门" width="120" />
        <el-table-column prop="phone" label="手机号" width="140">
          <template #default="{ row }">
            {{ row.phone || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="wechat_userid" label="企微ID" width="140" />
        <el-table-column prop="role" label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small" effect="dark"
                    style="border-radius: 6px">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small" effect="plain"
                    style="border-radius: 6px">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="warning" size="small" @click="handleResetPassword(row)">重置密码</el-button>
            <el-button link :type="row.is_active ? 'danger' : 'success'" size="small"
                       @click="handleToggleActive(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="flex justify-end mt-4">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="fetchUsers"
      />
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑用户' : '新增用户'" width="480px"
               :close-on-click-modal="false" destroy-on-close>
      <el-form :model="formData" label-width="80px" label-position="left">
        <el-form-item label="姓名" required>
          <el-input v-model="formData.name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="企微ID" required>
          <el-input v-model="formData.wechat_userid" placeholder="如 wx_zhangsan"
                    :disabled="isEditing" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="formData.phone" placeholder="可选，用于手机号登录" />
        </el-form-item>
        <el-form-item label="部门">
          <el-select v-model="formData.department" placeholder="选择部门" filterable allow-create>
            <el-option label="管理层" value="管理层" />
            <el-option label="软件研发部" value="软件研发部" />
            <el-option label="硬件测试部" value="硬件测试部" />
            <el-option label="采购部" value="采购部" />
            <el-option label="仓储物流部" value="仓储物流部" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="formData.role">
            <el-option label="普通员工" value="employee" />
            <el-option label="部门经理" value="manager" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="初始密码" v-if="!isEditing">
          <el-input v-model="formData.password" placeholder="默认 aipm2026" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting"
                   style="background: linear-gradient(135deg, #3b82f6, #6366f1); border: none">
          {{ isEditing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getUsers, createUser, updateUser, deleteUser, resetPassword } from '../api/users'

const users = ref<any[]>([])
const loading = ref(false)
const searchText = ref('')
const currentPage = ref(1)
const pageSize = 20
const total = ref(0)

// 弹窗状态
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref('')
const submitting = ref(false)
const formData = reactive({
  name: '',
  wechat_userid: '',
  phone: '',
  department: '',
  role: 'employee',
  password: 'aipm2026',
})

function roleLabel(role: string) {
  return { admin: '管理员', manager: '经理', employee: '员工' }[role] || role
}

function roleTagType(role: string) {
  return { admin: 'danger', manager: 'warning', employee: '' }[role] || ''
}

let searchTimer: any = null
function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    currentPage.value = 1
    fetchUsers()
  }, 300)
}

async function fetchUsers() {
  loading.value = true
  try {
    const res: any = await getUsers({
      page: currentPage.value,
      page_size: pageSize,
      search: searchText.value,
    })
    users.value = res.items
    total.value = res.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '获取用户列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  isEditing.value = false
  editingId.value = ''
  Object.assign(formData, {
    name: '', wechat_userid: '', phone: '', department: '', role: 'employee', password: 'aipm2026',
  })
  dialogVisible.value = true
}

function openEditDialog(row: any) {
  isEditing.value = true
  editingId.value = row.id
  Object.assign(formData, {
    name: row.name,
    wechat_userid: row.wechat_userid,
    phone: row.phone || '',
    department: row.department,
    role: row.role,
    password: '',
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formData.name || !formData.wechat_userid) {
    ElMessage.warning('请填写姓名和企微ID')
    return
  }
  submitting.value = true
  try {
    if (isEditing.value) {
      await updateUser(editingId.value, {
        name: formData.name,
        phone: formData.phone || undefined,
        department: formData.department,
        role: formData.role,
      })
      ElMessage.success('用户信息已更新')
    } else {
      await createUser({
        name: formData.name,
        wechat_userid: formData.wechat_userid,
        phone: formData.phone || undefined,
        department: formData.department,
        role: formData.role,
        password: formData.password || 'aipm2026',
      })
      ElMessage.success('用户创建成功')
    }
    dialogVisible.value = false
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function handleResetPassword(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定重置用户 "${row.name}" 的密码为 aipm2026？`, '重置密码',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await resetPassword(row.id)
    ElMessage.success(`${row.name} 的密码已重置为 aipm2026`)
  } catch {}
}

async function handleToggleActive(row: any) {
  const action = row.is_active ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      `确定${action}用户 "${row.name}"？`, `${action}用户`,
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    if (row.is_active) {
      await deleteUser(row.id)
    } else {
      await updateUser(row.id, { is_active: true })
    }
    ElMessage.success(`${row.name} 已${action}`)
    fetchUsers()
  } catch {}
}

onMounted(fetchUsers)
</script>
