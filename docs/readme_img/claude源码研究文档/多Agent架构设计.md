# Claude Code 架构研究文档整理版（保留全部信息）

> 说明：本文件基于两篇原始文档重新整理，目标是提升可读性。
>
> 处理原则：只整理格式，不做内容删减；原始信息完整保留。
>
> 原文备份：多Agent架构设计_原文备份.md

## 第一篇：Claude 架构设计

## 二、架构设计

一个能自主编程的 Agent 要处理的事情非常多：调大模型 API、执行 40 多种工具、管理权限、压缩上下文、维护记忆、支持多 Agent 协作……如果这些东西全部塞在一个文件里，代码会立刻变成一团乱麻。
那 Claude Code 是怎么组织这些子系统的？
它采用了一个四层分层架构：我们从上往下，一层一层来理解。
引擎层是 Agent 的「大脑」，负责思考和调度。
它的关键设计原则是不包含任何业务逻辑，它不知道怎么读文件、怎么改代码、怎么搜索，这些全是工具层的事。
引擎层只做三件事：第一，协调，把用户输入、系统指令、历史对话拼在一起，发给大模型；第二，分发，大模型说「我要用某个工具」时，找到对应的工具并执行；第三，决策，根据大模型的返回决定是继续循环还是结束对话。
这种设计的

好处是：新增能力只需要新增一个工具，引擎层完全不用改。
工具层是 Agent 的全部「能力」，40 多个工具都在这一层。
每个工具就是 Agent 的一个能力：执行 Shell 命令、读写文件、搜索代码、生成子 Agent……这些工具不是随便写的，它们遵循一个统一的规范。
这个规范不仅定义了「工具能做什么」，还强制定义了三个安全属性：这个工具是只读的还是会改东西的？
它是否具有破坏性需要额外确认？
它能不能和其他工具同时执行？
这三个属性不是「建议加上」的，而是类型系统强制要求的，漏了任何一个，代码就编译不过。
这意味着每一把刀都有刀鞘，从出厂就配好了安全机制。
服务层是所有层共享的「基础设施」。
这一层包括三样东西：调大模型 API（不管是谁要调，主循环也好、子 Agent 也好，都走这一层）、上下文压缩（后面会详细讲的五步压缩策略）、MCP 协议（和外部工具服务器通信的标准接口）。
你可以把它类比成大楼的水电煤，所有楼层都需要，但谁也不会自己去铺设管道。
安全与治理层有点特殊，它不像其他三层那样各管一块，而是像一张安全网罩在所有层上面。
权限系统决定哪些操作需要用户确认、哪些可以自动执行；Hook 系统允许在工具执行前后插入自定义行为（比如「每次 git push 前自动跑 lint」）；Bash 安全模块会对 Shell 命令做语法级别的分析，检测命令注入、路径逃逸等危险模式，而不是简单地用正则匹配关键词。

## 三、Agent 工作模式

搞清楚了四层架构的宏观布局之后，一个自然的问题来了：引擎层那个主循环里，到底发生了什么？
Agent 是怎么「思考」和「行动」的？
它用的是什么 Agent 框架？
是大家常说的 ReAct 模式吗？
这个问题值得深入聊聊，因为 Agent 的工作模式决定了整个系统的架构走向。
Claude Code 的答案可能出乎你的意料，它没有用 ReAct，而是用了一个更简洁、更高效的模式。

### 什么是 ReAct

如果你接触过 Agent 开发，大概率听说过 ReAct（Reasoning + Acting）。
它是 2022 年提出的一种 Agent 范式，核心思路是把 Agent 的每一步拆成三个阶段：

具体来说，模型在每一轮都会先输出一段「思考」（Thought），比如「我需要先读取 config.ts 文件来了解数据库连接配置」；然后选择一个工具调用（Action）；最后拿到工具结果（Observation）。
这三步不断循环，直到模型认为任务完成。
这个模式在 2022 年非常流行，因为当时的大模型（GPT-3.5 时代）推理能力有限，需要用显式的「Thought」步骤来引导模型一步步思考。
但 ReAct 有几个问题：

- 第一个问题：Token 浪费。
 每一轮都要输出一段 Thought 文本，这些文本要作为上下文的一部分发给 API，占用了宝贵的 Token 预算。
对于编程 Agent 来说，一次任务可能循环 50 轮，每轮都写一段「我打算先读取……然后分析……」的思考过程，加起来就是好几万 Token 的浪费。

- 第二个问题：应用层代码太复杂。
 你需要解析模型的输出，区分「哪部分是 Thought、哪部分是 Action」，然后提取 Action 调用工具，再把 Observation 拼回去。
这个解析过程写起来很麻烦，而且很容易出 bug，因为模型输出的格式不一定标准，一崩就全崩了。

- 第三个问题：ReAct 是为「弱模型」设计的。
 当大模型的推理能力不够强时，用显式的 Thought 来「强迫」它一步步思考是有意义的。
但 Claude Opus 这种级别的模型，推理能力已经足够强了，它完全可以在内部完成推理，不需要在输出里显式写出每一步的思考过程。

### Tool-Use Loop

Claude Code 没有采用 ReAct 的 Thought-Action-Observation 三步循环，而是用了一个更简洁的模式，我把它叫做 

### Tool-Use Loop

。
核心思路非常简单，就一个 while(true) 循环：看到区别了吗？
没有 Thought 步骤。
模型在内部完成推理（通过 Extended Thinking，这是 Claude Opus 的一个能力，模型在生成回复前会在内部进行一段不可见的深度推理，不占用上下文空间），然后直接返回两种结果之一：**tool_use**：「我要用某个工具」，应用层执行工具，把结果拼入消息列表，继续循环**end_turn**：「我说完了」，跳出循环，把最终结果返回给用户这个设计的核心哲学是：信任模型的推理能力，保持应用层框架尽可能简单。
来看 query.ts 中的核心循环，它的实际代码长这样（这是一段 TypeScript 代码，其中 yield 的作用是流式输出，你可以理解为一边接收 API 的响应，一边把每个 token 实时传给 UI 显示）：async function* queryLoop(
  params: QueryParams,
  consumedCommandUuids: string[],
): AsyncGenerator<StreamEvent | Message, Terminal> {
let state: State = { messages, toolUseContext, turnCount: 1, ... }

while (true) {
    // 步骤 1：压缩上下文（五步从轻到重）
    // 步骤 2：调用大模型 API，流式接收
    forawait (const event of streamAPI(params)) {
      yield event  // 流式输出每个 token
    }
    // 步骤 3：分析模型返回
    if (response.stopReason === 'end_turn') break// 完成了，跳出循环

    // 步骤 4：执行工具调用（并发/串行编排）
    const toolResults = await executeToolCalls(toolUseMessages)

    // 步骤 5：更新 state，继续循环
    state = { ...state, messages: updatedMessages, turnCount: turnCount + 1 }
    continue
  }
}
注意 break 和 continue，模型说 end_turn 就 break 跳出循环，说 tool_use 就 continue 回到循环开头。
整个决策逻辑就这么简单。

### 为什么比 ReAct 更好

你可能会问：不就是把 Thought 去掉了吗，有什么了不起的？
区别其实很大，我列了三个关键原因：第一，Extended Thinking 让推理在「模型内部」完成。
 Claude Opus 支持 Extended Thinking，模型在生成最终回复之前，会在内部进行一段不可见的深度推理。
这段推理发生在模型内部，不占用应用的上下文空间，也不需要应用层去解析。
所以 ReAct 的 Thought 步骤在 Claude 的架构里是多余的，模型已经在内部「想好了」，不需要在外部输出中再写一遍。
第二，API 原生支持 tool_use。
 Claude 的 API 原生支持工具调用，模型可以直接返回 tool_use 类型的响应，不需要用正则表达式从文本中提取「Action」。
这消除了 ReAct 的格式解析问题，应用层代码变得极其简洁。
第三，end_turn 作为天然的终止信号。
 ReAct 需要一套额外的规则来判断「Agent 是否完成了」，比如检测输出中是否包含「Final Answer」。
而 

### Tool-Use Loop

 用模型的 end_turn 信号作为终止条件，这是 API 层面的原语，语义清晰，不需要任何解析。
用一个表格来总结两者的区别：维度ReAct

### Tool-Use Loop

推理方式显式 Thought 文本模型内部 Extended Thinking工具调用解析文本提取 ActionAPI 原生 tool_use终止判断检测 「Final Answer」API 原生 end_turnToken 开销每轮要输出 Thought无额外开销编排复杂度高（需要解析 Thought/Action）低（只需要 if/else）适合场景弱模型 + 简单工具强模型 + 复杂工具集Claude Code 的 Agent 工作模式可以总结为一句话：信任模型的推理能力，把应用层框架做得尽可能简单。
ReAct 的设计哲学是「帮模型思考」，用显式的 Thought 步骤引导模型一步步推理。
这在弱模型时代是必要的。
但 Claude Code 面对的是 Opus 级别的强模型，它的推理能力完全可以在内部完成，不需要应用层去「教」它怎么想。
所以 Claude Code 的 

### Tool-Use Loop

 只做最简单的事：调 API、执行工具、再调 API。
推理交给模型，执行交给工具，编排交给最简单的 while(true) 循环。
这种「大道至简」的设计，反而是最高效的。

### Plan Mode

Claude Code 不仅有 

### Tool-Use Loop

 这种「边想边做」模式，还有 

### Plan Mode

，一个更精细的两阶段工作流：先规划、再执行。

### Plan Mode

 的核心思想是：复杂任务应该先规划再执行，避免方向跑偏、浪费精力。
它并不是一个独立的框架，而是在同一个 

### Tool-Use Loop

 中通过 EnterPlanMode 和 ExitPlanMode 两个工具实现的：整个流程分三步：

#### 

- 第一步：模型自主进入或用户手动触发。
 当模型判断「这是一个复杂任务」时，它会调用 EnterPlanMode 工具。
对于简单任务（修 typo、加 console.log），则明确不进入。
用户也可以通过 Shift+Tab 手动切换。

#### 

- 第二步：只读探索 + 设计方案。
 进入 

### Plan Mode

 后，权限降为只读，模型只能用 Read、Grep、Glob 这些工具去探索代码库，不能写文件、不能改代码、不能跑命令。
探索完后，把计划写入 .claude/plans/ 目录。
每 5 轮对话，系统会偷偷给模型塞一张「小纸条」，提醒它「你现在还在 

### Plan Mode

，别手痒改代码」，防止模型在长对话中「走神」。

#### 

- 第三步：用户审批后实施。
 模型调用 ExitPlanMode，此时需要用户确认。
用户批准后，权限恢复为之前的模式，模型开始自由执行读写操作，按计划实施。

### Plan Mode

 最值得学习的设计是「工具即能力」。
对模型来说，

### Plan Mode

 不是一种特殊的「模式切换」，而只是调用了 EnterPlanMode 和 ExitPlanMode 这两个工具。
