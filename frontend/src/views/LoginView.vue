<template>
  <div class="login-wrap">
    <div class="login-card card">
      <div class="brand">
        <svg class="brand-mark" width="38" height="38" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="2" y="2" width="28" height="28" rx="8" fill="var(--primary-strong)"/>
          <circle cx="10" cy="10" r="3" fill="#fff"/>
          <circle cx="22" cy="10" r="3" fill="#fff"/>
          <circle cx="16" cy="22" r="3" fill="#fff"/>
          <path d="M10 10 L16 22 M22 10 L16 22" stroke="#fff" stroke-width="2" fill="none"/>
        </svg>
        <div>
          <div class="brand-name">AgentServer</div>
          <div class="brand-sub">AI 智能体管理平台</div>
        </div>
      </div>

      <form @submit.prevent="login" class="login-form">
        <label class="field">
          <span>用户名</span>
          <input class="input" type="text" v-model.trim="u" placeholder="请输入用户名" autocomplete="username" />
        </label>
        <label class="field">
          <span>密码</span>
          <input class="input" type="password" v-model="p" placeholder="请输入密码" autocomplete="current-password" />
        </label>

        <div v-if="error" class="err">{{ error }}</div>

        <button class="btn btn-primary login-submit" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登 录' }}
        </button>
      </form>
      <p class="hint">默认管理员：<b>admin / admin123</b>（请在登录后修改密码）</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login as authLogin } from '../auth'

const router = useRouter()
const u = ref('')
const p = ref('')
const error = ref('')
const loading = ref(false)

async function login() {
  error.value = ''
  if (!u.value || !p.value) { error.value = '请输入用户名和密码'; return }
  loading.value = true
  try {
    const ok = await authLogin(u.value, p.value)
    if (ok) { router.push('/') }
    else { error.value = '用户名或密码错误' }
  } catch (e) {
    error.value = '网络错误：' + (e?.message || e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100%; display: flex; align-items: center; justify-content: center;
  padding: 24px; background: var(--bg);
}
.login-card { width: 380px; max-width: 92vw; padding: 32px 30px; }
.brand { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.brand-name { font-weight: 700; font-size: 19px; color: var(--text); letter-spacing: -0.2px; }
.brand-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
.login-form { display: flex; flex-direction: column; }
.login-form .field { gap: 7px; }
.login-form .field > span { font-size: 13px; color: var(--text-2); font-weight: 500; }
.login-form .input { width: 100%; }
.login-submit { width: 100%; margin-top: 6px; padding: 11px; letter-spacing: 2px; }
.hint {
  margin: 18px 0 0; text-align: center; font-size: 12px; color: var(--muted);
}
.hint b { color: var(--text-2); }
</style>
