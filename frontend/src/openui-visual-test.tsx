import React from 'react'
import { createRoot } from 'react-dom/client'
import OpenUIMessage from './components/OpenUIMessage'
import './style.css'

const aiPrompt = [
  '请用 OpenUI 渲染一个结构化运营分析界面。',
  '界面需要包含标题、摘要、指标表格、趋势图、状态步骤、标签和后续操作。',
].join('\n')

const aiOpenUIResponse = `header = CardHeader("NeoFish OpenUI 渲染测试", "结构化运营分析界面")
summary = TextContent("这是一次对 AI 结构化 UI 输出的端到端渲染检查：同一条回答包含摘要、表格、图表、步骤、标签和后续动作。")
status = Callout("success", "OpenUI 响应已生成", "检测到 root = Card([...]) 结构，并使用 @openuidev/react-lang Renderer 渲染。")
metrics = Table([Col("模块", ["结构识别", "React 渲染", "视觉检查", "交互动作"]), Col("结果", ["通过", "通过", "通过", "可回传"], "string"), Col("置信度", [98, 96, 94, 88], "number")])
trend = LineChart(["输入", "解析", "渲染", "截图"], [Series("完成度", [20, 55, 86, 100])], "linear", "阶段", "完成度")
steps = Steps([StepsItem("提问 AI", "要求 AI 生成结构化 OpenUI 响应。"), StepsItem("渲染组件", "Vue 页面通过 React bridge 挂载 OpenUI Renderer。"), StepsItem("视觉截图", "用浏览器打开测试页面并检查截图。")])
tags = TagBlock(["Card", "Table", "LineChart", "Steps", "Callout"])
followups = FollowUpBlock([FollowUpItem("继续生成更复杂的仪表盘"), FollowUpItem("把该结构保存为模板")])
root = Card([header, summary, status, metrics, trend, steps, tags, followups])`

function VisualTestApp() {
  const [action, setAction] = React.useState('')

  return React.createElement(
    'main',
    { className: 'theme-app min-h-screen overflow-auto px-6 py-8' },
    React.createElement(
      'section',
      { className: 'mx-auto flex max-w-5xl flex-col gap-5' },
      React.createElement(
        'div',
        { className: 'theme-card rounded-lg p-5' },
        React.createElement('p', { className: 'theme-text-muted text-xs font-semibold uppercase tracking-[0.08em]' }, 'Prompt to AI'),
        React.createElement('pre', { className: 'theme-text-primary mt-3 whitespace-pre-wrap text-sm leading-6' }, aiPrompt),
      ),
      React.createElement(
        'div',
        { className: 'theme-card rounded-lg p-5' },
        React.createElement('p', { className: 'theme-text-muted text-xs font-semibold uppercase tracking-[0.08em]' }, 'Rendered AI OpenUI Response'),
        React.createElement(
          'div',
          { className: 'mt-4', 'data-testid': 'openui-render-target' },
          React.createElement(OpenUIMessage, { content: aiOpenUIResponse, onAction: setAction }),
        ),
      ),
      React.createElement(
        'div',
        { className: 'theme-card rounded-lg p-5' },
        React.createElement('p', { className: 'theme-text-muted text-xs font-semibold uppercase tracking-[0.08em]' }, 'Raw OpenUI'),
        React.createElement('pre', { className: 'theme-text-primary mt-3 overflow-auto whitespace-pre-wrap text-xs leading-5' }, aiOpenUIResponse),
        action ? React.createElement('p', { className: 'theme-text-secondary mt-3 text-sm' }, `Action captured: ${action}`) : null,
      ),
    ),
  )
}

createRoot(document.getElementById('app')!).render(React.createElement(VisualTestApp))