就像调用 Read 工具读文件一样自然。
整个过程不需要引擎层做任何特殊处理，query() 仍然只是一个简单的 while(true) 循环。

## 四、System Prompt 的构造

System Prompt 就是 Claude Code 的灵魂，它定义了 Agent 的身份、行为规范、可用工具、安全约束……一切。
但 Claude Code 的 System Prompt 不是一个静态的文本文件。
它是动态组装的，由十几个 Section 拼接而成，而且在组装过程中做了非常精巧的缓存优化。
我们先来看一下，Claude Code 的 System Prompt 到底长什么样，它是怎么「调教」大模型变成一个靠谱的编程 Agent 的。
注：Claude Code 源码中所有 Prompt 原文均为英文。
为了让大家更好地理解设计思路，下面展示的 Prompt 内容我翻译成了中文，并保留了关键术语的英文原文。
角色定义与安全红线每个 Agent 的 System Prompt 都要回答一个根本问题：你是谁？
Claude Code 的开场是这样的：你是一个交互式代理（interactive agent），帮助用户完成软件工程任务。

请使用下面的指令和可用的工具来协助用户。

重要：你绝对不能为用户生成或猜测 URL，除非你确信这些 URL
是为了帮助用户完成编程任务。
你可以使用用户在消息或本地文件中
提供的 URL。

注意两个关键点。
第一，它把自己定位为「interactive agent」，而不是「assistant」或「chatbot」，这从一开始就暗示了模型应该主动采取行动，而不是被动回答。
第二，立刻划了安全红线：不能乱编 URL。
这看起来是个小事，但对编程 Agent 非常重要，如果模型瞎编一个 npm 包的 URL，用户执行了就可能中招。
紧接着是一段安全约束指令，这段话非常值得每个 Agent 开发者抄作业：重要：允许协助已授权的安全测试、防御性安全研究、CTF 挑战赛
和教育场景。
拒绝涉及破坏性技术、DoS 攻击、大规模目标扫描、
供应链攻击或用于恶意目的的检测规避请求。

这段 Prompt 没有用「绝对不能做 X」的口吻，而是先说「可以做什么」（授权的安全测试、CTF 挑战），再划定「不能做什么」（DoS、供应链攻击）。
这种「先肯定再约束」的写法，比纯禁止清单效果好得多，它给了模型清晰的判断依据，而不是一堆模糊的红线。

### 行为准则

接下来是一大段关于「怎么做事」的行为指南，这部分是 Claude Code System Prompt 的精华。
我挑几条最值得学习的：关于修改代码前先阅读：一般来说，不要对你没有阅读过的代码提出修改建议。
如果用户
要求你查看或修改某个文件，先读一遍它。
在提出修改建议之前，
先理解现有代码。

这条看起来简单，但解决了 Agent 的一个常见问题：很多 Agent 会根据用户描述直接生成代码，而不先看看现有代码是什么样的，结果经常和项目风格不一致或者引入重复实现。
关于代码风格：「少即是多」：不要在用户要求之外添加功能、重构代码或进行"改进"。
修一个 bug
不需要顺手清理周围的代码。
一个简单功能不需要额外的可配置性。

不要为一次性操作创建辅助函数、工具类或抽象层。

三行相似的代码比一个过早的抽象更好。

这个设计思路太重要了。
如果你用过 Agent 写代码，你一定遇到过这种情况：你让它修一个 bug，它顺手把整个文件重构了，加了一堆你没要求的类型标注和错误处理。
Claude Code 在 Prompt 里明确禁止了这种行为。
关于失败处理：「先诊断再换方案」：如果某个方案失败了，先诊断原因再决定是否换方案——读报错信息、
检查你的假设、尝试有针对性的修复。
不要盲目重试完全相同的操作，
但也不要因为一次失败就放弃一个可行的方案。

这条解决了 Agent 的另一个常见问题，「摆烂式重试」或「草率放弃」。
Claude Code 要求模型先搞清楚为什么失败了，再决定是修复还是换方案，而不是两个极端。

### 操作安全

Claude Code 对「什么操作需要用户确认」做了非常详细的规定。
我建议每个 Agent 开发者都研读这段 Prompt：仔细考虑操作的可逆性（reversibility）和影响范围（blast radius）。

一般来说，你可以自由执行本地的、可逆的操作，比如编辑文件或
运行测试。
但对于难以撤销、影响共享系统或有风险的操作，
请先和用户确认后再执行。

需要用户确认的高风险操作示例：
- 破坏性操作：删除文件/分支、删表、rm -rf
- 难以逆转的操作：force-push、git reset --hard、修改已发布的 commit
- 对他人可见的操作：推送代码、创建/关闭 PR、发送消息
- 上传到第三方工具：内容可能被缓存或索引，即使删除也无法撤回
这段的核心思想是用可逆性和影响范围两个维度来判断风险。
读文件、改本地代码是低风险的（可逆、只影响本地），直接放行。
git push、发 Slack 消息是高风险的（不可逆、影响他人），必须确认。
然后还有一句非常精妙的补充：用户批准了某个操作（比如 git push）一次，并不意味着他在所有
场景下都批准这个操作。
授权仅对指定的范围有效，不能超出范围。

这解决了「权限蔓延」的问题，用户同意了一次 push 不代表以后都自动 push，授权是一次性的、有范围的。
这个原则在 Agent 权限设计中非常重要。

### 工具使用指南

当有专用工具可用时，不要用 Bash 来执行命令。
使用专用工具可以
让用户更好地理解和审查你的工作。
这一点至关重要：

- 读取文件用 Read 工具，而不是 cat、head、tail 或 sed
- 编辑文件用 Edit 工具，而不是 sed 或 awk
- 创建文件用 Write 工具，而不是 echo 重定向
- 搜索文件用 Glob 工具，而不是 find 或 ls
- 搜索内容用 Grep 工具，而不是 grep 或 rg
这条规则的设计动机值得深思。
为什么不让模型直接用 cat 读文件、用 sed 改代码？
技术上完全可以。
原因是可审查性。
当模型调用 Read 工具读文件时，UI 会清晰地展示「Agent 正在读取 src/index.ts」。
但如果模型执行 cat src/index.ts，用户看到的只是一条 Bash 命令和一大坨输出，完全不知道 Agent 在干什么。
而且，专用工具有专用的权限检查，Read 工具会检查文件路径是否在允许范围内，而 cat 命令就没有这层保护了。
所以「用专用工具而不是 Bash」不仅是体验问题，更是安全问题。

### Git 安全协议

Claude Code 对 Git 操作有一套非常严格的安全协议，这段 Prompt 写得极其细致：

### Git 安全协议

：
- 绝不修改 git config
- 绝不执行破坏性 git 命令（push --force、reset --hard、
  checkout .、clean -f），除非用户明确要求
- 绝不跳过 hooks（--no-verify），除非用户明确要求
- 绝不 force push 到 main/master 分支，如果用户要求则发出警告

关键：始终创建新的 commit（NEW commit），而不是用 --amend 修改。

当 pre-commit hook 失败时，commit 实际上并没有发生——所以
--amend 会修改上一个（不相关的）commit，可能导致代码丢失。

正确做法是：修复问题后创建一个新的 commit。

最后一条关于 --amend 的警告特别值得注意。
很多人（包括一些 Agent 实现）在 commit 失败后会习惯性地 git commit --amend。
但如果失败原因是 pre-commit hook 拒绝了，那么 commit 实际上没发生！
这时候 --amend 会修改上一个（不相关的）commit，可能导致代码丢失。
这种微妙的 bug 很难被发现，Claude Code 直接在 Prompt 里防住了。

### 输出风格约束

Claude Code 对模型的输出风格也有严格规定：# 输出效率
直奔重点。
先尝试最简单的方案。
要极度简洁。

工具调用之间的文字不超过 25 个词。
最终回复不超过 100 个词。

先给出答案或行动，而不是推理过程。
跳过填充词、开场白和
不必要的过渡句。
不要复述用户说过的话——直接做就行。

25 个词的限制非常苛刻，这意味着模型在两次工具调用之间，基本只能说一句话。
这个设计的目的是避免 Agent 「话痨」，没人想看 Agent 在每次读文件前先写一段「让我来看看这个文件的内容……」的废话。

### 环境信息注入

每次对话开始时，Claude Code 会把当前

### 环境信息注入

 System Prompt：# 环境信息
- 主工作目录：/Users/you/my-project
- 是否为 Git 仓库：是
- 操作系统平台：darwin (macOS)
- Shell 类型：zsh
- 当前模型：Claude Opus 4.6 (1M context)
- 知识截止日期：2025 年 5 月
这些信息让模型知道自己「在哪里」，是什么操作系统、什么 Shell、什么项目目录。
没有这些信息，模型可能会在 macOS 上执行 apt-get install，或者在 zsh 环境里用 bash 语法。

### 分割线与三级缓存

了解了各个 Section 的内容，我们回到一个很实际的问题：这些 Section 是怎么组装到一起的？
为什么组装方式会影响费用？
先看一段组装后的 System Prompt 长什么样（简化版）：┌─────────────────────────────────────────────────┐
│  [角色定义] 你是一个交互式代理，帮助用户完成...    │  ← 所有用户完全一样
│  [安全红线] 重要：允许协助已授权的安全测试...       │  ← 所有用户完全一样
│  [

### 行为准则

] 一般来说，不要对你没有阅读过的代码...   │  ← 所有用户完全一样
│  [

### 操作安全

] 仔细考虑操作的可逆性...               │  ← 所有用户完全一样
│  [工具使用] 当有专用工具可用时...                  │  ← 所有用户完全一样
│  [Git 安全] 绝不修改 git config...               │  ← 所有用户完全一样
│  [输出风格] 直奔重点，要极度简洁...               │  ← 所有用户完全一样
├────── __SYSTEM_PROMPT_DYNAMIC_BOUNDARY__ ────────┤
│  [环境信息] 主工作目录: /Users/you/my-project    │  ← 每个用户不一样
│  [CLAUDE.md] 本项目使用 TypeScript + Jest...      │  ← 每个项目不一样
│  [记忆指令] 你有一个持久记忆系统...               │  ← 每次对话可能不一样
│  [MCP 指令] 你已连接 GitHub MCP server...         │  ← 每个用户不一样
└─────────────────────────────────────────────────┘
看到中间那条粗线了吗？
那就是 Claude Code 在 System Prompt 中插入的分割标记 __SYSTEM_PROMPT_DYNAMIC_BOUNDARY__。
分割线之上的内容，对所有用户都完全一样。
 不管你是北京的 Java 工程师还是纽约的 Python 开发者，你看到的「角色定义」「

### 行为准则

」「

### Git 安全协议

」这些内容是一模一样的。
分割线之下的内容，每个用户都不同。
 你的工作目录、你的 CLAUDE.md、你的记忆文件、你连接的 MCP 服务，这些是因人而异的。

