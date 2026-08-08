#!/usr/bin/env bash
# AI Lab — Agent 批复条件叫号与通知路由脚本
#
# 逻辑规则:
# 1. 检查 Inbox 指定单据中的 Supervision 审核结论；
# 2. 若结论包含 "需修改" / "Requires Modification" / "否决" ➔ 路由通知 main (重新修改方案)；
# 3. 若结论包含 "批准" / "Approved" / "待实施" / "通过" ➔ 路由通知 coder (indep-coder 执行代码 Patch)；
# 4. 若结论包含 "Coder 开发情况总结" / "开发完成" / "待二次验收" ➔ 路由通知 Auditor (进行二次验收)。

set -euo pipefail

DOC_PATH="${1:-}"

if [ -z "${DOC_PATH}" ]; then
  echo "❌ 用法: bash scripts/dispatch_agent_notice.sh <inbox_doc_path>"
  echo "示例: bash scripts/dispatch_agent_notice.sh \"AI Lab/00_Inbox/2026-08-08-agent协议签署-solution.md\""
  exit 1
fi

if [ ! -f "${DOC_PATH}" ]; then
  echo "❌ 错误: 文件不存在 -> ${DOC_PATH}"
  exit 1
fi

echo "========================================================"
echo "  AI Lab Agent 条件叫号与通知分发器 (Post-Approval Dispatcher)"
echo "========================================================"
echo "📄 正在解析单据: ${DOC_PATH}"

CONTENT=$(cat "${DOC_PATH}")

# 1. 优先判定批准/待实施 (推进给 Coder)
if echo "${CONTENT}" | grep -qiE "(评估结论|审核结论).*?(批准|Approved|待实施|通过)"; then
  echo "✅ 识别结论: [批准 / 待实施] -> 路由至 coder (indep-coder)"
  echo "--------------------------------------------------------"
  echo "📢 微信叫号指令: coder 按照 Inbox 单据 ${DOC_PATH} 的批复意见执行代码开发"
  echo "--------------------------------------------------------"
  echo "PROMPT: coder (indep-coder) 方案已批准！请读取 ${DOC_PATH} 中的【结构化验收清单】，开始代码 Patch 与测试。"

# 2. 判定需修改/否决 (退回给 Main)
elif echo "${CONTENT}" | grep -qiE "(评估结论|审核结论).*?(需修改|Requires Modification|否决|Rejected)"; then
  echo "⚠️ 识别结论: [需修改 / 否决] -> 路由至 main (重新迭代方案)"
  echo "--------------------------------------------------------"
  echo "📢 微信叫号指令: main 请查看 Inbox 单据 ${DOC_PATH} 并根据批复意见修改方案"
  echo "--------------------------------------------------------"
  echo "PROMPT: main 已经收到批复意见，请读取 ${DOC_PATH} 中的【Supervision 审核批复】节，按意见修改方案。"

# 3. 判定 Coder 开发完成 (推进给 Auditor 验收)
elif echo "${CONTENT}" | grep -qiE "Coder 开发情况总结|开发完成|待二次验收"; then
  echo "🔍 识别结论: [Coder 完成开发] -> 路由至 Auditor (二次只读验码)"
  echo "--------------------------------------------------------"
  echo "📢 微信叫号指令: supervision 验证 Inbox 单据 ${DOC_PATH} 的代码成果"
  echo "--------------------------------------------------------"
  echo "PROMPT: Auditor 请提取 Git Commit SHA，对照 ${DOC_PATH} 中的【结构化验收清单】进行二次只读验码。"

else
  echo "ℹ️ 单据状态解析中 (待进一步明确审核结论)..."
fi

echo "========================================================"
