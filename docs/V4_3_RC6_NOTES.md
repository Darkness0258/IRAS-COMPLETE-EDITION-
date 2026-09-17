# IRAS v4.3.0 RC6 — Device-Local AI Failover

RC6 addresses the real-device failure where the specialized engineering DAG was structurally correct but the first inspection worker still failed after every configured cloud AI provider remained unavailable through the provider-recovery window.

## What changed

- **Paired-device Ollama fallback.** Specialized orchestration workers now use the normal cloud provider pool first and, when it is unavailable, can fall back to an OpenAI-compatible Ollama model running on the paired Windows PC.
- **Outbound-only transport preserved.** Render never opens or connects to a laptop port. Model requests are delivered through the existing authenticated device command queue; the Windows executor alone contacts the loopback Ollama endpoint.
- **Loopback-only enforcement.** `IRAS_DEVICE_OLLAMA_BASE_URL` must resolve to `localhost`, `127.0.0.1`, or `::1` over plain HTTP. This feature cannot be repurposed as a generic network proxy.
- **Tool safety preserved.** A local model can propose normal IRAS tool calls, but tool execution still occurs through the cloud ToolRegistry, verified project root, Remote session permissions, laptop-local policy, and emergency stop.
- **Bounded payloads.** Messages, tool schemas, generation length, timeout, and tool-call payloads are bounded before entering the bridge queue.
- **Automatic local model discovery.** The Windows executor queries local Ollama tags and prefers `qwen2.5-coder:7b`, then `qwen2.5-coder:1.5b`, then compatible alternatives. `IRAS_DEVICE_OLLAMA_MODEL` can pin a model.
- **Doctor visibility.** `iras --doctor` now reports whether the device-local AI fallback is available and lists a few detected local models.

## Configuration

Cloud orchestration fallback is enabled by default:

```env
IRAS_DEVICE_OLLAMA_FALLBACK=true
IRAS_DEVICE_OLLAMA_MODEL=
IRAS_DEVICE_OLLAMA_TIMEOUT=120
```

On the Windows device, Ollama defaults to:

```env
IRAS_DEVICE_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
IRAS_DEVICE_OLLAMA_MODELS=qwen2.5-coder:7b,qwen2.5-coder:1.5b,llama3.1:8b,llama3
```

If no local Ollama model is available, IRAS falls back to the existing provider-aware wait/retry behavior and reports the failure honestly rather than bypassing the safety model.

Remote protocol remains `1`.