为什么要这么分？
因为 Claude API 有一个 Prompt Cache 机制：如果两次请求的 Prompt 前缀完全相同，API 会复用上次的计算结果，**费用可以降低 90%**。
对于几万 Token 的 System Prompt 来说，缓存命中与否意味着每次请求几美分和几美元的差距。
分割线之上的内容对所有用户都一样，所以可以全球所有用户共享同一份缓存——你用的和东京的开发者用的是同一份。
而分割线之下的内容因人而异，没法共享，只能实时生成。
这就是 Claude Code 的三级缓存体系：全局缓存（分割线之上，跨组织跨用户共享）→ 组织缓存（同一组织内跨会话共享）→ 会话缓存（同一个 Section 在一次会话内只计算一次）。
每一级都在帮 API 省钱。

### 小结

回过头来看 Claude Code 的 System Prompt，你会发现它其实在做一件事：用最小的 Token 成本，给模型划出最清晰的行为边界。
怎么划的呢？
我总结了三个最值得抄作业的设计。
第一个是「先给范围再画红线」。
比如安全约束那段，它不是一上来就说「不准做这不准做那」，而是先说「安全测试、CTF 挑战这些可以做」，然后再说「DoS、供应链攻击这些不能做」。
这比你写十句「不准 XX」管用得多，因为模型拿到了判断标准，而不是一堆模糊的禁令。
第二个是「用两个维度把风险分出层次」。
Claude Code 判断一个操作安不安全，不看它「看起来危不危险」，而是看两件事：这操作能撤回吗？
会影响别人吗？
改本地代码当然能撤回、只影响自己，直接放行。
git push 撤不回来、别人能看到，那就得确认。
这个思路比笼统的「危险/安全」二分法精细太多了。
第三个是「静态内容和动态内容用分割线隔开」。
那条分割线不是随便画的，它把所有用户都一样的部分和因人而异的部分切开了。
这样做的好处是，分割线之上的内容可以被全球所有用户共享缓存，每次 API 调用能省 90% 的费用。
一个看似简单的排版调整，背后是实打实的成本优化。

## 五、记忆系统

每次启动 Claude Code 都是一个全新的会话，模型不记得上次对话的任何内容。
但用户的偏好、项目背景、行为反馈，这些信息需要跨会话保持。
这个问题看起来简单，做起来却非常难。
业界常见的方案是用向量数据库，把记忆存成 embedding，每次对话时做相似度检索。
但 Claude Code 没有这么做。
为什么？
因为 Agent 需要记住的大部分不是「相似的文档片段」，而是「用户说过'不要 mock 数据库'」这种结构化的行为指令。
用向量相似度去检索「不要 mock 数据库」这句话，效果其实很差，它可能匹配到一堆包含「数据库」关键词的无关内容，真正重要的行为反馈却被淹没了。
Claude Code 设计了一套完全不同的记忆系统，我们来一层一层拆解。

### 记什么：四类型分类

Claude Code 把记忆分成了四种明确的类型：export const MEMORY_TYPES = [
  'user',      // 用户画像：角色、偏好、知识水平
  'feedback',  // 行为反馈：该做什么、不该做什么
  'project',   // 项目动态：在做什么、截止日期、协作信息
  'reference', // 外部指针：哪里能找到什么信息
] as const
注意，只有这四种，不能随便加新的。
为什么不搞一个通用的「any」类型什么都能存？
因为无约束的记忆会迅速膨胀成垃圾堆。
限定四种类型，就是在逼 Agent 做分类决策。
每存一条记忆，它必须想清楚「这到底属于哪一类」，而不是一股脑往里塞。
我逐个解释一下这四种类型的设计意图。
User（用户画像）是最个人化的一类，记住用户是谁、擅长什么、知识水平如何。
比如用户说「我是一个写了十年 Go 的后端工程师，第一次接触 React」，Agent 就应该在解释前端概念时用后端的类比，而不是从零讲起。
这类记忆让 Agent 的回答因人而异，而不是千篇一律。
Feedback（行为反馈）是最重要的一类，记住用户说过「不要做什么」和「做得好继续保持」。
这类记忆的关键在于，它不仅记规则本身，还要求记录 Why（为什么） 和 How to apply（怎么应用）：规则本身：集成测试必须使用真实数据库，不能用 mock
Why：上季度 mock 测试全部通过但生产环境迁移失败了
How to apply：在这个模块写测试时，始终连接真实数据库
为什么一定要记 Why？
因为光记住「不要 mock 数据库」是不够的。
如果遇到一个边缘情况，比如一个纯单元测试不涉及数据库迁移，Agent 需要根据 Why 来判断「这条规则在这个场景下是否适用」。
没有 Why，Agent 只能盲目遵守，可能在不该用真实数据库的地方也强行连接。
Project（项目动态）记的是「正在发生什么」，谁在做什么、截止日期是什么、有什么重要决策。
这类记忆有一个特殊要求：必须把相对日期转成绝对日期。
用户说「周四之前冻结合并」，Agent 要存成「2026-03-05 之前冻结合并」，因为「周四」过几天就没意义了，但「2026-03-05」永远准确。
Reference（外部指针）记的是「去哪找什么信息」，Bug 在 Linear 的哪个项目里追踪、Grafana 看板的地址是什么、Slack 的哪个频道能问到相关的人。
这类记忆的价值在于，Agent 不需要知道外部系统的具体内容，只需要知道去哪里找。

### 不记什么：排除清单

Claude Code 明确规定了什么不应该存到记忆里，这个设计和「记什么」同样重要。
首先是代码模式、项目架构和文件结构这些信息，通过 grep、git、CLAUDE.md 就能获取，存在记忆里反而会导致记忆和代码实际状态不一致。
然后是 Git 历史和最近的改动，git log 和 git blame 才是权威来源，不需要记忆系统再来存一遍。
调试方案和修复方法也不存，因为修复已经在代码里了，commit 消息已经记录了上下文。
CLAUDE.md 里已经写了的内容也不存，避免重复。
最后是临时任务状态和当前对话上下文，这些是会话级的信息，不需要跨会话保持。
这个排除清单背后的核心原则是：可以从当前代码推导出来的信息，一律不存。
因为代码是「活的」，它随时在变，但记忆是「死的」，它存下来就定格了。
如果记忆说「AuthService 在 src/auth.ts 第 42 行」，但代码已经重构了，那这条记忆就变成了一个「权威的错误」，比没有记忆还糟糕。

### 怎么存：索引 + 独立文件

搞清楚了「记什么」和「不记什么」，接下来看「怎么存」。
每条记忆存为一个独立的 .md 文件，文件开头有一段 YAML 格式的元信息（你可以理解为这条记忆的「身份证」）：---
name: no-mock-database
description: 集成测试必须使用真实数据库，不能用 mock
type: feedback
---

集成测试必须使用真实数据库，不能用 mock。

**Why:** 上季度 mock 测试全部通过但生产环境迁移失败了。

**How to apply:** 在这个模块写测试时，始终连接真实数据库。

文件开头那段 YAML 格式的元信息里，三个字段各有用途：name 是人类可读的标识；description 是一句话摘要，专门用于检索时的相关性匹配（后面会讲到）；type 标记四类型之一。
然后有一个 MEMORY.md 文件作为索引，它是一个不超过 200 行（25KB）的轻量目录：- [No Mock Database](feedback_no_mock_db.md) — tests must use real DB
- [User Preferences](user_preferences.md) — prefers terse responses
- [Auth Rewrite](project_auth_rewrite.md) — driven by compliance, not tech debt
注意这个 200 行的硬性上限。
为什么要限制？
来看源码里的截断逻辑：export const MAX_ENTRYPOINT_LINES = 200
exportconst MAX_ENTRYPOINT_BYTES = 25_000  // 25KB

exportfunction truncateEntrypointContent(raw: string): EntrypointTruncation {
// 同时检查行数和字节数上限
const wasLineTruncated = lineCount > MAX_ENTRYPOINT_LINES
const wasByteTruncated = byteCount > MAX_ENTRYPOINT_BYTES

if (wasLineTruncated || wasByteTruncated) {
    // 截断并附加警告
    return {
      content: truncated + '\n\n> WARNING: MEMORY.md 太大了...',
      // ...
    }
  }
}
它同时检查行数和字节数两个维度。

为什么要两个？
因为有人可能写了 199 行，每行 500 字，行数没超但字节数爆了。
双重检查堵住了这个漏洞。
现在来看整个存储架构的关键设计：MEMORY.md 索引始终被加载到 System Prompt 里，但独立记忆文件按需加载。
这解决了一个经典矛盾，如果把所有记忆都塞进 System Prompt，50 条记忆就可能占满上下文；如果完全不塞，Agent 又不知道有哪些记忆可用。
索引文件两全其美：Agent 看到索引就知道有哪些记忆，但只加载真正相关的那几条。

### 怎么召回：Sonnet 当秘书

存好了记忆，关键问题来了：每次对话时，怎么从几十条记忆里挑出最相关的那几条加载进来？
Claude Code 的做法非常巧妙，用一个廉价的小模型（Sonnet）来做记忆检索。
整个召回流程分为三步：

#### 

- 第一步：扫描所有记忆文件的「头部信息」export asyncfunction scanMemoryFiles(
  memoryDir: string,
  signal: AbortSignal,
): Promise<MemoryHeader[]> {
const entries = await readdir(memoryDir, { recursive: true })
const mdFiles = entries.filter(
    f => f.endsWith('.md') && basename(f) !== 'MEMORY.md',
  )
// 只读每个文件的前 30 行（frontmatter 区域），不读全文
const headers = awaitPromise.allSettled(
    mdFiles.map(async (relativePath) => {
      const { content, mtimeMs } = await readFileInRange(
        filePath, 0, 30,  // 只读前 30 行！

      )
      const { frontmatter } = parseFrontmatter(content)
      return {
        filename: relativePath,
        description: frontmatter.description || null,
        type: parseMemoryType(frontmatter.type),
        mtimeMs,  // 文件修改时间，用于后续的新旧度判断
      }
    }),
  )
// 按修改时间倒序，最多 200 个
return headers.sort((a, b) => b.mtimeMs - a.mtimeMs)
    .slice(0, 200)
}
注意它只读每个文件的前 30 行，足够提取文件开头那段元信息里的 name、description、type，但不会读取记忆的完整内容。
这样即使有 200 个记忆文件，扫描开销也很小。

#### 

- 第二步：拼成清单，发给 Sonnet 做选择。
扫描完之后，所有记忆的「头部信息」被拼成一个文本清单：- [feedback] feedback_no_mock.md (2026-03-28): 集成测试必须使用真实数据库
- [user] user_preferences.md (2026-03-25): 用户是后端工程师，偏好简洁回复
- [project] project_auth.md (2026-03-20): 认证模块重写由合规需求驱动
然后把这个清单连同用户当前的输入一起发给 Sonnet：const result = await sideQuery({
  model: getDefaultSonnetModel(),
  system: '你是一个记忆选择器，从列表中选出最多 5 条与用户问题最相关的记忆...',
  messages: [{
    role: 'user',
    content: `用户问题: ${query}\n\n可用的记忆:\n${manifest}`,
  }],
  max_tokens: 256,  // 只需要返回文件名列表，非常短
})
Sonnet 返回的只是一个文件名列表（比如 ["feedback_no_mock.md", "project_auth.md"]），不是记忆内容本身。

