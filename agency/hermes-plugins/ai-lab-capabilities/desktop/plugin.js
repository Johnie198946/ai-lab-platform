import React, { useState } from 'react'
import { Button, Codicon, COMPOSER_AREAS, host } from '@hermes/plugin-sdk'

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

function copyCommandBody(text) {
  const trimmed = text.trim()
  if (/^\/copy(?:\s|$)/i.test(trimmed)) return trimmed.replace(/^\/copy(?:\s+|$)/i, '').trim()
  if (/(?:^|\n)\/copy\s*$/i.test(trimmed)) return trimmed.replace(/(?:^|\n)\/copy\s*$/i, '').trim()
  return null
}

async function publishRecent() {
  const sessionId = host.state.focusedSessionId.get()
  if (!sessionId) throw new Error("当前聊天尚未建立会话")
  const receipt = await api.rest('/desktop/push-recent', {
    method: 'POST',
    body: { session_id: sessionId },
    timeoutMs: 70_000
  })
  host.notify({ kind: 'success', message: receipt.noop ? "无新的可推送消息" : receipt.receipt })
}

async function publishCopy(text) {
  if (!text) throw new Error('请把正文写在 /copy 后面，或把 /copy 放在正文最后一行')
  const receipt = await api.rest('/desktop/push-copy', {
    method: 'POST',
    body: { text },
    timeoutMs: 70_000
  })
  host.notify({ kind: 'success', message: `已复制到 QuanSyn：${receipt.result_id}` })
}

function QuanSynPullButton() {
  const [busy, setBusy] = useState(false)

  const pull = async () => {
    if (busy) return
    setBusy(true)
    try {
      const row = await api.rest('/desktop/pull', { method: 'POST', body: {}, timeoutMs: 70_000 })
      if (row.empty) {
        host.notify({ kind: 'info', message: 'QuanSyn 暂无待处理问题' })
        return
      }
      insertIntoComposer(row.text)
      await api.rest('/desktop/pull-presented', {
        method: 'POST', body: { transfer_ids: row.items.map(item => item.id) }, timeoutMs: 70_000
      })
      host.notify({ kind: 'success', message: `已拉取 ${row.items.length} 条到当前输入框` })
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
      title: '拉取全部新消息到输入框',
      type: 'button',
      variant: 'ghost'
    },
    React.createElement(Codicon, { name: busy ? 'loading' : 'cloud-download', size: '0.8rem' }),
    React.createElement('span', null, '拉取到输入框')
  )
}

const plugin = {
  id: 'ai-lab-capabilities',
  name: 'QuanSyn Desktop Relay',
  description: 'Relay all new QuanSyn messages into the composer; /push publishes the latest five new visible session messages.',
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
              if (/^\/pull\s*$/i.test(trimmed)) {
                const row = await api.rest('/desktop/pull', { method: 'POST', body: {}, timeoutMs: 70_000 })
                if (!row.empty) {
                  insertIntoComposer(row.text)
                  await api.rest('/desktop/pull-presented', { method: 'POST', body: { transfer_ids: row.items.map(item => item.id) } })
                }
                return null
              }
              if (/^\/push\s*$/i.test(trimmed)) {
                await publishRecent()
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
