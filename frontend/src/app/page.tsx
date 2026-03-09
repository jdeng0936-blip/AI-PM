/**
 * app/page.tsx — 根路由重定向到 /dashboard
 */
import { redirect } from 'next/navigation'

export default function Home() {
  redirect('/dashboard')
}