#### 

- 第三步：加载选中记忆的完整内容，注入上下文。
拿到文件名列表后，系统才去读取这几条记忆的完整内容，作为 <system-reminder> 注入当前对话。
这里还有一个非常讲究的细节，记忆陈旧度检测。
对于超过 1 天的记忆，系统会自动附加一段警告：export function memoryFreshnessText(mtimeMs: number): string {
const d = memoryAgeDays(mtimeMs)
if (d <= 1) return''// 今天或昨天的记忆不加警告
return (
    `这条记忆已经有 ${d} 天了。
` +
    `记忆是某个时间点的观察，不是实时状态——` +
    `其中关于代码行为或 file:line 引用的断言可能已经过时。
` +
    `在当作事实引用之前，请先对照当前代码验证。
`
  )
}

为什么需要这个？
因为用户可能 30 天前存了一条记忆说「AuthService 在 src/auth.ts 第 42 行使用了 JWT」，但代码早就改了。
如果模型盲目相信这条记忆，就会给出错误的建议。
陈旧度警告提醒模型「这个信息可能过时了，先验证再引用」。

### 性能优化：并行预取

最后一个值得学习的设计：记忆召回的执行时机。
Sonnet 侧查询不是在主模型需要时才触发的，而是在用户提交消息后立刻就开始了，和主模型的 API 调用并行执行：// query.ts 中的调用——在进入主循环之前就启动记忆预取
using pendingMemoryPrefetch = startRelevantMemoryPrefetch(
  state.messages,
  state.toolUseContext,
)
时序大概是这样的：Sonnet 比 Opus 快得多（延迟通常只有几百毫秒），所以等主模型的响应回来时，记忆选择早就完成了。
整个记忆召回过程几乎不增加任何额外延迟。
还有一个小优化：如果用户当前正在使用某些工具（比如正在调用某个 MCP 工具），Sonnet 选择器会自动过滤掉该工具的使用文档类记忆，因为模型已经在用这个工具了，它的用法文档此刻是噪声，不是信号。
但「该工具的已知 bug 和注意事项」类记忆仍然会被选中，正在用的时候，恰恰是最需要知道坑在哪里的时候。

### 小结

回顾一下 Claude Code 的记忆系统，它的核心设计哲学可以用三句话概括。
第一句是「记该记的，不记能推导的」。
通过四类型封闭集合加上排除清单，把记忆控制在有价值的范围内，防止它膨胀成一个什么都往里塞的垃圾堆。
第二句是「存索引，按需加载详情」。
MEMORY.md 作为轻量索引始终常驻在 System Prompt 里，但每条记忆的具体内容是独立文件，用到的时候才加载。
这样既让 Agent 知道有哪些记忆可用，又不会撑爆上下文。
第三句是「用小模型做秘书，大模型做决策」。
Sonnet 负责并行预取和选择记忆，Opus 只管做决策，加上陈旧度检测机制，实现了零延迟、低成本、高可靠。

## 六、上下文窗口管理

这可能是整个 Claude Code 里最复杂也最精妙的部分。
大模型有上下文窗口限制。
即使是 200K Token 的窗口，一次复杂的编程任务（读了几十个文件、执行了几十条命令）很容易就塞满了。
业界常见的做法是「简单截断」，只保留最近的 N 条消息，旧的扔掉。
但这对于编程 Agent 来说是灾难性的：你可能 20 轮前读过一个关键配置文件，现在要改代码时那个文件的信息已经被截掉了，Agent 就会犯低级错误。
另一种做法是「全量摘要」，把整段对话总结成一段摘要。
但这很贵（摘要本身就是一次 API 调用），而且有信息损失。

### 压缩五步走

Claude Code 的核心理念是：压缩一定有信息损失，所以能不压就不压，必须压的时候从最轻的手段开始。
它设计了五个从轻到重的压缩手段，就像医院的分诊制度一样：先试最温和的，不行再上猛药。
在每次 API 调用前依次尝试：为什么要分五步，而不是一步到位做全量摘要？
因为每一步的「代价」是递增的。
第 1 层几乎没有信息损失，完整内容还在磁盘上，只是不在上下文里了。
第 2、3 层有少量信息损失，丢掉了老的工具输出，但模型随时可以重新获取。
第 4 层有中等信息损失，对话细节被分段压缩了。
第 5 层信息损失最大，整段对话变成一段摘要。
所以 Claude Code 的策略是：先用代价最小的手段，实在不行再升级。
大部分情况下，前三层就够用了，根本不需要触发昂贵的全量摘要。
接下来我们一层一层拆解。

### 第 1 步：大结果存磁盘

问题是什么？
 想象一下，你让 Agent 读一个 10MB 的日志文件。
Read 工具忠实地返回了全部内容，一下子就吃掉了几万 Token。
更夸张的是，如果模型同时读了 3 个大文件，一条消息就可能占掉大半个上下文窗口。
Claude Code 怎么做？
 它在工具结果进入消息列表之前，就先做一道「体检」：async function maybePersistLargeToolResult(
  toolResultBlock: ToolResultBlockParam,
  toolName: string,
): Promise<ToolResultBlockParam> {
const size = contentSize(content)
// 单个工具结果超过阈值（默认约 50KB）？

if (size <= threshold) {
    return toolResultBlock  // 没超，原样通过
  }
// 超了！
把完整内容存到磁盘文件
const result = await persistToolResult(content, toolUseId)
// 用一个 2KB 的预览替换原内容
const preview = buildLargeToolResultMessage(result)
return { ...toolResultBlock, content: preview }
}
它的逻辑很简单：如果单个工具的结果超过约 50KB，就把完整内容写到磁盘上，在消息里只留一个 2KB 的预览摘要。
这样模型还是能看到文件的大概内容（前 2KB），但不会撑爆上下文。
除了单个工具的限制，还有一个消息级的总量控制，同一条消息里所有工具结果的总大小不能超过 200KB。
如果超了，系统会挑出最大的那几个结果存磁盘，直到总量降到限制以内。
这一层的精妙之处在于：完整内容并没有丢，它还在磁盘上。
如果模型后面真的需要那个大文件的某个片段，它可以再次调用 Read 工具去读取特定的行范围。

### 第 2 步：砍掉远古消息

问题是什么？
 一次长对话可能有上百轮。
对话开头那几轮的内容，比如用户最初的探索性提问、模型早期的试探性回答，到了后面几乎完全没用了。
但它们仍然占着宝贵的上下文空间。
Claude Code 怎么做？
 Snip 是最「粗暴」但也最高效的一层，直接把对话开头的一批老消息移除掉，然后插入一个边界标记告诉模型「这之前的内容已经被清理了」。
if (feature('HISTORY_SNIP')) {
  const snipResult = snipModule.snipCompactIfNeeded(messagesForQuery)
  messagesForQuery = snipResult.messages
  snipTokensFreed = snipResult.tokensFreed
  if (snipResult.boundaryMessage) {
    yield snipResult.boundaryMessage  // 插入边界标记
  }
}
它不做任何摘要，不总结「前面聊了什么」，直接砍掉。
听起来很暴力，但对于那些确实已经完全过时的消息来说，这是代价最低的做法，因为它不需要额外调用大模型来生成摘要，零 API 开销。
还有一个重要的细节：Snip 会把「我释放了多少 Token」这个数字（snipTokensFreed）传给后面的第 5 层 Auto-Compact。
为什么？
因为 Auto-Compact 是根据「当前上下文占了多少 Token」来决定是否触发的。
如果 Snip 已经释放了足够的空间，Auto-Compact 就不需要触发了，避免两层同时做无谓的压缩。

### 第 3 步：裁剪老的工具输出

问题是什么？
 经过前两层之后，上下文里剩下的都是「不太老但也不太新」的消息。
这些消息不能直接砍掉（可能还有用），但里面大量的工具输出其实已经过时了，比如 30 分钟前读的一个文件，现在那个文件可能已经被改过了。
Claude Code 怎么做？
 Micro-Compact 的核心思想是时间衰减：越老的工具结果越不重要，可以被裁剪。
但是，不是所有工具的结果都能裁剪：const COMPACTABLE_TOOLS = new Set([
  FILE_READ_TOOL_NAME,    // 读文件 → 可以重新读
  ...SHELL_TOOL_NAMES,    // 执行命令 → 可以重新执行
  GREP_TOOL_NAME,         // 搜索 → 可以重新搜
  GLOB_TOOL_NAME,         // 查找文件 → 可以重新查
  WEB_SEARCH_TOOL_NAME,   // 搜索网页 → 可以重新搜
  FILE_EDIT_TOOL_NAME,    // 编辑文件 → 结果可裁剪
  FILE_WRITE_TOOL_NAME,   // 写文件 → 结果可裁剪
])
看到规律了吗？
可以被裁剪的，都是「可重新获取」的工具，Read 的结果可以再读一次，Bash 的输出可以再执行一次，搜索结果可以再搜一次。
但 AgentTool（子 Agent 的输出）、TaskTool（任务状态）这类工具的结果永远不会被裁剪，因为子 Agent 的推理过程是不可重复的，砍掉就真的丢了。
具体裁剪逻辑是「保留最近 N 个，清理其余的」：// 收集所有可裁剪工具的结果 ID
const compactableIds = collectCompactableToolIds(messages)
// 保留最近 5 个，其余全部清理
const keepRecent = Math.max(1, config.keepRecent)  // 至少保留 1 个
const keepSet = new Set(compactableIds.slice(-keepRecent))
const clearSet = compactableIds.filter(id => !keepSet.has(id))
被裁剪的工具结果会被替换成一个标记：export const TIME_BASED_MC_CLEARED_MESSAGE =
  '[Old tool result content cleared]'
这样模型看到这个标记就知道「这里原来有内容但被清理了」。
如果它后面还需要这些信息，它可以自己决定重新读文件或重新执行命令。
为什么叫「时间衰减」？
因为它的触发条件跟时间有关，当距离上一次 API 调用超过一定时间（默认约 60 分钟），说明大模型 API 端的 Prompt Cache 大概率已经过期了。
既然缓存已经没了，那清理旧的工具结果也不会浪费之前的缓存投入。

### 第 4 步：读时投影

问题是什么？
 经过前三层后，如果上下文还是太大，下一步就得做全量摘要了。
但全量摘要代价很高（要额外调一次 API），而且会把整段对话的细节全部丢掉。
有没有一个「中间态」，比全量摘要轻，但比 Micro-Compact 重？
Claude Code 怎么做？
 Context Collapse 引入了一个非常巧妙的概念，读时投影（Read-Time Projection）。
