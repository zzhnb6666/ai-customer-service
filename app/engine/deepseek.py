from pathlib import Path
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
)


def _read_dir(directory: str) -> list[str]:
    """读取目录下所有 txt/md 文件"""
    d = Path(directory)
    if not d.exists():
        return []
    parts = []
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in (".txt", ".md"):
            try:
                parts.append(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return parts


def _load_product_knowledge() -> str:
    return "\n\n".join(_read_dir("uploads"))


def _load_human_examples() -> str:
    """加载人工客服对话范例，供 AI 学习说话风格"""
    examples = _read_dir("data/human_examples")
    if not examples:
        return ""
    return "\n\n---\n\n".join(examples)


PRODUCT_KNOWLEDGE = _load_product_knowledge()
HUMAN_EXAMPLES = _load_human_examples()


SYSTEM_PROMPT = f"""你是 Jarvis III 的官方AI客服助手。

## 你的身份
- 你代表 Jarvis III 品牌
- Jarvis III 是一款智能辅助产品
- 网站: https://jarvis003.com/
- 联系邮箱: hi@jarvis.com

## 回复原则
1. 用中文回复，语气专业友好
2. 所有产品相关问题，必须严格基于下面【产品知识库】的内容回答
3. 知识库里有的信息，直接准确回答
4. 知识库里没有的信息，坦诚说明"目前没有相关信息"，建议用户通过联系邮箱咨询
5. 不要编造任何产品信息
6. 回复简洁有条理
7. 学习和模仿人工客服的说话方式、语气、用词习惯

## 【产品知识库】
{PRODUCT_KNOWLEDGE}
"""


def reload_knowledge():
    """热更新知识库（上传新内容后调用）"""
    global PRODUCT_KNOWLEDGE, HUMAN_EXAMPLES, SYSTEM_PROMPT
    PRODUCT_KNOWLEDGE = _load_product_knowledge()
    HUMAN_EXAMPLES = _load_human_examples()

    extra = ""
    if HUMAN_EXAMPLES:
        extra = f"""
## 【人工客服对话范例 - 请学习以下说话风格】
{HUMAN_EXAMPLES}
"""

    SYSTEM_PROMPT = f"""你是 Jarvis III 的官方AI客服助手。

## 你的身份
- 你代表 Jarvis III 品牌
- Jarvis III 是一款智能辅助产品
- 网站: https://jarvis003.com/
- 联系邮箱: hi@jarvis.com

## 回复原则
1. 用中文回复，语气专业友好
2. 所有产品相关问题，必须严格基于下面【产品知识库】的内容回答
3. 知识库里有的信息，直接准确回答
4. 知识库里没有的信息，坦诚说明"目前没有相关信息"，建议用户通过联系邮箱咨询
5. 不要编造任何产品信息
6. 回复简洁有条理
7. 学习和模仿人工客服的说话方式、语气、用词习惯
{extra}
## 【产品知识库】
{PRODUCT_KNOWLEDGE}
"""


# Initialize with human examples if available
reload_knowledge()


async def chat(messages: list[dict], knowledge: str = "") -> str:
    """调用 DeepSeek 进行对话"""
    system_msg = {"role": "system", "content": SYSTEM_PROMPT}

    if knowledge and knowledge not in system_msg["content"]:
        system_msg["content"] += f"\n\n【额外参考】\n{knowledge}"

    response = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[system_msg] + messages,
        temperature=0.7,
        max_tokens=2000,
    )
    return response.choices[0].message.content
