# Deep Dive: Prompt Caching for AI Agents on Amazon Bedrock

## TL;DR

Prompt caching lets you avoid re-processing the same tokens on every API call. For agentic workloads — where a single user message triggers 3-5 Bedrock invocations (tool calls, research, iteration) — this cuts input token costs by 60-90% and reduces latency significantly.

---

## The Problem: Agents Are Expensive

A typical agentic turn looks like this:

```
User sends "Plan a video about ElastiCache"
  → Call 1: [system_prompt + tools + user_msg]           = 15,000 tokens
  → Call 2: [all above + assistant + tool_result]         = 17,000 tokens  
  → Call 3: [all above + assistant + another_tool_result] = 19,000 tokens
  → Call 4: [all above + final response]                  = 20,000 tokens
```

Without caching, you pay for **71,000 input tokens** for a single user message. The system prompt (~5K), tool definitions (~8K), and earlier conversation are resent identically on every call.

With caching: you pay full price once, then 90% off for the repeated prefix on calls 2, 3, 4.

---

## Key Terms

### Cache Checkpoint (cachePoint)
A marker you place in your request that tells Bedrock: "everything before this point should be cached." It's a content block you insert into `system`, `messages`, or `tools`.

```json
{"cachePoint": {"type": "default"}}
```

### Prompt Prefix
The contiguous token sequence from the start of your request up to the cache checkpoint. This is what gets stored in cache. It must be **identical** between requests to get a cache hit.

### Cache Write
First time Bedrock sees a prefix → stores it in cache. You pay a **25% premium** over standard input token price.

### Cache Read (Cache Hit)
Subsequent request with the same prefix → reads from cache. You pay **90% less** than standard input token price.

### Uncached Tokens (inputTokens)
Any tokens after the last cache checkpoint. Charged at standard input rate.

### TTL (Time To Live)
How long the cache lives. Default: **5 minutes** (resets on each hit). Some models support **1 hour** TTL.

### Minimum Token Threshold
The prefix must exceed a minimum size to be cached:
- **Claude Sonnet 4.6, Opus 4, 3.7 Sonnet:** 1,024 tokens
- **Claude Opus 4.5, Haiku 4.5, Sonnet 4.5:** 4,096 tokens

If your prefix is below this, the request succeeds but nothing is cached.

### Maximum Cache Checkpoints
Up to **4 cachePoints per request** (for Claude models). You can place them in `system`, `messages`, and `tools`.

### Simplified Cache Management
Bedrock automatically looks back **~20 content blocks** from your cache checkpoint to find the longest matching prefix from any existing cache entry. You don't need to predict exact boundaries — just place one checkpoint at the end of your content.

---

## How It Works in Strands SDK

### Option 1: Automatic Mode (Recommended)

```python
from strands import Agent
from strands.models import BedrockModel, CacheConfig

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    cache_config=CacheConfig(strategy="auto"),
    cache_tools="default",
)

agent = Agent(model=model, system_prompt="...", tools=[...])
```

**What `cache_config=CacheConfig(strategy="auto")` does internally:**

On every Bedrock API call, Strands:
1. Strips ALL existing `cachePoint` blocks from messages
2. Injects ONE `cachePoint` at the end of the **last user message** (including tool_result messages)
3. Sends the request

This means the cache point **moves forward** with each invocation, creating a rolling chain of cache entries.

**What `cache_tools="default"` does:**

Appends a `cachePoint` after all tool specifications in `toolConfig`. Since tools rarely change during a session, this caches your entire tool schema.

### Option 2: Manual System Prompt Caching

```python
agent = Agent(
    model=model,
    system_prompt=[
        {"text": "Your long system prompt here..."},
        {"cachePoint": {"type": "default"}}
    ]
)
```

Place the checkpoint explicitly after your system prompt content blocks.

### Option 3: Combined (What We Use in Production)

```python
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-6",
    cache_config=CacheConfig(strategy="auto"),  # auto-manages message caching
    cache_tools="default",                       # caches tool definitions
)

# System prompt cachePoint is added by Strands when using system_prompt as list
agent = Agent(
    model=model,
    system_prompt=[
        {"text": system_prompt_text},
        {"cachePoint": {"type": "default"}}
    ],
    tools=[...]
)
```