什么意思呢？
前面三层都是「写时压缩」，直接修改消息列表，把内容替换掉或删掉。
但 Context Collapse 不修改原始消息，它只在调用 API 的那一刻，动态计算一个「压缩视图」给模型看。
// 这是 query.ts 中的调用
// 注意：这是一个"读时投影"——不修改 REPL 的完整历史，
// 只在发送给 API 时计算压缩视图
if (feature('CONTEXT_COLLAPSE') && contextCollapse) {
  const collapseResult = await contextCollapse.applyCollapsesIfNeeded(
    messagesForQuery,
    toolUseContext,
    querySource,
  )
  messagesForQuery = collapseResult.messages
}
它的触发有两级阈值：90% 上下文窗口：主动开始分段压缩旧消息（预留缓冲区）95% 上下文窗口：紧急压缩更多内容（留足 API 响应空间）这个设计最精妙的地方是它和第 5 层的配合：Context Collapse 运行在 Auto-Compact 之前。
如果 Context Collapse 已经通过「读时投影」把上下文压到了阈值以下，Auto-Compact 就完全不需要触发了。
这样模型保留了更多的细节上下文，而不是被一段粗糙的全量摘要替代。

### 第 5 步：全量摘要

问题是什么？
 当前面四层都不够用，上下文实在太大了，必须做一次彻底的压缩。
这是代价最高但效果最强的一层。

什么时候触发？
 Claude Code 用一个公式计算触发阈值：function getAutoCompactThreshold(model: string): number {
  const effectiveContextWindow = getEffectiveContextWindowSize(model)
  // 有效窗口 - 13K 缓冲区 = 触发阈值
  return effectiveContextWindow - 13_000
}
以 200K Token 的模型为例：有效窗口大约 180K（预留 20K 给输出），减去 13K 缓冲区，当上下文达到 167K Token 时触发。
触发后做了什么？
 三步走：

#### 

- 第一步：生成摘要。
调用大模型，把整段对话总结成一段结构化摘要。
这个摘要不是随便写的，Claude Code 用一个精心设计的 Prompt 要求模型按多个维度来总结：用户的主要请求和意图、关键技术概念、涉及的文件和代码片段、遇到的错误和修复方案、问题解决过程、用户的所有消息（不能遗漏任何一条）、待完成的任务、当前工作状态、建议的下一步。
为什么要这么细？
因为压缩后模型要靠这段摘要来「恢复记忆」。
如果摘要漏掉了关键信息（比如「用户还有一个待完成的任务」），模型就会忘记这件事。

#### 

- 第二步：替换旧消息。
把压缩边界之前的所有消息删掉，替换为刚才生成的摘要。
同时插入一条边界标记消息，记录压缩前的 Token 数，方便后续追踪。

#### 

- 第三步：Post-Compact Restoration（压缩后恢复）。
这是整个流程中最关键的一步，压缩完不是就完了，还要主动恢复最重要的上下文：export const POST_COMPACT_MAX_FILES_TO_RESTORE = 5
export const POST_COMPACT_TOKEN_BUDGET = 50_000
export const POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000
export const POST_COMPACT_SKILLS_TOKEN_BUDGET = 25_000
系统会从文件状态缓存（fileStateCache）中找出最近访问过的文件，按最后访问时间排序，挑选最多 5 个、总共不超过 50K Token 的文件内容重新注入。
同时恢复活跃的 Skill（不超过 25K Token），如果有进行中的 Plan 也会恢复 Plan 文件。
为什么要做恢复？
因为压缩后模型「失忆」了，它不记得刚才读过的文件内容了。
如果不恢复，模型的第一反应就是「让我重新读一下文件」，白白浪费一轮工具调用。
主动恢复最近的文件内容，可以让模型无缝继续工作，体验上几乎感觉不到压缩发生过。
还有一个兜底机制：如果全量摘要连续失败 3 次（比如 API 超时），系统会自动放弃，不会无限重试，这就是熔断器 模式，防止一个失败的压缩操作拖垮整个 Agent。

### 小结

回顾一下这五步压缩策略，它们体现了一个核心设计哲学：能轻则轻，逐步加码。
层级手段信息损失API 开销触发条件第 1 层大结果存磁盘几乎为零零工具结果超 50KB第 2 层砍掉远古消息低零消息过时第 3 层清理老工具输出中低零缓存过期/数量超限第 4 层读时投影压缩中低上下文达 90%第 5 层全量摘要高高（一次 API 调用）上下文达 ~93%越往下代价越高，但效果也越强。
大部分场景下前三层就足够了，它们完全不需要额外的 API 调用，只是「搬运」和「裁剪」数据。
只有在极端情况下，才需要触发昂贵的全量摘要。
这种设计的另一个好处是各层相互协调。
第 2 层 Snip 会告诉第 5 层「我已经释放了多少 Token」，避免重复压缩。
第 4 层 Context Collapse 在第 5 层之前运行，如果它够用了，第 5 层就不触发。
每一层都在为下一层「减负」。

---

## 第二篇：多 Agent 架构设计

## 一、先搞明白 Multi-Agent 到底是个啥

在扒源码之前，我想先花一点篇幅，把 Multi-Agent 这个词的底层逻辑讲清楚。
因为我发现很多人连「为啥要有多 agent」都没想明白，光盯着代码看是看不懂的。

### 为什么一个 agent 不够用？

我们先回到最朴素的 agent 模型：一个 LLM + 一堆工具 + 一个循环。
你给它一个任务，它自己决定调什么工具、调几次，直到做完。
这就是经典的 agentic loop。
看起来挺强的是吧？
但一到真实项目里，问题就出来了。
想象你让一个 agent 去做这么一件事：「调研下 React 18 的新特性，然后在我的项目里实现一个 useTransition 的例子，最后帮我把代码评审一遍」。
这一套下来有三个麻烦：第一，上下文会爆炸。
调研阶段要看大量文档和 StackOverflow 链接，实现阶段要读项目代码，评审阶段又要重新读实现。
三个阶段的内容全塞到一个 agent 的上下文里，token 蹭蹭往上涨，后面直接塞不下。
第二，职责混乱。
一个 agent 既当研究员又当程序员又当评审员，它自己都不知道现在是什么角色，容易跑偏。
比如调研到一半就开始写代码了，代码写到一半又去查文档。
第三，没法并发。
一个 agent 一次只能做一件事，它在查文档的时候，项目代码就在那干等着。
单 agent 硬扛三件事老板派活的思路这时候 Multi-Agent 的思路就来了。
说白了，就像一个老板带团队：老板不自己一头扎进代码里，而是把任务拆成几块，派给不同的「专家」。
研究员去调研，工程师去写代码，评审员去挑错。
老板自己只负责看大方向、收结果、做决策。

这样一来：每个专家的上下文是干净的（只装自己领域的信息）；职责也清楚（研究员就好好查资料别去写代码）；多个专家还能同时开工。
这就是 Multi-Agent 的核心思想：把一个大任务拆给多个职责清晰的 agent 去做，它们之间通过某种方式通信和协作。

### Multi-Agent 的三种常见形态

绕开花哨的术语，Multi-Agent 系统在工业界落地时，一般就三种形态。
第一种，父子型。
主 agent 处理整个任务，遇到某个子问题时派一个 subagent 出去搞定，拿结果回来接着干。
这是最常见的，Claude Code 里的 Task 工具就是这种。
第二种，平级协作型。
几个 agent 职责对等，通过共享状态或者消息互相协作。
不过这种在工程上比较难落地，状态同步很麻烦。
第三种，主从型（Coordinator-Worker）。
有一个专门的「协调者 agent」，它自己不干活，只负责派 worker、收结果、做合成。
worker 之间互不通信，全靠协调者调度。
这种是高并发场景的标配。
Claude Code 源码里，常规 Subagent 对应父子型，Coordinator 模式对应主从型，Fork Subagent 是父子型的一个特殊优化版本（跟 cache 有关，后面讲）。

### subagent 在 Claude Code 里到底长啥样？

讲到这儿可能还有朋友有点虚：「subagent 听起来挺抽象，它在 Claude Code 里到底长啥样，看得见吗？
」我举个真实能感知的场景你就懂了。
你跟 Claude Code 说「调研一下这个项目的认证模块」，它自己判断一下：这活得派个「侦察兵」去干，而不是我亲自扎进去。
于是它在内部调了一个叫 Agent 的工具（对，这个工具的名字就叫 Agent），把任务交给一个叫 Explore 的内置 subagent 去跑。
Explore 带着一套精简的工具池（只有读文件、搜代码这些只读工具），带着一份独立的上下文，跑完调研把结果打包回来交给主 agent。
主 agent 收到结果后，该改代码改代码、该回答回答。
所以 subagent 不是什么玄学，说白了就是「主 agent 通过一个特定工具派出去的另一个独立 agent 实例」。
每一个 subagent 都是一个真实存在的执行单元，有自己的工具池、上下文、生命周期。
明白了这些，咱们就可以进入 Claude Code 的源码了。

## 二、Subagent 的隔离机制

在讲通信、讲并发之前，我想先从 Claude Code 多 agent 设计里最关键的一环讲起：隔离机制。
为什么隔离最关键？
你想想，多 agent 系统本质就是「一堆 agent 共处一个进程、共享一个底层运行时」。
如果隔离做得不好，一个 subagent 偷偷污染了父 agent 的状态、或者调了不该调的工具，整个系统就会乱成一锅粥。
Claude Code 在 subagent 启动时，把隔离做到了两个维度：工具隔离（不给子 agent 它不该有的工具）和 上下文隔离（不让子 agent 搅乱父 agent 的运行时状态）。
咱们一个一个看。
第一维度：给子 agent 发一个定制工具箱先说工具隔离。
这是 Claude Code 多 agent 设计里最容易被忽略，但又很重要的一环。
什么意思呢？
主 agent 拥有一大堆工具（读文件、写文件、执行命令、派 subagent、问用户问题等等几十个），但你不能把这堆工具原封不动地丢给 subagent。
为啥？
你想想，如果 subagent 也能调派新 subagent 的工具，那它就能派子子 agent，子子 agent 又派子子子 agent，层层嵌套没完没了，token 消耗直接起飞。
再比如主 agent 用来管理任务列表的工具，是给主 agent 的大脑用的，subagent 跟着瞎写会污染主 agent 的待办状态。
所以 Claude Code 给 subagent 发工具的思路是「按 agent 身份走三道准入门」：第一道门是「所有 subagent 通用黑名单」。
这道门里被禁的工具有几类：能派新 subagent 的工具：防止子再派孙、孙再派重孙的递归嵌套能主动问用户问题的工具：子 agent 不该抢主 agent 的对话权，用户是跟主 agent 说话的能切换规划模式的工具：规划模式是主 agent 用来跟用户对齐方案的，子 agent 没资格切能停止其他任务的工具：任务管理是主线程的专属权力，子 agent 乱停会天下大乱第二道门是「自定义 agent 多套一层黑名单」。
用户自己写的 agent（比如在项目里自己配的那种 Markdown agent）比内置 agent 要再严一点，因为用户写的没经过官方审核，多防一道更安全。
第三道门反过来，是「后台异步 agent 走白名单」。
这类 agent 是完全后台跑的，没法跟用户交互，所以只准用事先圈定好的一小批工具（读文件、搜代码、执行命令、编辑文件这些）。
白名单的哲学是「默认不准用，明确列出来的才能用」，比黑名单更保险。
三道门走下来，每个 subagent 拿到的都是一份量身定制的工具池，既够它干活，又不会越权。
这个机制在源码里其实就是一个过滤函数：// src/tools/AgentTool/agentToolUtils.ts:70
exportfunction filterToolsForAgent({ tools, isBuiltIn, isAsync, permissionMode }): Tools {
return tools.filter(tool => {
    if (tool.name.startsWith('mcp__')) returntrue// MCP 工具全放行
    if (ALL_AGENT_DISALLOWED_TOOLS.has(tool.name)) returnfalse
    if (!isBuiltIn && CUSTOM_AGENT_DISALLOWED_TOOLS.has(tool.name)) returnfalse
    if (isAsync && !ASYNC_AGENT_ALLOWED_TOOLS.has(tool.name)) {
      returnfalse
    }
    returntrue
  })
}
可以看到就是顺着「全局黑名单 → 自定义 agent 加严 → 异步白名单」这三道条件依次判定。
最后留下来的，才是这个 subagent 能用的工具。
这个设计看着简单，其实挺有工程智慧的。
我在设计自己的多 agent 系统时，就学到了一条原则：不要假设所有 agent 都能用所有工具，按 agent 类型做细粒度的权限控制。

