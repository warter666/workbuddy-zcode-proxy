# 发给 ZCode 的自装提示词

把下面整段复制给 ZCode，它会自己完成部署与注册。

---

请把 WorkBuddy→ZCode 本地代理部署到本机并注册进 ZCode。按顺序执行，每步验证通过再进下一步：

1. 选一个英文无空格目录作为代理目录（如 `D:\AI_Proxy`），把仓库里的 `workbuddy-proxy.js`、`scan_mem.py`、`wb_decrypt.py`、`start-proxy.bat`、`stop-proxy.bat` 原样复制进去。
2. 检查 `%LOCALAPPDATA%\CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info` 是否存在（WorkBuddy 已登录的凭证文件）。读其中 `auth.accessToken`：如果是明文字符串（`eyJ` 开头），跳过第 3 步；如果是 `{"$wbEncrypted":1,"envelope":...}` 信封，执行第 3 步。
3. 生成信封密钥：base64 解开 `envelope` 字段拿到 JSON，记下 `keyId`。确认 WorkBuddy 桌面端正在运行，用 `Get-CimInstance Win32_Process -Filter "Name='WorkBuddy.exe'"` 找到命令行里没有 `--type=` 的主进程 PID，然后在代理目录跑 `python scan_mem.py <keyId> <PID>`，成功会生成 `wb-key-payload.json`。
4. 跑 `start-proxy.bat` 启动代理，然后验证：`curl http://127.0.0.1:8787/health` 应返回 `"status":"ok"`，`curl http://127.0.0.1:8787/v1/models` 应含 15 个模型。
5. 备份 `%USERPROFILE%\.zcode\v2\provider_config.json` 后合并供应商配置（ZCode 3.14.4 只认这个文件，`config.json` 的 provider 键不生效），三处同写：`config.providerOrder` 加入 `"workbuddy-provider"`；`config.providerConfigRules.providerRules[]` 新增 `{"providerId":"workbuddy-provider","providerName":"WorkBuddy","enabled":true,"config":{"group":"standard-personal","access":{"type":"api-key","apiKey":"workbuddy"},"api":{"type":"openai-chat-completions","baseUrl":"http://127.0.0.1:8787/v1"},"personalModelIds":[...15 个模型 ID...],"modelOrder":[同前]}}`；`config.modelConfigRules.providerModelRules[]` 每个模型一条（`enabled:true`、`properties.contextWindow` 按模型表、`inputFormat.supportsImage:true`、`outputFormat.supportsText:true`、`optionSpecs.reasoningLevel.values:["low","high","max"]`——必须声明，缺了会话恢复会 sessionModelUnavailable）。已有供应商规则全部保留，是合并不是替换。改完用 node 校验 JSON 合法。
6. 提醒用户：完全重启 ZCode（含托盘），模型列表会出现 WorkBuddy 分组，选 `deepseek-v4.1-flash` 发消息验证。告诉用户代理需常驻（双击 `start-proxy.bat`），WorkBuddy 桌面端不必一直开着，但别分享 `wb-key-payload.json`。

模型清单（ID | 上下文 | 输出 | 思考档位 | 倍率）：
deepseek-v4.1-flash | 1000000 | 128000 | high 固定 | x0.11
deepseek-v4-pro | 1000000 | 128000 | high/xhigh | x0.51
glm-5.3 | 1000000 | 64000 | low/high/max | x0.79
glm-5.3-flash | 1000000 | 131072 | low/high/max | x0.06
glm-5.2 | 1000000 | 64000 | high/xhigh | x0.79
glm-5.1 | 200000 | 48000 | medium 固定 | x0.79
glm-5v-turbo | 200000 | 64000 | medium 固定 | x0.71
kimi-k3-1 | 1000000 | 32000 | low/high/xhigh | x1.62
kimi-k2.8-preview | 1000000 | 64000 | low/high/max | x0.77
kimi-k2.7 | 256000 | 32000 | medium 固定 | x0.57
kimi-k2.6 | 256000 | 32000 | medium 固定 | x0.52
minimax-m3 | 512000 | 64000 | medium 固定 | x0.25
hy3-b | 192000 | 64000 | low/high | x0.00
hy3-x | 192000 | 64000 | low/high | x0.05
hy4-preview-f | 1000000 | 64000 | high 固定 | x0.00