This gives you 3 cache checkpoints:
1. System prompt (fixed, always cached)
2. Tools (fixed, always cached)  
3. Last user message (moves forward, rolling cache)

---

## Step-by-Step: What Happens Across Turns

### Turn 1, Call 1 (First ever invocation)

```
Request: [system + cachePoint₁] [tools + cachePoint₂] [user_msg₁ + cachePoint₃]

Bedrock checks: any existing cache? → No.
Result:
  cacheWriteInputTokens: 2,490  (entire prefix written to cache)
  cacheReadInputTokens:  0
  inputTokens:           3      (tokens after last cachePoint)
```

**Cost:** 2,490 × $3.75/MTok = $0.0093 (25% more than standard)

### Turn 1, Call 2 (After tool call, same user turn)

```
Request: [system + CP₁] [tools + CP₂] [user_msg₁ | assistant_tool_use | tool_result + CP₃]

Bedrock checks: prefix match? → Yes! First 2,490 tokens match.
Result:
  cacheReadInputTokens:  2,490  (previous prefix read from cache)
  cacheWriteInputTokens: 1,129  (new delta: assistant + tool_result)
  inputTokens:           3
```

**Cost:** 2,490 × $0.30/MTok + 1,129 × $3.75/MTok = $0.0007 + $0.0042 = $0.0049

**Without caching this would cost:** 3,622 × $3.00/MTok = $0.0109

### Turn 2 (User sends second message)

```
Request: [system + CP₁] [tools + CP₂] [user_msg₁ | asst₁ | user_msg₂ + CP₃]

Bedrock checks: longest prefix match? → 3,619 tokens match (from Turn 1 Call 2's cache)
Result:
  cacheReadInputTokens:  3,619
  cacheWriteInputTokens: 1,136  (delta: new user message content)
  inputTokens:           3
```

### Turn 10 (Deep into conversation)

```
  cacheReadInputTokens:  ~7,000  (growing — all previous conversation)
  cacheWriteInputTokens: ~1,130  (constant — just the new delta)
  inputTokens:           3
  Cache hit rate:        ~86%
```

---

## The Rolling Cache Chain (Visual)

```
Turn 1:  [████████████████████ WRITE 2490 ████████████████████] [3]
                                                                 ↑ cachePoint

Turn 2:  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ READ 2490 ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓][█ W 1129 █] [3]
                                                                              ↑ cachePoint

Turn 3:  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ READ 3619 ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓][█ W 1136 █] [3]
                                                                                           ↑ CP

Turn N:  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ READ (growing) ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓][█ W ~1130 █] [3]
                                                                                                         ↑ CP

Legend: ▓ = cache READ (90% off)  █ = cache WRITE (+25%)  [3] = uncached (standard price)
```

**Key insight:** READ grows linearly (cheap). WRITE stays constant (just the new delta). The cache point moves forward but Bedrock uses "simplified cache management" to find the previous entry just 2 blocks back.

---

## Real Benchmark Data

Tested with `global.anthropic.claude-sonnet-4-6`, ~2,500 token system prompt, >1,024 token user messages:

| Turn | Cache Read | Cache Write | Uncached | Total Input | Hit % |
|------|-----------|-------------|----------|-------------|-------|
| 1    | 0         | 2,490       | 3        | 2,493       | 0%    |
| 2    | 2,490     | 1,129       | 3        | 3,622       | 69%   |
| 3    | 3,619     | 1,136       | 3        | 4,758       | 76%   |
| 4    | 4,755     | 1,126       | 3        | 5,884       | 81%   |
| 5    | 5,881     | 1,132       | 3        | 7,016       | 84%   |
| 6    | 7,013     | 1,133       | 3        | 8,149       | 86%   |

**Write pattern:** `[2490, 1129, 1136, 1126, 1132, 1133]` — constant after turn 1.
**Read pattern:** `[0, 2490, 3619, 4755, 5881, 7013]` — linear growth.

---

## The "20 Content Blocks" Limit — Does It Matter?

The docs warn that simplified cache management only looks back ~20 content blocks. We tested with **30 content blocks (15 turns)** — no degradation:

```
Turn 11 | blocks=21 | READ=1,909 | WRITE=124 | HIT=94%
Turn 12 | blocks=23 | READ=2,033 | WRITE=124 | HIT=94%
Turn 15 | blocks=29 | READ=2,405 | WRITE=124 | HIT=95%
```

