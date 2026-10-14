<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand"><span class="logo">◆</span> DeepAgent</div>
      <h2>登录</h2>
      <p class="sub">登录后可使用前台对话或后台管理</p>
      <label class="field">
        <span>用户名</span>
        <input v-model="username" placeholder="用户名" autofocus />
      </label>
      <label class="field">
        <span>密码</span>
        <input v-model="password" type="password" placeholder="密码" @keyup.enter="submit" />
      </label>
      <div v-if="error" class="err">{{ error }}</div>
      <button class="submit" :disabled="loading" @click="submit">
        {{ loading ? '登录中…' : '登录' }}
      </button>
      <div class="hint">默认管理员账号：<code>admin</code> / <code>admin123</code></div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../auth'

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const route = useRoute()
const router = useRouter()

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value.trim(), password.value)
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  flex: 1; display: flex; align-items: center; justify-content: center;
  background: var(--bg); padding: 20px;
}
.login-card {
  width: 360px; max-width: 100%; background: var(--panel);
  border: 1px solid var(--border); border-radius: 16px; padding: 28px 26px;
  box-shadow: 0 10px 30px rgba(20, 22, 28, 0.06);
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 16px; }
.logo {
  width: 32px; height: 32px; border-radius: 9px;
  background: linear-gradient(135deg, #4f6ef7, #8b5cf6); color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 16px;
}
h2 { margin: 16px 0 4px; font-size: 20px; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 16px; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; font-size: 13px; color: var(--muted); }
.field input {
  border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
  font-size: 14px; background: var(--bg); color: var(--text);
}
.field input:focus { border-color: var(--accent); outline: none; }
.err { background: #fde8e8; color: #d93025; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.submit {
  width: 100%; border: none; background: var(--accent); color: #fff;
  padding: 11px; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 600;
}
.submit:disabled { opacity: 0.55; cursor: not-allowed; }
.hint { color: var(--muted); font-size: 12px; margin-top: 14px; text-align: center; }
.hint code { background: var(--code-bg); padding: 1px 6px; border-radius: 4px; }
</style>
