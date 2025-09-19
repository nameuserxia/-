from google import genai
import re
import json
import os

# 初始化客户端（会自动读取环境变量 GEMINI_API_KEY）
client = genai.Client()

PARSER_PROMPT_CHINESE = """
请从用户指令中提取出发地（origin）、目的地（destination）以及任何约束条件（constraints）。
请严格以 JSON 格式返回，键名必须是 "origin", "destination", "constraints"。
"constraints" 应为一个字典，包含所有找到的约束条件。
如果信息缺失，请设置为空字符串或空字典。
用户指令：
\"\"\"{user}\"\"\"
请只返回 JSON 对象，不要包含任何其他解释性文字。
JSON 结构示例：
{{
  "origin": "出发地名称",
  "destination": "目的地名称",
  "constraints": {{
    "avoid": "需要避开的区域或条件",
    "must_pass": "必须经过的地点",
    "stopover": "中途停留点",
    "highlimit": "高度限制"
  }}
}}
"""

def parse_request(user_text: str) -> dict:
    """
    使用最新版 Gemini API 解析中文路径指令。
    如果 API 调用失败，则回退到简单中文正则解析。
    """
    parsed_data = {'origin': '', 'destination': '', 'constraints': {}}
    prompt = PARSER_PROMPT_CHINESE.format(user=user_text)

    try:
        # --- 调用新版 Gemini API ---
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        text = response.text.strip()
        print("DEBUG Gemini raw response:", repr(text))

        # 尝试提取 JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_text = json_match.group(0)
            try:
                parsed_data_from_api = json.loads(json_text)
                parsed_data = {
                    'origin': parsed_data_from_api.get('origin', ''),
                    'destination': parsed_data_from_api.get('destination', ''),
                    'constraints': parsed_data_from_api.get('constraints', {})
                }
                if parsed_data['origin'] or parsed_data['destination']:
                    print("Successfully parsed JSON from Gemini.")
                    return parsed_data
            except json.JSONDecodeError:
                print(f"Gemini 返回的 JSON 无法解析: {json_text}")
            except Exception as e:
                print(f"解析 Gemini JSON 时出错: {e}")

    except Exception as e:
        print(f"Gemini API 调用失败: {e}")

    # --- 回退逻辑（中文正则解析） ---
    print("Falling back to naive Chinese parsing.")
    chinese_origin = ''
    chinese_dest = ''
    chinese_constraints = {}

    # 匹配 "从 [出发地] 到 [目的地] (避开/绕开/不要经过 [约束])"
    match_full = re.search(r'从(.+?)到(.+?)(?:避开|绕开|不要经过)(.+)', user_text)
    if match_full:
        chinese_origin = match_full.group(1).strip()
        chinese_dest = match_full.group(2).strip()
        chinese_constraints['avoid'] = match_full.group(3).strip()
    else:
        match_simple = re.search(r'从(.+?)到(.+)', user_text)
        if match_simple:
            chinese_origin = match_simple.group(1).strip()
            chinese_dest = match_simple.group(2).strip()

    parsed_data = {
        'origin': chinese_origin,
        'destination': chinese_dest,
        'constraints': chinese_constraints
    }

    return parsed_data

