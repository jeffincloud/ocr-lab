"""Ask the model about one passport with thinking on and off, keeping the reasoning. Runs inside the API pod."""
import base64
import json

import httpx

from app import ocr

img, fmt = ocr._resize(open("/tmp/p22.png", "rb").read())
url = f"{ocr.OPENAI_BASE_URL.rstrip('/')}/v1/chat/completions"
res = {}
for think in (True, False):
    body = {"model": ocr.OPENAI_MODEL, "max_tokens": 1500, "temperature": 0, "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": think},
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode()}},
                {"type": "text", "text": ocr.PROMPT}]}]}
    r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {ocr.OPENAI_API_KEY}"}, timeout=120).json()
    m = r["choices"][0]["message"]
    res["on" if think else "off"] = dict(reasoning=m.get("reasoning_content") or m.get("reasoning"), content=m.get("content"),
                                         usage=r.get("usage"), finish=r["choices"][0].get("finish_reason"))
print(json.dumps(res))
