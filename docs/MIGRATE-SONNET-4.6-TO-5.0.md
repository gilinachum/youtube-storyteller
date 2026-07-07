# Migrating from Claude Sonnet 4.6 → Sonnet 5.0 on Amazon Bedrock

> Based on hands-on migration experience (July 2026). Covers gotchas, config changes, and validation steps.

## Model IDs

| Scope | Sonnet 4.6 | Sonnet 5.0 |
|-------|-----------|-----------|
| In-region | `anthropic.claude-sonnet-4-6` | `anthropic.claude-sonnet-5` |
| US geo | `us.anthropic.claude-sonnet-4-6` | `us.anthropic.claude-sonnet-5` |
| Global (10% cheaper) | `global.anthropic.claude-sonnet-4-6` | `global.anthropic.claude-sonnet-5` |

**Recommended: use `global.anthropic.claude-sonnet-5`** — same quality, ~10% cheaper per token.

## Endpoints

- **bedrock-runtime** (Converse/Invoke API): Works as before, drop-in model ID swap
- **bedrock-mantle** (Messages API): NEW for Sonnet 5 — `https://bedrock-mantle.{region}.api.aws/anthropic/v1/messages` with `AnthropicBedrockMantle` client
- Both endpoints supported; pick whichever your SDK uses

## ⚠️ Critical: Reasoning is ALWAYS ON

Sonnet 5.0 has **adaptive thinking enabled by default and cannot be disabled**. This means:

- Every response includes a `reasoningContent` block (even for trivial tasks)
- Extra tokens consumed on every call (~2-3K input-equivalent tokens overhead)
- Effort level IS configurable (low/medium/high) — use lower effort for simple routing tasks
- If your code parses response content, handle the `reasoningContent` block (it appears before `text` or `toolUse` blocks)

## Key Differences

| | 4.6 | 5.0 |
|---|---|---|
| Max output tokens | 64K | **128K** |
| Knowledge cutoff | Aug 2025 | **Jan 2026** |
| Prompt cache min tokens | 1,024 | **4,096** ⚠️ |
| Cache checkpoints | 4 | 4 |
| Cache TTL | 5min / 1hr | 5min / 1hr |
| In-region availability | eu-west-2 only | **us-east-1 only** |
| Geo inference | US + EU + AU + JP | **US only** (no EU/AU/JP geo yet) |
| Service tiers | Standard + Reserved | **Standard only** |

## Gotchas

1. **Prompt cache minimum is 4x higher** — your system prompt + tools must total ≥4,096 tokens for caching to activate. If you're below that, caching won't fire and costs go up.

2. **No EU/AU/JP geo routing yet** — if you need data residency outside US, stay on 4.6 or use `global.` (routes worldwide).

3. **No Reserved capacity tier** — only Standard (on-demand) for now.

4. **Output is chattier** — Sonnet 5 tends to produce ~60% more output tokens per response. If you have tight `max_tokens`, you're fine. If not, expect higher output costs.

5. **Token speed is actually faster** — 24 ms/output-token vs 34 ms/tok on 4.6. Wall clock may be similar or slightly longer due to more output.

6. **`anthropic_version` stays the same** — still `bedrock-2023-05-31` for Invoke API.

7. **Tool calling works identically** — Converse API tool schemas are unchanged. The `reasoningContent` block appears in the response but tool routing is unaffected.

## Latency Benchmark (Real-World, July 2026)

Tested with ~8.5K token system prompt + tools, Hebrew content generation:

| Model | Avg Latency | ms/output-token | Avg Output Tokens |
|-------|-------------|-----------------|-------------------|
| Sonnet 4.6 (us.) | 11.9s | 34 | 350 |
| Sonnet 5.0 (global.) | 13.7s | 24 ⚡ | 569 |

Sonnet 5 is faster per-token but generates more output per request.

## Migration Checklist

```
[ ] Swap model ID in config/env vars
[ ] Verify model access:
    aws bedrock get-foundation-model-availability --model-id anthropic.claude-sonnet-5 --region us-east-1
[ ] Check system prompt token count ≥ 4,096 (for cache to work)
[ ] Handle reasoningContent in response parsing (if doing manual parsing)
[ ] Test multi-turn conversations (cache behavior changes)
[ ] Update max_tokens if you want to use the new 128K output limit
[ ] If using EU/AU/JP geo inference → stay on 4.6 or switch to global.*
[ ] Redeploy and verify via logs that new model ID appears
[ ] Run a quality comparison with your actual prompts before going to prod
```

## Quick Validation

```python
import boto3, json

client = boto3.client('bedrock-runtime', region_name='us-east-1')
response = client.converse(
    modelId='global.anthropic.claude-sonnet-5',
    messages=[{"role": "user", "content": [{"text": "Say hello"}]}],
    inferenceConfig={"maxTokens": 256}
)

# Response content will include reasoningContent + text blocks
for block in response['output']['message']['content']:
    if 'text' in block:
        print(f"Text: {block['text']}")
    elif 'reasoningContent' in block:
        print(f"Reasoning: (present, {len(str(block))} chars)")

print(f"Tokens: in={response['usage']['inputTokens']} out={response['usage']['outputTokens']}")
```

## Pricing Reference

Check current pricing at: https://aws.amazon.com/bedrock/pricing/

Global inference is ~10% cheaper than in-region/geo for both input and output tokens.

## Regional Availability (as of July 2026)

- **In-region:** us-east-1 only
- **US geo:** us-east-1, us-east-2, us-west-1, us-west-2, ca-central-1, ca-west-1
- **Global:** All regions worldwide
