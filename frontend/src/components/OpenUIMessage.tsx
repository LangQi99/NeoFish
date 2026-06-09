import React from 'react'
import { Renderer, type ActionEvent } from '@openuidev/react-lang'
import { openuiChatLibrary } from '@openuidev/react-ui'
import '@openuidev/react-ui/components.css'

interface OpenUIMessageProps {
  content: string
  isStreaming?: boolean
  onAction?: (message: string) => void
}

function getActionMessage(event: ActionEvent): string {
  if (typeof event.params?.message === 'string') return event.params.message
  if (typeof event.params?.url === 'string') return event.params.url
  return event.humanFriendlyMessage || 'Continue'
}

export default function OpenUIMessage({ content, isStreaming = false, onAction }: OpenUIMessageProps) {
  return React.createElement(
    'div',
    { className: 'openui-message' },
    React.createElement(Renderer, {
      response: content,
      library: openuiChatLibrary,
      isStreaming,
      onAction: (event: ActionEvent) => onAction?.(getActionMessage(event)),
    }),
  )
}