### 第二维度：搭一个隔离的运行环境

说完工具，再来聊第二维度：上下文隔离。
这块是 Claude Code 多 agent 设计里最精髓的一块，我觉得全篇文章最值得细读的就是这一节。
先说问题。
父 agent 跑起来后有一个庞大的运行时上下文，里面装着很多东西：已经读过哪些文件、每个文件读到第几行、全局的 UI 状态、中止信号、权限状态、任务注册表等等。
现在轮到你做设计。
要派一个 subagent，这份庞大上下文怎么传给它？
你脑子里很可能蹦出两个直觉方案：A 完全共享（父那份直接给子用）、或者 B 完全新建（给子一份全新空的）。
先别看下面，自己想想哪个对？
…先说 A 不行，举个具体场景你就懂：父 agent 已经读过 file.ts 的前 100 行，子 agent 拿过去接着读到 200 行。
这下父 agent 那边「文件读到哪了」的缓存被刷成 200 了，下次它要读这文件就以为自己已经读过 200 行了，直接跳过。
子的一次操作，把父的视图污染了。
再说 B 也不行：用户按 Ctrl+C 想中止整个任务，主线程把中止信号广播出去，结果子 agent 因为是全新上下文收不到这个信号，对外面发生啥一无所知，自顾自继续跑。
子 agent 跟世界完全脱节了。
发现了吧，两个极端都走不通。
那 Claude Code 怎么办？
答案是一个很巧妙的折中思路：不按「整体」决策，而是按「字段」决策。
每一项状态单独判断该克隆、该共享、该屏蔽，还是该新建。
我把 Claude Code 在这件事上的四个关键决策挑出来，用大白话讲一遍：

- 决策一：「读文件的缓存」要复制一份给子 agent这个缓存存的是「这个文件读过没、读到第几行」。
如果父子共享，子 agent 读了某个文件，父 agent 会误以为自己也读过，下次跳过不读，数据就错了。
所以要复制一份独立的给子 agent，子怎么折腾都不影响父的文件视图。

- 决策二：「改全局状态」这件事对子 agent 直接关闭全局 UI 状态是主线程用 React 在管的。
如果异步 subagent 也能改，就会出现「两边同时改同一份状态、抢起来对不上」的问题，界面就花了。
所以 Claude Code 干脆把 subagent 的「写全局状态」这个权力完全关闭掉，改成空操作，一了百了。

- 决策三：但「注册后台任务」这条通路得保留这里有个小细节值得讲。
既然子 agent 的写权力关掉了，那它自己起的后台进程（比如在后台跑一条 bash 命令）怎么登记到全局任务表？
Claude Code 专门开了一个小口子：其他写全局的口都堵死，唯独「注册/结束后台任务」这条路留着。
不然子 agent 起的后台进程就变成「没爹的孤儿进程」，永远在后台跑没人回收。

- 决策四：给每个 subagent 发独立 ID、深度代代 +1每派一个 subagent，都给它一个独立的 ID，并且在父 agent 的深度基础上 +1。
这样系统能随时知道「当前这个 agent 处于嵌套的第几层」。
深度超过阈值（比如 5 层）就报警甚至强制停止，防止意外嵌套失控。
这四个决策其实回答了四类问题：信息怎么传、状态怎么写、通路怎么留、身份怎么追踪。
对应到源码里，就是一个叫 createSubagentContext 的函数，我把最能说明上面四个决策的部分精简出来：// src/utils/forkedAgent.ts:345
exportfunction createSubagentContext(parentContext, overrides): ToolUseContext {
return {
    // 

- 决策一：文件读缓存克隆一份
    readFileState: cloneFileStateCache(parentContext.readFileState),
    // 

- 决策二：写全局状态直接设为空操作
    setAppState: () => {},
    // 

- 决策三：但任务注册的通路例外保留
    setAppStateForTasks: parentContext.setAppStateForTasks ?? parentContext.setAppState,
    // 

- 决策四：独立 ID + 深度 +1
    agentId: overrides?.agentId ?? createAgentId(),
    queryTracking: {
      chainId: randomUUID(),
      depth: (parentContext.queryTracking?.depth ?? -1) + 1,
    },
    // ...其他字段略
  }
}
你看这几行代码，一一对应上面讲的四个决策：克隆缓存、关掉写权限、保留任务通路、发独立 ID。
看完这块，我的感受是：所谓上下文隔离，不是一刀切地「全隔离」或者「不隔离」，而是按每个状态的语义单独决策。
这个细腻劲儿，正是 Claude Code 这种工业级产品稳定跑的根基。
走完「工具隔离」和「上下文隔离」这两道门，一个 subagent 就拿到了干净的工具池 + 干净的运行环境，可以独立跑起来了。
那父 agent 和这个跑起来的 subagent，又是怎么互相说话的呢？
下一章见真章。

## 三、父子 Agent 是怎么通信的

隔离机制搞定了，但隔离只是开始，真正决定一个多 agent 系统好不好用的，是它们之间怎么通信。
这一章我来讲 Claude Code 的通信方式。
先抛一个问题：subagent 跑起来之后，父 agent 怎么给它发新指令？
subagent 又怎么把结果交回去？
为什么不用函数调用？
我建议你先停个 10 秒，自己想想：如果让你来设计这套通信，你会怎么写？
大概率你脑子里第一反应是「父 agent 调个函数，等 subagent 跑完返回」对吧？
这跟我们平时写 RPC 调远程服务的思路一模一样，太自然了。
但我接着追问你两个问题，你看你能不能答上来：第一个追问：如果 subagent 是个跑 5 分钟的代码评审任务，那这 5 分钟里，父 agent 能干啥？
用户跟父 agent 说话又会发生什么？
第二个追问：如果父 agent 想同时派 5 个 subagent 并行调研 5 个模块，你这个「调函数等返回」的方案要怎么改？
是不是有点卡了？
第一个追问的答案是：父 agent 啥也干不了，被同步阻塞死了。
用户在这 5 分钟里跟它说话也没反应。
第二个追问的答案是：要么 5 个 subagent 全在主线程里阻塞排队，要么得手动搓各种并发代码，整体会乱成一锅粥。
Claude Code 正是看穿了这两个坑，才换了一个完全不一样的路子：消息驱动。
想象每个 subagent 是公司里一个带「信箱」的独立员工。
父 agent 要给它布置新活，就往它信箱里扔一张字条走人，不站在那儿等。
subagent 自己干完活了，通过另一条信道把结果送回主 agent 的案头。
这个「信箱 + 字条」的模型，本质上就是消息队列 + 异步通知。
没有直接的函数返回，没有主线程阻塞，所有沟通都是消息。
subagent 的员工档案为了支持这套模型，Claude Code 给每个 subagent 建了一份「员工档案」：一个对象，里面记着这个 subagent 的 ID、当前状态（等待中/跑步中/已完成/失败/被停了）、它的信箱（待处理消息数组）、已经产生的结果、进度信息等等。
所有跟 subagent 有关的读写（父要发消息，子要改状态），都通过全局的 task 表里这份档案来进行。
对应到源码里的类型定义大致长这样：// src/tasks/LocalAgentTask/LocalAgentTask.tsx:116
export type LocalAgentTaskState = TaskStateBase & {
  type: 'local_agent';
  agentId: string;               // 子 agent 唯一 ID
  prompt: string;                // 初始任务
  agentType: string;
  status: TaskStatus;            // pending/running/completed/failed/killed
  result?: AgentToolResult;      // 完成后的结果
  progress?: AgentProgress;      // 进度
  isBackgrounded: boolean;       // 是否已转后台
  pendingMessages: string[];     // 信箱：父 agent 扔进来的待处理消息
  messages?: Message[];
};
重点关注的是 pendingMessages 数组，它就是我们前面说的「信箱」，父 agent 往里扔字条，子 agent 自己来捡。

### 父 → 子：扔字条 + 子自己来取

父 agent 要给跑着的 subagent 发指令的流程，拆开看就是两步：

#### 

- 第一步：父往信箱扔字条。
父 agent 在自己的 agentic loop 里调用一个叫 SendMessage 的工具，工具内部做的事情很简单：往目标 subagent 档案的信箱末尾追加一条消息，然后立刻返回。
父 agent 扔完走人，不等子 agent 看。

#### 

- 第二步：子在循环边界自己捡字条。
subagent 自己的 agentic loop 在每一轮工具调用结束后，都会去瞄一眼自己的信箱。
如果有新字条，就把这些字条作为「用户消息」注入自己的对话历史，然后带着新消息进入下一轮 LLM 调用。
这里有个细节设计特别巧：如果子 agent 已经干完活停下来了（completed 或者被手动停了），父 agent 发 SendMessage 会怎样？
Claude Code 的做法是：自动把它唤醒。
从磁盘上那份已经保存的对话 transcript 里，把子 agent 的完整对话历史恢复出来，拼上新消息，重新跑起来。
这个唤醒机制很妙，意味着 subagent 即使完成了也不是「死了」，父 agent 随时可以叫醒它继续干。
对应到源码，SendMessage 工具里的核心逻辑长这样：// src/tools/SendMessageTool/SendMessageTool.ts:800
const task = appState.tasks[agentId]
if (isLocalAgentTask(task) && !isMainSessionTask(task)) {
  if (task.status === 'running') {
    queuePendingMessage(agentId, input.message, context.setAppStateForTasks)
    return { data: { success: true, message: 'Message queued...' } }
  }
  // 任务已停止，自动唤醒从 transcript 里恢复
  const result = await resumeAgentBackground({ agentId, prompt: input.message, ... })
}
可以看到就是两个分支：正在跑就扔信箱，已经停了就唤醒。
「扔信箱」这个动作本身的实现就 4 行：// src/tasks/LocalAgentTask/LocalAgentTask.tsx:162
export function queuePendingMessage(taskId, msg, setAppState): void {
  updateTaskState<LocalAgentTaskState>(taskId, setAppState, task => ({
    ...task,
    pendingMessages: [...task.pendingMessages, msg]
  }));
}
纯纯的「追加到数组末尾」。

