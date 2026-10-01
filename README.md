# workbuddy-zcode-proxy

把腾讯 WorkBuddy 桌面端的模型额度接进 ZCode：一个纯本地的 Node 代理 + 一份 ZCode 供应商注册配置。装完之后 ZCode 模型列表里多出一个 WorkBuddy 分组，15 个模型直接选，消耗的是自己 WorkBuddy 账号的积分，和平时在 WorkBuddy 里用一样。

只做三件事：

1. **协议翻译**。ZCode 走 OpenAI 兼容协议调 `127.0.0.1:8787`，代理把请求翻译成 WorkBuddy 网关（`copilot.tencent.com/v2/chat/completions`）的原生格式转发，SSE 回流清洗后交给 ZCode。temperature / max_tokens / 思考档位按服务端下发的模型配置强制对齐，官方从不赋值的字段一律剥掉。
2. **令牌解密**。WorkBuddy 5.6.2 起 accessToken 落盘变成 AES-256-GCM 信封（`$wbEncrypted`），不再有明文。代理按逆向出的 WB-AAD v1 规范在内存里解密，令牌刷新自动跟随，明文令牌不落盘。
3. **通道适配**。网关有两道校验：令牌信封（对应 401）和 system 角色提示词的通道扫描（对应 400 `code 11128`）。第二道的解法是把 system/developer 内容挂 user 角色下发——内容零改写，只换角色标签。

所有请求走本机，代理只监听 `127.0.0.1`，凭证不离开你的电脑。

## 实测环境

WorkBuddy 5.6.2 + ZCode 3.14.4 + Windows，2026-10-01。老版本 WorkBuddy（5.5.6，明文 token）向下兼容。

## 部署

前提：本机装了 WorkBuddy 并登录过（代理靠读它的登录态文件拿凭证）、ZCode 已安装、Node.js ≥ 18。

1. 把本仓库放进一个英文无空格目录（示例用 `D:\AI_Proxy`）。
2. **生成令牌信封密钥**（5.6.2+ 必需，老版本跳过）：密钥不在磁盘任何文件里，只存在于运行中的 WorkBuddy 桌面端进程内存。桌面端开着的时候跑：

   ```
   powershell "Get-CimInstance Win32_Process -Filter \"Name='WorkBuddy.exe'\" | Where-Object { $_.CommandLine -notmatch '--type=' } | Select-Object ProcessId"
   python scan_mem.py <keyId> <主进程PID>
   ```

   `<keyId>` 取自 `workbuddy-desktop.info` 里 `auth.accessToken.envelope` base64 解开后的 `keyId` 字段（本机实测为 `9127dea1b44020a7`）。脚本按 keyId 自校验，命中后生成 `wb-key-payload.json`。这个文件等价于账号凭证的一部分，**不要分享、不要提交**（已在 .gitignore）。该密钥跨重启稳定，正常只需提取一次。
3. 启动：双击 `start-proxy.bat`（停止用 `stop-proxy.bat`）。
4. **注册进 ZCode**：ZCode 3.14.4 读的是 `%USERPROFILE%\.zcode\v2\provider_config.json`（`config.json` 里的 provider 键不生效）。三处必须同写，缺 `providerOrder` 会"显示但不可用"：
   - `config.providerOrder` 加入 `"workbuddy-provider"`；
   - `config.providerConfigRules.providerRules[]` 新增一条：`api.type = "openai-chat-completions"`、`api.baseUrl = "http://127.0.0.1:8787/v1"`、`personalModelIds` / `modelOrder` 列 15 个模型 ID；
   - `config.modelConfigRules.providerModelRules[]` 每个模型一条（`contextWindow`、`inputFormat.supportsImage`，以及**必须声明**的 `optionSpecs.reasoningLevel.values`——缺了会话恢复时会 `sessionModelUnavailable` 被回退成默认供应商）。

   不想手动改的话，把 [PROMPT_FOR_ZCODE.md](PROMPT_FOR_ZCODE.md) 发给 ZCode 让它自己装。
5. 重启 ZCode，模型列表里选 WorkBuddy 分组即可。

## 两个硬坎的细节（能跑通的关键）

**坑一：令牌信封（5.6.2 起）**

`workbuddy-desktop.info` 里的 accessToken 变成 `{"$wbEncrypted":1,"envelope":"<base64>"}`，解开是 `{suite:1, keyId, nonce, authTag, ciphertext}`。加密方案逆向自 CLI 包（`app.asar.unpacked/cli/dist/`）：

- 密钥 = `sha256(atRestSecretKey)`；`keyId = sha256(密钥) 十六进制前 16 位`（与信封头核对，自校验）；
- AES-256-GCM，AAD 按 WB-AAD v1 规范拼：`"WB-AAD\0" + 版本号 + 长度前缀的 framing 名（字段级 WBEV1 / 整文件 WBEF1）+ "sym-v1" + suite + keyId + framing 字节 + 空 sequence + 空 final`；
- `atRestSecretKey` 不在磁盘任何文件（keyblob / workbuddy.db / leveldb 全查过），由桌面端运行时派生，所以只能从进程内存里拿——这就是 `scan_mem.py` 存在的原因。密钥跨重启稳定，令牌刷新不影响它。

**坑二：11128 通道校验**

带完整系统提示词的请求会被网关以 `400 {"code":11128,"msg":"Illegal API invocation from an unapproved channel"}` 拦截，而裸消息能过。二分定位后的结论：

- 确定性内容扫描，与工具定义、消息历史、请求长度、`max_completion_tokens` 等字段无关；
- 最小触发组合小到一句 `Main branch (you will usually use this for PRs)`，把其中任一单词换成别的就通过；
- 同样的内容挂 **user 角色**就能通过。

