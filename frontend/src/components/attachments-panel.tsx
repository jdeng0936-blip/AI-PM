'use client'

import { useEffect, useRef, useState } from 'react'
import {
  uploadAttachment,
  deleteAttachment,
  transcribeAudio,
  getAsrStatus,
  type Attachment,
  type AsrStatus,
} from '@/api/attachments'

interface Props {
  /** 上传完成回调,父组件可拿到所有附件 id 在提交日报时一起带上 */
  onChange?: (attachments: Attachment[]) => void
  /** 录音转写完成回调,父组件可用来自动填入文本框 */
  onTranscribed?: (text: string) => void
}

const MAX_BYTES = 25 * 1024 * 1024

function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / (1024 * 1024)).toFixed(1)}MB`
}

function kindBadge(kind: Attachment['kind']): string {
  return { image: '🖼️', voice: '🎤', document: '📄', other: '📎' }[kind] || '📎'
}

export default function AttachmentsPanel({ onChange, onTranscribed }: Props) {
  const [files, setFiles] = useState<Attachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  // 录音状态
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const [asrStatus, setAsrStatus] = useState<AsrStatus | null>(null)

  useEffect(() => {
    getAsrStatus()
      .then(setAsrStatus)
      .catch(() => setAsrStatus({ configured: false, provider: 'none' }))
  }, [])

  useEffect(() => {
    onChange?.(files)
  }, [files, onChange])

  // ── 文件上传 ──
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files
    if (!list || list.length === 0) return
    setError('')
    setUploading(true)
    try {
      for (const file of Array.from(list)) {
        if (file.size > MAX_BYTES) {
          setError(`${file.name} 超过 25MB 上限`)
          continue
        }
        const att = await uploadAttachment(file)
        setFiles((prev) => [...prev, att])
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || '上传失败')
    } finally {
      setUploading(false)
      // 允许重复选同一个文件
      e.target.value = ''
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteAttachment(id)
      setFiles((prev) => prev.filter((f) => f.id !== id))
    } catch {
      setError('删除失败')
    }
  }

  // ── 录音 ──
  const startRecording = async () => {
    setError('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('浏览器不支持录音')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      audioChunksRef.current = []
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) audioChunksRef.current.push(ev.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        await uploadAndTranscribe(blob)
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setRecording(true)
    } catch (err: any) {
      setError(err?.message || '麦克风权限被拒绝')
    }
  }

  const stopRecording = () => {
    mediaRecorderRef.current?.stop()
    setRecording(false)
  }

  const uploadAndTranscribe = async (blob: Blob) => {
    setTranscribing(true)
    setError('')
    try {
      const res = await transcribeAudio(blob, {
        save_attachment: true,
        file_name: `voice_${Date.now()}.webm`,
      })
      if (!res.configured) {
        setError('后端 ASR 未配置,仅保存了录音文件')
      } else if (!res.transcript) {
        setError('转写失败,可重试或手动输入')
      } else {
        onTranscribed?.(res.transcript)
      }
      // 如果服务端落库为附件,把它加进列表
      if (res.attachment_id && res.file_url) {
        setFiles((prev) => [
          ...prev,
          {
            id: res.attachment_id!,
            uploaded_by: '',
            kind: 'voice',
            file_name: `voice_${Date.now()}.webm`,
            mime_type: 'audio/webm',
            size_bytes: blob.size,
            file_url: res.file_url!,
            transcript: res.transcript,
          },
        ])
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || '转写请求失败')
    } finally {
      setTranscribing(false)
    }
  }

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200">
          📎 附件 & 🎤 语音输入
        </h3>
        {asrStatus && (
          <span className="text-xs text-gray-400">
            ASR:{' '}
            {asrStatus.configured ? (
              <span className="text-emerald-400">
                ✓ {asrStatus.provider}
              </span>
            ) : (
              <span className="text-amber-400">未配置</span>
            )}
          </span>
        )}
      </div>

      {/* 操作按钮区 */}
      <div className="flex flex-wrap items-center gap-2">
        <label className="cursor-pointer rounded-md bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-500 disabled:opacity-50">
          {uploading ? '上传中...' : '📷 选择文件'}
          <input
            type="file"
            multiple
            className="hidden"
            disabled={uploading}
            onChange={handleFileSelect}
            accept="image/*,audio/*,application/pdf,.doc,.docx,.xls,.xlsx,.txt"
          />
        </label>

        {!recording ? (
          <button
            type="button"
            disabled={transcribing}
            onClick={startRecording}
            className="rounded-md bg-rose-600 px-3 py-1.5 text-sm text-white hover:bg-rose-500 disabled:opacity-50"
          >
            {transcribing ? '🤖 转写中...' : '🎤 开始录音'}
          </button>
        ) : (
          <button
            type="button"
            onClick={stopRecording}
            className="rounded-md bg-amber-600 px-3 py-1.5 text-sm text-white hover:bg-amber-500"
          >
            ⏹ 停止并转写
          </button>
        )}

        {recording && (
          <span className="text-xs text-rose-400 animate-pulse">● 正在录音</span>
        )}
      </div>

      {error && (
        <div className="rounded bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* 已上传列表 */}
      {files.length > 0 && (
        <div className="space-y-1">
          {files.map((f) => (
            <div
              key={f.id}
              className="flex items-center justify-between rounded bg-gray-900/50 px-3 py-1.5 text-sm"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span>{kindBadge(f.kind)}</span>
                <a
                  href={f.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate text-gray-200 hover:text-indigo-400"
                  title={f.file_name}
                >
                  {f.file_name}
                </a>
                <span className="shrink-0 text-xs text-gray-500">
                  {formatBytes(f.size_bytes)}
                </span>
                {f.transcript && (
                  <span
                    className="ml-2 truncate text-xs text-emerald-400"
                    title={f.transcript}
                  >
                    &ldquo;{f.transcript.slice(0, 30)}
                    {f.transcript.length > 30 ? '...' : ''}&rdquo;
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={() => handleDelete(f.id)}
                className="ml-2 text-xs text-gray-400 hover:text-red-400"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
