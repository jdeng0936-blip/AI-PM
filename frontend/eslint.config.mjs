// ESLint 9 flat config(Stage 1:从 `next lint` 迁移到 ESLint CLI)
//
// Next.js 15 推荐做法:用 FlatCompat 加载 next/core-web-vitals + next/typescript presets。
// 一旦 eslint-config-next 完全支持 flat config(预计 Next 16),
// 可改为直接 import。
import { FlatCompat } from '@eslint/eslintrc'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const compat = new FlatCompat({
  baseDirectory: __dirname,
})

export default [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'dist/**',
      'out/**',
      'next-env.d.ts',
      'env.d.ts',          // process.env 类型扩展,用 {} 是 declaration merging 习惯
      'next.config.js',    // CommonJS 配置文件,无法用 ESM import
      // Sentry config 文件 import @sentry/nextjs,某些规则不适用
      'sentry.*.config.ts',
      'instrumentation.ts',
    ],
  },
  ...compat.config({
    extends: ['next/core-web-vitals', 'next/typescript'],
  }),
  {
    // 项目级 rule 调整
    rules: {
      // 历史代码中有较多 any,Stage 1 后续子任务再逐步收紧
      '@typescript-eslint/no-explicit-any': 'off',
      // 与 SQLAlchemy 后端类似:`if (x == true)` 在 TS 里也有合法场景(对比 enum)
      'eqeqeq': ['error', 'smart'],
    },
  },
]