**Why it doesn't matter:** With auto strategy, each turn writes a new cache entry. The next turn only needs to look back **2 blocks** (1 assistant message + 1 new user message) to find the match. You never approach the 20-block limit.

**When it WOULD matter:** If you only cache the system prompt (block 0) and never place another cachePoint in messages, then after 20+ message blocks, the system prompt cache won't be found from a messages-level cachePoint. Solution: use the auto strategy.

---

## Cost Analysis

### Bedrock Pricing (Claude Sonnet 4.6)

| Token Type | Price/MTok | vs Standard |
|-----------|-----------|-------------|
| Standard input | $3.00 | baseline |
| Cache write | $3.75 | +25% |
| Cache read | $0.30 | -90% |
| Output | $15.00 | (unchanged) |

### Per-Turn Cost Comparison (15K system+tools prefix, typical agent)

**Without caching:**
```
Turn 1: 15,000 × $3.00/MTok = $0.045
Turn 2: 16,200 × $3.00/MTok = $0.049
Turn 5: 20,000 × $3.00/MTok = $0.060
5-turn session total: ~$0.26
```

**With caching:**
```
Turn 1: 15,000 × $3.75/MTok = $0.056 (write — 25% more expensive!)
Turn 2: 15,000 × $0.30 + 1,200 × $3.75 = $0.0045 + $0.0045 = $0.009
Turn 5: 18,800 × $0.30 + 1,200 × $3.75 = $0.0056 + $0.0045 = $0.010
5-turn session total: ~$0.095
```

**Savings: ~63% over a 5-turn session.** Gets better with more turns and tool calls.

### Breakeven Point

Turn 1 extra cost: 15K × ($3.75 - $3.00)/MTok = **+$0.011**
Turn 2 savings: 15K × ($3.00 - $0.30)/MTok = **-$0.040**

**Breakeven: Turn 2.** For agents with tool calls, breakeven happens within the first user turn (the second Bedrock invocation already reads from cache).

---

## Gotchas & Best Practices

### 1. Minimum Token Threshold
If your total prefix (system + messages up to cachePoint) is under 1,024 tokens, nothing gets cached. The request succeeds silently — no error, no cache. Make sure your system prompt + tools exceed the minimum.

### 2. Cross-Region Inference
Caching works with cross-region profiles (`us.anthropic.claude-sonnet-4-6`). However, at high demand, requests may route to different regions causing cache misses (writes). The docs note: "At times of high demand, these optimizations may lead to increased cache writes."

### 3. TTL Refresh
The 5-min TTL resets on every cache hit. As long as your user sends a message within 5 minutes, the cache stays warm. For longer gaps, consider 1-hour TTL (available on Opus 4.5, Haiku 4.5, Sonnet 4.5).

### 4. Tool Changes Invalidate Tool Cache
If you dynamically add/remove tools between calls, the tools cache will miss. Keep tool definitions stable within a session.

### 5. Max 4 cachePoints Per Request
With auto strategy + system cachePoint + tools cachePoint = 3 checkpoints. You have room for 1 more if needed.

### 6. Streaming Works Too
Caching works with both `converse()` and `converseStream()`. Same behavior, same metrics.

### 7. Cache Hits Don't Count Against Rate Limits
From the docs: "cache hits are not deducted against your rate limit." Free throughput for cached tokens.

---

## Implementation Checklist for Agent Builders

- [ ] Add `cache_config=CacheConfig(strategy="auto")` to your BedrockModel
- [ ] Add `cache_tools="default"` to cache tool definitions
- [ ] Add `{"cachePoint": {"type": "default"}}` to system prompt content blocks
- [ ] Verify system prompt + tools > 1,024 tokens (check with first request metrics)
- [ ] Monitor `cacheReadInputTokens` and `cacheWriteInputTokens` in responses
- [ ] For long-idle sessions (>5 min between messages), consider 1h TTL if model supports it
- [ ] Keep tool definitions stable within a session

---

## References

- [AWS Docs: Prompt caching for faster model inference](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [Strands SDK source: BedrockModel caching](https://github.com/strands-agents/sdk-python/blob/main/src/strands/models/bedrock.py)
- [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
