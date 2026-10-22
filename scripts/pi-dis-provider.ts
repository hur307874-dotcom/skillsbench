// pi-coding-agent 扩展：注册 r.dis.115.zone 中转站为自定义 provider
// 用法：DIS_API_KEY=<key> NO_PROXY=r.dis.115.zone pi -e scripts/pi-dis-provider.ts \
//        --provider dis --model deepseek-v4.1-flash -p "..."
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const MODELS = [
  "deepseek-v4.1-flash",
  "deepseek-v4-pro",
  "glm-5.3",
  "kimi-k2.6",
  "grok-4.6",
  "mimo-v2.6-flash",
];

export default function (pi: ExtensionAPI) {
  pi.registerProvider("dis", {
    name: "siliconflow relay",
    baseUrl: "https://api.siliconflow.cn/v1",
    apiKey: "DIS_API_KEY",
    api: "openai-completions",
    models: MODELS.map((id) => ({
      id,
      name: id,
      reasoning: false,
      input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128000,
      maxTokens: 8192,
    })),
  });
}
