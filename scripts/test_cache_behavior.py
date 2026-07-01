"""Test prompt caching with >1024 token increments per turn.

Each user message is large enough to exceed the 1024 minimum cache checkpoint threshold
on its own, so we can see how cache write behaves when deltas are substantial.
"""

import boto3
import time

client = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "global.anthropic.claude-sonnet-4-6"

# System prompt ~2500 tokens
SYSTEM_PROMPT = """You are a cloud architecture expert. Provide detailed technical responses.
""" + "\n".join(f"Knowledge entry {i}: AWS best practice reference material for comprehensive cloud architecture design covering VPC networking, security groups, IAM policies, encryption standards, monitoring strategies, cost optimization techniques, and disaster recovery planning. This block ensures sufficient token count for caching behavior analysis." for i in range(30))

system = [
    {"text": SYSTEM_PROMPT},
    {"cachePoint": {"type": "default"}}
]

raw_messages = []

# Each question is padded to be ~1200+ tokens so the delta per turn > 1024
PADDING = " ".join(f"Consider aspect-{i} including scalability, reliability, security implications, cost factors, operational overhead, and integration patterns with existing services." for i in range(30))

QUESTIONS = [
    f"Design a complete VPC architecture for a financial services company. {PADDING}",
    f"Now add a Kubernetes cluster to this architecture with proper networking. {PADDING}",
    f"Add a data pipeline with Kinesis, S3, and Redshift to the architecture. {PADDING}",
    f"Implement a disaster recovery strategy across two regions. {PADDING}",
    f"Add API Gateway with Lambda and DynamoDB for a microservices layer. {PADDING}",
    f"Finally, design the monitoring and alerting stack with CloudWatch and Grafana. {PADDING}",
]


def send_message(user_text: str, turn_num: int):
    """Send a message with cachePoint only on last user message."""
    raw_messages.append({"role": "user", "content": [{"text": user_text}]})

    api_messages = []
    for i, msg in enumerate(raw_messages):
        if i == len(raw_messages) - 1 and msg["role"] == "user":
            api_messages.append({
                "role": "user",
                "content": msg["content"] + [{"cachePoint": {"type": "default"}}]
            })
        else:
            api_messages.append(msg)

    response = client.converse(
        modelId=MODEL_ID,
        messages=api_messages,
        system=system,
        inferenceConfig={"maxTokens": 300}
    )

    usage = response["usage"]
    input_tokens = usage.get("inputTokens", 0)
    output_tokens = usage.get("outputTokens", 0)
    cache_read = usage.get("cacheReadInputTokens", 0)
    cache_write = usage.get("cacheWriteInputTokens", 0)
    total_input = input_tokens + cache_read + cache_write

    hit_pct = cache_read / total_input * 100 if total_input else 0
    print(f"Turn {turn_num}: READ={cache_read:>6,} | WRITE={cache_write:>6,} | UNCACHED={input_tokens:>6,} | TOTAL={total_input:>6,} | HIT={hit_pct:.0f}%")

    assistant_text = response["output"]["message"]["content"][0]["text"]
    raw_messages.append({"role": "assistant", "content": [{"text": assistant_text}]})

    return {"turn": turn_num, "cache_read": cache_read, "cache_write": cache_write,
            "input_tokens": input_tokens, "total_input": total_input, "output_tokens": output_tokens}


def main():
    print(f"Model: {MODEL_ID}")
    print(f"System prompt: ~{len(SYSTEM_PROMPT)//4} tokens (est)")
    print(f"Each user msg: ~{len(QUESTIONS[0])//4} tokens (est) — well over 1024")
    print(f"Max output: 300 tokens/turn (so assistant reply + next user msg > 1024 delta)")
    print()

    results = []
    for i, q in enumerate(QUESTIONS, 1):
        r = send_message(q, i)
        results.append(r)
        time.sleep(2)

    print(f"\n{'='*80}")
    print(f"{'Turn':<6}{'READ':<12}{'WRITE':<12}{'UNCACHED':<12}{'TOTAL':<10}{'HIT%':<7}{'Delta (W)':<12}")
    print(f"{'-'*80}")
    prev_total = 0
    for r in results:
        hit = r['cache_read'] / r['total_input'] * 100 if r['total_input'] else 0
        delta_note = f"(+{r['total_input']-prev_total})" if prev_total else "(initial)"
        print(f"{r['turn']:<6}{r['cache_read']:<12,}{r['cache_write']:<12,}{r['input_tokens']:<12,}{r['total_input']:<10,}{hit:<7.0f}{delta_note}")
        prev_total = r['total_input']

    print(f"\nWRITE per turn: {[r['cache_write'] for r in results]}")
    print(f"READ per turn:  {[r['cache_read'] for r in results]}")
    print(f"\nQ: Does WRITE = full prefix or just delta?")
    print(f"   If WRITE ≈ TOTAL → full prefix rewrite")
    print(f"   If WRITE ≈ delta (~{results[1]['total_input']-results[0]['total_input']} per turn) → only new content written")


if __name__ == "__main__":
    main()