### 子 → 父：把通知伪装成用户消息

反方向呢？
subagent 跑完一个任务，怎么告诉父 agent「我干完了」？
最直觉的做法是：给主线程发一个「工具返回结果」事件。
但 Claude Code 玩得更骚气，它的设计是：把完成通知拼成一段 XML，伪装成一条用户消息，塞给父 agent 的对话历史。
父 agent 那边看到的就像用户发了一条新消息过来，长这样：<task-notification>
<task-id>agent-a1b</task-id>
<output-file>/tmp/xxx.txt</output-file>
<status>completed</status>
<summary>Agent "Investigate auth bug" completed</summary>
<result>Found null pointer in src/auth/validate.ts:42...</result>
<usage>
  <total_tokens>12345</total_tokens>
  <tool_uses>8</tool_uses>
  <duration_ms>34567</duration_ms>
</usage>
</task-notification>
📌 配图建议：task-notification XML 渲染示意，高亮各个 tag 的含义为啥要搞 XML 不用结构化对象？
 这个设计有它的巧妙之处，我特意想明白过。
第一，LLM 对 XML 非常友好。
Anthropic 训练 Claude 的时候就强调了 XML 的结构化表达。
你把 XML 塞到 prompt 里，LLM 能很自然地解析出语义，不用额外教它。
第二，XML 是纯文本，可以直接塞进对话历史。
如果是结构化对象，还得额外走个「工具结果」的字段结构，流程更复杂。
第三，它伪装成用户消息，天然地复用了 agentic loop 的处理逻辑。
父 agent 不需要额外的状态机去「等通知」，它就像收到一条新的用户输入一样处理。
这种「把系统事件伪装成对话」的设计思路，在 LLM 应用里是非常值得学的一招。
对应到源码里，生成这段 XML 的代码就是在拼字符串：// src/tasks/LocalAgentTask/LocalAgentTask.tsx:197
const message = `<${TASK_NOTIFICATION_TAG}>
<${TASK_ID_TAG}>${taskId}</${TASK_ID_TAG}>
<${OUTPUT_FILE_TAG}>${outputPath}</${OUTPUT_FILE_TAG}>
<${STATUS_TAG}>${status}</${STATUS_TAG}>
<${SUMMARY_TAG}>${summary}</${SUMMARY_TAG}>${resultSection}${usageSection}
</${TASK_NOTIFICATION_TAG}>`;
enqueuePendingNotification({ value: message, mode: 'task-notification' });
拼完就扔到主 agent 的待处理消息队列里，等主 agent 下一轮循环时当作一条用户消息来处理。

### 为什么要自动后台化？

再讲一个通信体系里的重要设计：auto-background。
subagent 跑起来之后，父 agent 其实要等一会。
如果 subagent 很快跑完（比如 30 秒内），父 agent 就在前台阻塞等，像一次普通工具调用，完事就拿结果继续。
但如果 subagent 跑超过 2 分钟还没完，Claude Code 会自动把它转到后台，让父 agent 可以先继续干别的。
2 分钟后 subagent 真完成了，通过前面说的 task-notification 把结果送回。
这个设计本质上是把同步工具调用自动降级成异步通知的优化。
没有它，长任务会一直占着父 agent 的执行权，用户也没法跟父 agent 继续对话。
源码里这个「2 分钟阈值」就是一个常量开关：// src/tools/AgentTool/AgentTool.tsx:72
function getAutoBackgroundMs(): number {
  if (isEnvTruthy(process.env.CLAUDE_AUTO_BACKGROUND_TASKS) 
      || getFeatureValue_CACHED_MAY_BE_STALE('tengu_auto_background_agents', false)) {
    return 120_000;  // 2 分钟
  }
  return 0;
}

### 回头看通信设计的全貌

到这儿我们把父子通信的两个方向都讲清楚了：父 → 子：调 SendMessage 工具把消息写进子 agent 的信箱 → 子 agent 下一轮循环边界自己读取。
子 → 父：子 agent 把完成通知拼成 XML 消息 → 伪装成用户消息注入父 agent 对话。
整个通信体系就两个关键字：异步 + 消息。
没有直接函数调用，没有锁，没有回调地狱，全靠读写共享的任务状态和消息队列。
这种设计有个特别大的好处：天然支持多 subagent 并发。
因为父 agent 从来不阻塞等子，它可以同时派 5 个 subagent，谁先完成谁先给它发通知，父 agent 按到达顺序处理就行。
下一章，我们再讲一个特别精妙的优化：Fork Subagent。

## 四、Fork Subagent：省钱又省延迟的隐藏大招

前面讲的常规 subagent 已经是主流玩法了，但 Claude Code 还有一个更精妙的机制，叫 Fork Subagent。
这个机制有点隐蔽，用起来是透明的，但对成本和延迟的优化非常显著。
我先抛两个问题让你估算下，先别往下翻看答案：第一，Claude Code 的 system prompt 大概有多长？
是几百 token、几千 token，还是上万 token？
 第二，每派一个 subagent，如果它有自己独立的 system prompt，LLM API 那边对这段 prompt 是从头算一遍，还是有办法复用？
subagent 的隐藏成本公布答案：Claude Code 的 system prompt 长度是上万 token，里面塞了大量的工具说明、规范约定、用户上下文。
而每派一个 subagent，如果它有独立的 system prompt（内置的 Explore、Plan 这些都有独立的），LLM API 那边就得对这一万多 token 重新从头算一遍，就跟没见过似的。
这有两个代价：钱（input token 重新算钱）和延迟（首 token 等更久）。
在生产环境里，subagent 派得越频繁，这个开销线性放大，是个很可怕的成本黑洞。
Anthropic 有个 prompt 缓存机制可以缓解这事。
简单说：API 请求里如果前缀跟之前某次请求一样，这段前缀可以不重新算，直接走缓存，价钱只要原来的 10%，延迟也大幅降低。
到这儿我再问你一个关键的：prompt 缓存命中的条件是「内容大致相同」就行，还是「字符级别相同」，还是「字节级别完全相同」？
再猜一下。
公布：是最严格的那个，字节级别完全相同。
系统 prompt 一个字不一样、工具列表顺序不一样、甚至空格位置不一样，都会直接没命中缓存。
是不是比你想的严格多了？
那既然这么严，能不能设计一种 subagent，它的 system prompt 和工具池跟父 agent 完全一样，这样就能复用父的缓存了？
这就是 Fork Subagent 的起点。

### Fork 的核心思路：派一个「字节级相同」的分身

Fork Subagent 的直觉是这样的：派一个子 agent 出去干活，但这个子 agent 的 API 请求前缀跟父 agent 一模一样，让 Anthropic 那边一看：「哦这个前缀我认识」，走缓存。
这里的「一模一样」要做到什么程度？
字节级。
一个字节不对都不行。
具体要对齐哪些东西呢？
有五样必须跟父 agent 完全一致：系统 prompt 的内容（最核心的，对齐第一位）用户上下文（拼在消息前的那部分动态内容，比如当前项目的 CLAUDE.md 内容）系统上下文（拼在 system prompt 后的环境信息）工具池的顺序和定义（工具的字段结构会被序列化进 API 请求，顺序都不能变）对话历史的前缀（决定了 user/assistant 消息序列中「从哪里开始分叉」）这五样只要有一样跟父 agent 字节不一致，缓存就直接没了。
对应到源码里，Claude Code 专门定义了一个类型（CacheSafeParams），把这五项打包：// src/utils/forkedAgent.ts:57
exporttype CacheSafeParams = {
/** System prompt - 必须跟父完全一致 */
  systemPrompt: SystemPrompt
/** User context - 拼接在消息前，影响缓存 */
  userContext: { [k: string]: string }
/** System context - 拼接在 system prompt 后，影响缓存 */
  systemContext: { [k: string]: string }
/** 工具池、模型等所在的上下文 */
  toolUseContext: ToolUseContext
/** 父 agent 的消息前缀，用于缓存共享 */
  forkContextMessages: Message[]
}
你看这个类型的意思很明显：凡是会影响缓存命中的字段，我全列在这儿，你 Fork 的时候严格按这份清单跟父 agent 对齐。

### 一个有意思的细节：system prompt 不重新生成

Fork Subagent 的合成定义里有个有意思的细节，值得单独说。
正常一个 subagent 有个生成 system prompt 的函数，跑的时候现生成一段 prompt 文本。
但 Fork 机制用的那个 subagent 的生成函数直接返回空字符串：// src/tools/AgentTool/forkSubagent.ts:60
export const FORK_AGENT = {
  agentType: FORK_SUBAGENT_TYPE,
  tools: ['*'],             // 用父的完整工具池
  maxTurns: 200,
  model: 'inherit',          // 继承父的模型
  permissionMode: 'bubble',  // 权限弹窗浮到父终端
  source: 'built-in',
  getSystemPrompt: () => '', // 返回空串！

} satisfies BuiltInAgentDefinition
这不是偷懒，而是精心设计的。
为啥要返回空串？
因为 Fork subagent 的 system prompt 根本不走这个函数生成，而是直接用父 agent 已经渲染好的那份字节。
原因很简单：如果重新调一次生成函数，里面可能有些小差异（比如某个功能开关的缓存状态变了、某个动态字段的值变了），生成出来的 prompt 跟父 agent 就可能差一个字符，缓存就没了。
最稳的办法是：把父 agent 那边已经渲染出来的 prompt，作为字节原样拿过来用，一个字节都不动。
这个细节非常工业级，普通人写 agent 系统根本想不到。

### 什么时候用 Fork，什么时候用常规 subagent？

Fork 机制不是万能的，它的适用场景很特定：你希望子 agent 完全继承父 agent 的整个上下文（对话历史、system prompt、工具池），只是「派个分身去试试另一条路」。
比如「Ctrl+F 生成 PR 描述」「运行 /btw 命令做 post-turn 总结」，这些任务需要父 agent 的完整上下文，但又不希望污染父 agent 的主循环。
相反，如果你的任务有明确的专业分工（比如派一个专门搜代码的 agent、派一个专门做规划的 agent），那就用常规 subagent，它们的 system prompt 是定制的，Fork 机制反而不适用。
还有一个关键点：Fork 机制和 Coordinator 模式是互斥的。
Coordinator 模式下主 agent 已经是个纯协调者了，它派的 worker 本来就是异步的，不需要 Fork 这种「轻量分身」机制。
两个机制职责重叠，就只留一个：// src/tools/AgentTool/forkSubagent.ts:32
exportfunction isForkSubagentEnabled(): boolean {
if (feature('FORK_SUBAGENT')) {
    if (isCoordinatorMode()) returnfalse// 互斥！

    if (getIsNonInteractiveSession()) returnfalse
    returntrue
  }
returnfalse
}

