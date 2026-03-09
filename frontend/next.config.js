/** @type {import('next').NextConfig} */
const nextConfig = {
  // 生产部署使用 standalone 输出（Docker 优化）
  output: 'standalone',

  // 开发代理：将 /api/v1 请求代理到后端
  // Docker 环境中 BACKEND_URL=http://aipm-backend:8000
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ]
  },
}

module.exports = nextConfig

