import React, { useEffect, useState } from 'react'
import { Button, Codicon, COMPOSER_AREAS, host, useValue } from '@hermes/plugin-sdk'

const ACTIVE_KEY = 'active-request'
const ACTIVE_EVENT = 'quansyn:active-request'
let api = null

function visibleComposerTarget() {
  const rows = Array.from(document.querySelectorAll('[data-composer-target]'))
  const visible = rows.find(node => node instanceof HTMLElement && node.offsetParent !== null)
  return visible?.dataset?.composerTarget || 'main'
}

function insertIntoComposer(text) {
  window.dispatchEvent(new CustomEvent('hermes:composer-insert', {
    detail: { mode: 'block', target: visibleComposerTarget(), text }
  }))
  window.dispatchEvent(new CustomEvent('hermes:composer-focus', {
    detail: { target: visibleComposerTarget() }
  }))
}

function readActive() {
  return api?.storage.get(ACTIVE_KEY, null) || null
}

function writeActive(value) {
  if (value) api.storage.set(ACTIVE_KEY, value)
  else api.storage.remove(ACTIVE_KEY)
  window.dispatchEvent(new CustomEvent(ACTIVE_EVENT, { detail: value }))
}

function activeForSession(sessionId) {
  const active = readActive()
  if (!active) throw new Error('没有活动的 QuanSyn 请求，请先点击“拉取到输入框”')
  if (active.sessionId && sessionId && active.sessionId !== sessionId) {
    throw new Error('当前聊天不是拉取该问题时的聊天，请切回原聊天后再推送')
  }
  if (!sessionId) throw new Error('当前聊天尚未建立会话，请先发送拉取的问题并等待回答')
  if (!active.sessionId) {
    active.sessionId = sessionId
    writeActive(active)
  }
  return active
}

function copyCommandBody(text) {
  const trimmed = text.trim()
  if (/^\/copy(?:\s|$)/i.test(trimmed)) return trimmed.replace(/^\/copy(?:\s+|$)/i, '').trim()
  if (/(?:^|\n)\/copy\s*$/i.test(trimmed)) return trimmed.replace(/(?:^|\n)\/copy\s*$/i, '').trim()
  return null
}

async function publishLast() {
  const sessionId = host.state.focusedSessionId.get()
  const active = activeForSession(sessionId)
  const receipt = await api.rest('/desktop/push-last', {
    method: 'POST',
    body: { transfer_id: active.transferId, session_id: sessionId },
    timeoutMs: 70_000
  })
  writeActive(null)
  host.notify({ kind: 'success', message: `已推送到 QuanSyn：${receipt.result_id}` })
}

async function publishCopy(text) {
  const sessionId = host.state.focusedSessionId.get()
  const active = activeForSession(sessionId)
  if (!text) throw new Error('请把正文写在 /copy 后面，或把 /copy 放在正文最后一行')
  const receipt = await api.rest('/desktop/push-copy', {
    method: 'POST',
    body: { transfer_id: active.transferId, text },
    timeoutMs: 70_000
  })
  writeActive(null)
  host.notify({ kind: 'success', message: `已复制到 QuanSyn：${receipt.result_id}` })
}

function QuanSynPullButton() {
  const sessionId = useValue(host.state.focusedSessionId)
  const [active, setActive] = useState(() => readActive())
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const listener = event => setActive(event.detail || null)
    window.addEventListener(ACTIVE_EVENT, listener)
    return () => window.removeEventListener(ACTIVE_EVENT, listener)
  }, [])

  useEffect(() => {
    if (active && !active.sessionId && sessionId) {
      const bound = { ...active, sessionId }
      writeActive(bound)
      setActive(bound)
    }
  }, [active, sessionId])

  const pull = async () => {
    if (busy) return
    if (active) {
      host.notify({ kind: 'warning', message: `请先处理当前 QuanSyn 请求：${active.transferId}` })
      return
    }
    setBusy(true)
    try {
      const row = await api.rest('/desktop/pull', { method: 'POST', body: {}, timeoutMs: 70_000 })
      if (row.empty) {
        host.notify({ kind: 'info', message: 'QuanSyn 暂无待处理问题' })
        return
      }
      const files = Array.isArray(row.files) ? row.files : []
      const suffix = files.length ? `\n\n附件：\n${files.map(file => `- ${file.path}`).join('\n')}` : ''
      writeActive({ transferId: row.id, sessionId: sessionId || null, pulledAt: Date.now() })
      insertIntoComposer(`${row.text}${suffix}`)
      host.notify({ kind: 'success', message: `已拉取到当前输入框：${row.id}` })
    } catch (error) {
      host.notifyError(error, 'QuanSyn 拉取失败')
    } finally {
      setBusy(false)
    }
  }

  return React.createElement(
    Button,
    {
      'aria-label': '拉取 QuanSyn 问题到当前输入框',
      disabled: busy,
      onClick: pull,
      size: 'sm',
      title: active ? `当前请求 ${active.transferId}` : '拉取到输入框',
      type: 'button',
      variant: active ? 'secondary' : 'ghost'
    },
    React.createElement(Codicon, { name: busy ? 'loading' : active ? 'link' : 'cloud-download', size: '0.8rem' }),
    React.createElement('span', null, active ? 'QuanSyn 已关联' : '拉取到输入框')
  )
}

const plugin = {
  id: 'ai-lab-capabilities',
  name: 'QuanSyn Desktop Relay',
  description: 'Pull a QuanSyn request into the current Hermes composer and manually publish with /push or /copy.',
  defaultEnabled: true,
  register(ctx) {
    api = ctx
    ctx.onDispose(() => { api = null })
    ctx.registerMany([
      {
        id: 'pull-to-composer',
        area: COMPOSER_AREAS.leading,
        order: 20,
        render: () => React.createElement(QuanSynPullButton)
      },
      {
        id: 'manual-publish',
        area: COMPOSER_AREAS.middleware,
        order: -100,
        data: {
          handler: async draft => {
            const trimmed = draft.text.trim()
            try {
              if (/^\/push\s*$/i.test(trimmed)) {
                await publishLast()
                return null
              }
              const body = copyCommandBody(draft.text)
              if (body !== null) {
                await publishCopy(body)
                return null
              }
              return draft
            } catch (error) {
              host.notifyError(error, 'QuanSyn 推送失败')
              return null
            }
          }
        }
      }
    ])
  }
}

export default plugin