### Fork 的工程启示

Fork 机制我想单独说下它对我们的启示。
很多人做 agent 系统只关心「能不能跑起来」，不关心「跑起来要花多少钱」。
但在生产环境，这两个是一回事。
Claude Code 靠 Fork 机制，在缓存友好的场景下能把 subagent 的成本降到原来的 10% 左右。
这意味着什么？
意味着你的 subagent 可以调得更频繁。
原本成本考虑不敢派的活，现在都能派了，这反过来又让整个 agent 系统的能力边界扩大了。
所以成本优化本身就是能力的一部分。
这个思路我觉得对自建 agent 系统的朋友特别重要。
好了，讲完 Fork，下面进入整篇文章最「多 agent」的一章：Coordinator 模式。

## 五、Coordinator 模式：真正的多 Agent 并行协作

前面讲的 subagent（不管是常规的还是 Fork 的），本质都是父子结构：父 agent 派一个子，自己该干啥干啥，子完成了通知一声。
但如果你的任务量很大，需要一堆 agent 同时开工呢？
比如一个大的代码迁移，要并行调研 10 个模块。
这时候父子结构就显得单薄了。
Claude Code 为此设计了一个专门的模式：Coordinator 模式。
这是 Claude Code 多 agent 设计里最「多 agent」的部分，也是最能打的地方。

### Coordinator 模式的启用

这个模式不是默认开的，要显式打开。
需要同时满足两个条件：编译时的功能开关和**运行时的环境变量 CLAUDE_CODE_COORDINATOR_MODE=1**。
// src/coordinator/coordinatorMode.ts:36
export function isCoordinatorMode(): boolean {
  if (feature('COORDINATOR_MODE')) {
    return isEnvTruthy(process.env.CLAUDE_CODE_COORDINATOR_MODE)
  }
  return false
}
开启之后，主 agent 的行为模式会发生根本性变化。

### 核心设计：主 agent 退化成「纯协调者」

常规模式下，主 agent 是「全能型选手」：它读代码、写代码、跑测试、做规划全都干，只在需要时才派 subagent 帮一把。
Coordinator 模式下，主 agent 不干实际工作了，它只做三件事：派 worker、收结果、合成答案。
这个角色转换是通过主 agent 的 system prompt 强制约束出来的。
打开源码里那段 prompt，开头就写得很明白：You are Claude Code, an AI assistant that orchestrates software engineering 
tasks across multiple workers.

## 1. Your Role
You are a **coordinator**. Your job is to:
- Help the user achieve their goal
- Direct workers to research, implement and verify code changes
- Synthesize results and communicate with the user
- Answer questions directly when possible, don't delegate work 
  that you can handle without tools
翻译一下：你的身份是协调者，你的工作是指挥 worker 去做研究、实现、验证，然后自己合成结果跟用户交流。
能自己回答的问题不要派人去做。

### 三大内部工具

既然主 agent 要协调，就得有专门的协调工具。
Coordinator 模式下，主 agent 多了一套「团队管理」工具箱：派 worker 的工具：派一个新 worker 出去干某件具体的活，派完立刻返回 worker 的 ID。
创建/解散团队的工具：批量管理 worker 组。
给 worker 发消息的工具：给已经派出去的 worker 发后续指令（也就是前面讲的 SendMessage），因为 worker 的上下文还在，续命比重新派一个更省钱。
合成最终输出的工具：协调者合成完答案后，通过这个工具把最终回复交给用户。
停止 worker 的工具：当协调者意识到某个 worker 跑错方向时，把它停掉省 token。
这套工具放在一起，协调者就有了一整套指挥团队的 API。
📌 配图建议：协调者工具箱图，把五个工具画成五个按钮，标注每个按钮的作用对应到源码里，这组「只有协调者能用」的内部工具是这样定义的：// src/coordinator/coordinatorMode.ts:29
const INTERNAL_WORKER_TOOLS = new Set([
  TEAM_CREATE_TOOL_NAME,       // 创建 worker 团队
  TEAM_DELETE_TOOL_NAME,       // 解散团队
  SEND_MESSAGE_TOOL_NAME,      // 给 worker 发消息
  SYNTHETIC_OUTPUT_TOOL_NAME,  // 合成最终输出给用户
])

### 并行才是真本事

Coordinator 模式的 prompt 里有一句我特别喜欢：Parallelism is your superpower. Workers are async. Launch independent workers concurrently whenever possible, don't serialize work that can run simultaneously and look for opportunities to fan out.翻译一下：并行是你的超能力，worker 全是异步的，能并行的绝不串行，多找机会一口气派一堆出去。
这句话背后是一个很关键的工程事实：Claude Code 的派 worker 工具调用可以在同一条 assistant 消息里出现多次，底层会一起并发执行，不是一个跑完再跑下一个。
所以协调者要做的就是在一次 LLM 回合里，一口气生成多个派 worker 的工具调用：派 worker 调研 auth 模块
派 worker 调研 session 模块
派 worker 调研 token 模块
这三个调用同时启动，三个 worker 同时干活，协调者等通知一条条返回。

对比一下：串行：派 worker1 → 等 → 结果 → 派 worker2 → 等 → 结果 → 派 worker3... 用户等十分钟并行：同时派三个 worker → 三份结果陆续到 → 用户等三分钟多一点这就是「并行是超能力」的真正含义。
工业级多 agent 系统，没有并行就没有可用性。

### 协调者的「任务流水线」

Coordinator 模式下，一个典型的任务流程被切成四个阶段：阶段谁来做目的调研Workers（并行）调查代码库、找文件、理解问题合成协调者本人读完发现、理解问题、写实现规格实现Workers按规格做具体修改、提交验证Workers测试改动是否真的工作注意中间的「合成」阶段是协调者亲自做，这是协调者存在的意义：理解全局，做决策。
prompt 里反复强调：不要偷懒让 worker「based on your findings, implement the fix」，而是自己把 findings 读懂、写成具体的规格再派下去。
这是一个非常重要的 multi-agent 设计哲学：协调者必须「理解」而不能「转发」。
如果协调者只是转发，它就没有存在价值，worker 直接跟用户对话就行了。

### Continue vs Spawn：老 worker 还是新 worker？

协调者要持续派活，遇到一个新任务，是给老 worker 发消息续命，还是派个新 worker 从头开始？
这是个有经验才能做好的决策。
Claude Code 的 prompt 里给出了一张决策表，我总结一下核心逻辑：如果新任务跟 worker 现有上下文高度相关（比如刚查的文件现在要改），续命老 worker，因为它已经「知道」那些文件了。
如果新任务跟 worker 现有上下文没关系，或者之前 worker 的工作走偏了，派新 worker，避免旧上下文干扰判断。
验证这种需要「新鲜眼光」的工作，永远派新 worker，不能让刚写完代码的 worker 自己验自己。
这个设计其实也挺反映人类团队合作的直觉：有的活就该让懂上下文的人接着干（沟通成本低），有的活就该换个人做（避免认知偏差）。

### Worker 的工具限制

Coordinator 模式下，worker 拿到的工具有什么不同？
关键在于：协调者专属的那套内部工具（创建团队、发消息、合成输出等等），不给 worker 用。
worker 不需要再去协调别人，它的活是干事情。
这其实是一个递归防护：如果 worker 也能派 worker，整个系统就变成递归树了，没完没了。
通过工具白名单把 worker 的「派人权」收回，让系统结构保持「一个协调者 + 一堆 worker」的扁平形态。

### 跟常规 subagent 对比

讲完这些我们对比一下 Coordinator 模式和常规 subagent：维度常规 subagentCoordinator 模式主 agent 角色全能选手纯协调者subagent 执行同步（2 分钟后才转后台）默认异步并发程度偶尔并发最大化并发适合场景单个任务 + 临时帮手大任务 + 高并发拆解系统形态父子树协调者 + worker 扁平层

### Coordinator 模式的工程启示

讲完 Coordinator，我想提炼几条值得学的设计思想。
第一，角色分离。
协调和干活是两件事，不要让同一个 agent 身兼二职。
角色清晰的系统更稳定。
第二，并发优先。
异步 + 消息队列是并发的基础，有了这套基础，多 agent 才能真正发挥威力。
第三，合成不转发。
协调者要理解中间结果，不能把它当传话筒。
这是 Multi-Agent 系统里最容易踩坑的一点。
第四，扁平不递归。
通过工具权限把层级限制在两层（协调者 + worker），避免失控的递归嵌套。

## 六、5 条 Multi-Agent 设计原则

Claude Code 的源码扒得差不多了。
我把前面讲的所有东西浓缩一下，沉淀成 5 条可以直接用到自己项目、也可以直接用到面试答案里的设计原则。

### 原则 1：上下文隔离要按字段粒度做

这是我最想强调的一条。
很多 agent 框架的「隔离」就是粗暴地给 subagent 一个空 context，结果缺这缺那一堆 bug。
Claude Code 的做法是：每个状态单独决策。
读文件缓存克隆（避免污染），写全局状态关掉（避免两边抢），任务注册通路保留（不然孤儿进程没人回收），深度计数 +1（可追踪，防失控嵌套）。
做多 agent 系统时，对着父 agent 的每项状态问一句：「子 agent 拿这个状态干啥？
会不会影响父？
」，就能避开大部分坑。

### 原则 2：通信走消息，不走函数调用

父 → 子：写入子 agent 的消息队列，子 agent 下一轮循环自己读取。
子 → 父：把完成通知包装成 XML 消息，伪装成用户消息注入父 agent 对话。
这套模型的好处：天然异步、天然支持并发、天然兼容 agentic loop、天然持久化（消息都能落盘）。
如果你问面试官「你们的多 agent 之间怎么通信」，把这套答出来，基本就到位了。
原则 3：工具权限要分级管控全局黑名单（防递归、防乱问用户），类型黑名单（自定义 agent 更严），异步白名单（后台 agent 只能用子集）。
每种 agent 按自己的场景配工具，不要一刀切。
原则 4：缓存友好是一种架构能力API 成本和延迟对生产环境 agent 来说是能力的一部分。
设计 subagent 的时候，考虑它的 prompt 前缀能不能复用父 agent 的缓存，能省 80-90% 的成本。
Claude Code 那套「严格锁定缓存前缀 + 复用父 agent 已渲染字节」的思路，是这方面的教科书式实现。
原则 5：并行优先 + 协调者合成真正的多 agent 系统威力在并发。
通过异步消息和消息队列做基础，通过协调者做合成，避免「大 agent 大循环什么都自己扛」的窘境。
并且协调者要亲自合成，不能当传话筒。
这 5 条原则背后，其实都能看到 Claude Code 源码里的清晰落点。
我建议你别光记这些原则，下次看到 Multi-Agent 相关的东西，都拿这 5 条去对照，会迅速看出对方系统的深浅。