所以代理把 system/developer 消息一律改挂 user 角色下发（内容零改写，只换角色标签）。副作用是指令从"系统角色"变成"用户角色"，实测指令遵循不受影响。

另外三个小坑也修在了代理里：上游 SSE 的 heartbeat 注释行与 data 行同块（逐行挑 `data:`）；每个 delta 块都带空占位字段导致思考被切碎（`sanitizeDelta` 只留有内容的字段）；客户端断开要用 `res.on("close")` 判断而不是 `req`。

## 模型清单

清单 = 服务端下发配置里 `agents` 数组中 `name:"cli"` 代理的 `models` 白名单（去掉 `fast-model`/`balanced-model`/`deep-model` 三个路由预设），参数取同文件 `models` 数组。共 15 个：

| 模型 ID | 显示名 | 上下文 | 输出 | 思考档位 | 可关思考 | 计费倍率 |
|---------|--------|--------|------|----------|:--------:|---------|
| `deepseek-v4.1-flash` | Deepseek-V4.1-Flash | 1,000,000 | 128,000 | `high`（固定） | 否 | x0.11 |
| `deepseek-v4-pro` | Deepseek-V4-Pro | 1,000,000 | 128,000 | `high` / `xhigh` | 是 | x0.51 |
| `glm-5.3` | GLM-5.3 | 1,000,000 | 64,000 | `low` / `high` / `max` | 否 | x0.79 |
| `glm-5.3-flash` | GLM-5.3-Flash | 1,000,000 | 131,072 | `low` / `high` / `max` | 否 | x0.06 |
| `glm-5.2` | GLM-5.2 | 1,000,000 | 64,000 | `high` / `xhigh` | 是 | x0.79 |
| `glm-5.1` | GLM-5.1 | 200,000 | 48,000 | `medium`（固定） | 否 | x0.79 |
| `glm-5v-turbo` | GLM-5v-Turbo | 200,000 | 64,000 | `medium`（固定） | 否 | x0.71 |
| `kimi-k3-1` | Kimi-K3 | 1,000,000 | 32,000 | `low` / `high` / `xhigh` | 是 | x1.62 |
| `kimi-k2.8-preview` | Kimi-K2.8-Preview | 1,000,000 | 64,000 | `low` / `high` / `max` | 是 | x0.77 |
| `kimi-k2.7` | Kimi-K2.7-Code | 256,000 | 32,000 | `medium`（固定） | 否 | x0.57 |
| `kimi-k2.6` | Kimi-K2.6 | 256,000 | 32,000 | `medium`（固定） | 否 | x0.52 |
| `minimax-m3` | MiniMax-M3 | 512,000 | 64,000 | `medium`（固定） | 否 | x0.25 |
| `hy3-b` | Hy3 | 192,000 | 64,000 | `low` / `high` | 否 | x0.00 |
| `hy3-x` | Hy3 | 192,000 | 64,000 | `low` / `high` | 否 | x0.05 |
| `hy4-preview-f` | Hy4 preview | 1,000,000 | 64,000 | `high`（固定） | 否 | x0.00 |

网关可能随时增删模型。升级 WorkBuddy 后重跑对齐脚本（见下）。

## 维护

升级 WorkBuddy 后三样东西可能变：

```bat
rem ① 客户端版本号（代理自动探测，一般不用管）
type "%USERPROFILE%\.workbuddy\last-launch.json"

rem ② CLI 模型白名单 + 参数（清单以 agents.name=="cli" 的 models 为准）
node -e "const d=require(process.env.USERPROFILE+'/.workbuddy/cache/acc-product-config-v3.json');const cli=d.agents.find(a=>a.name==='cli');for(const id of cli.models){const m=d.models.find(x=>x.id===id);if(!m)continue;const r=m.reasoning||{};console.log(m.id,'|',m.maxInputTokens,'|',m.maxOutputTokens,'|',m.temperature,'|',JSON.stringify(r.supportedEfforts||[r.effort]),'|','canDisable='+(r.canDisableThinking===true),'|',m.credits)}"

rem ③ 上游地址（服务端下发，直接读同一份配置）
node -e "const d=require(process.env.USERPROFILE+'/.workbuddy/cache/acc-product-config-v3.json');console.log(d.endpoint);console.log(JSON.stringify(d.officialEndpoints))"
```

模型表变了就同步改 `workbuddy-proxy.js` 的 `MODELS` 表和 ZCode 的 `provider_config.json`。代理报「令牌信封解密失败: keyId …」说明官方轮换了信封密钥，重跑一次 `scan_mem.py` 即可。

## 目录

```
workbuddy-proxy.js  本地代理（node，无第三方依赖）：协议翻译 + 信封解密 + SSE 清洗
scan_mem.py         从桌面端进程内存提取信封密钥（keyId 自校验）
wb_decrypt.py       解密链自检工具（脱敏输出）
start-proxy.bat     启动
stop-proxy.bat      停止
PROMPT_FOR_ZCODE.md 发给 ZCode 让它自己完成注册的提示词
```

## 免责声明

本项目通过逆向 WorkBuddy 客户端的本地存储与 CLI 代码，实现了对自己账号令牌的解密与官方网关的调用，仅供个人学习研究。使用本项目导致的账号限制、封禁由使用者自行承担；请勿用于商业用途或转售额度。代理只监听 `127.0.0.1`，日志不记录对话内容，`wb-key-payload.json` 等同凭证的一部分请妥善保管。WorkBuddy 是腾讯的产品，ZCode 是 Z.ai 的产品，本项目与二者均无关联。
