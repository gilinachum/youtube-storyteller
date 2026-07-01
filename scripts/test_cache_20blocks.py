"""Test: does caching degrade after 20+ content blocks?"""

import boto3
import time

client = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "global.anthropic.claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a helpful assistant. Be concise.
""" + "\n".join(f"Reference {i}: Additional context material for cloud architecture patterns and best practices for enterprise systems." for i in range(40))

system = [{"text": SYSTEM_PROMPT}, {"cachePoint": {"type": "default"}}]
raw_messages = []


def send_message(user_text: str, turn_num: int):
    raw_messages.append({"role": "user", "content": [{"text": user_text}]})

    api_messages = []
    for i, msg in enumerate(raw_messages):
        if i == len(raw_messages) - 1 and msg["role"] == "user":
            api_messages.append({"role": "user", "content": msg["content"] + [{"cachePoint": {"type": "default"}}]})
        else:
            api_messages.append(msg)

    response = client.converse(modelId=MODEL_ID, messages=api_messages, system=system, inferenceConfig={"maxTokens": 100})

    usage = response["usage"]
    cache_read = usage.get("cacheReadInputTokens", 0)
    cache_write = usage.get("cacheWriteInputTokens", 0)
    input_tokens = usage.get("inputTokens", 0)
    total = cache_read + cache_write + input_tokens
    blocks = len(raw_messages)  # total content blocks in messages

    hit = cache_read / total * 100 if total else 0
    print(f"Turn {turn_num:>2} | blocks={blocks:>3} | READ={cache_read:>6,} | WRITE={cache_write:>6,} | UNCACHED={input_tokens:>4} | TOTAL={total:>6,} | HIT={hit:.0f}%")

    assistant_text = response["output"]["message"]["content"][0]["text"]
    raw_messages.append({"role": "assistant", "content": [{"text": assistant_text}]})
    return {"turn": turn_num, "blocks": blocks, "cache_read": cache_read, "cache_write": cache_write}


def main():
    print(f"Model: {MODEL_ID}")
    print(f"Testing 15 turns (30 messages = 30+ content blocks) to check 20-block limit\n")

    for i in range(1, 16):
        send_message(f"Question {i}: Tell me about AWS service number {i} and its use cases.", i)
        time.sleep(1.5)

    print(f"\nTotal messages in conversation: {len(raw_messages)}")
    print(f"Total content blocks: {len(raw_messages)} (1 per message)")
    print("If caching degrades after 20 blocks, we'd see WRITE spike or READ drop to 0.")


if __name__ == "__main__":
    main()
