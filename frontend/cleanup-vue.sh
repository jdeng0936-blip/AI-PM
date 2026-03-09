#!/bin/bash
# ════════════════════════════════════════════════════════════════
# cleanup-vue.sh — 清理旧 Vue 3 前端文件
#
# 用法：cd frontend && bash cleanup-vue.sh
# ════════════════════════════════════════════════════════════════

set -e

echo "🧹 开始清理旧 Vue 文件..."

# Vue 模板/页面
rm -rf src/views
echo "  ✓ 已删除 src/views/"

# Vue Router
rm -rf src/router
echo "  ✓ 已删除 src/router/"

# Vue Composables
rm -rf src/composables
echo "  ✓ 已删除 src/composables/"

# 旧样式（已被 globals.css 替代）
rm -rf src/styles
echo "  ✓ 已删除 src/styles/"

# Vue 入口文件
rm -f src/App.vue src/main.ts
echo "  ✓ 已删除 App.vue, main.ts"

# Vite 配置（已被 next.config.js 替代）
rm -f vite.config.ts env.d.ts index.html
echo "  ✓ 已删除 vite.config.ts, env.d.ts, index.html"

# 旧构建产物和锁文件
rm -rf dist node_modules package-lock.json
echo "  ✓ 已删除 dist/, node_modules/, package-lock.json"

# 旧 Pinia store（已被 Zustand 替代）
rm -f src/stores/auth.ts
echo "  ✓ 已删除旧 Pinia store"

echo ""
echo "✅ 旧 Vue 文件清理完成！"
echo ""
echo "📦 接下来请执行："
echo "  npm install"
echo "  npm run build"
