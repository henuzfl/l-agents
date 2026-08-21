AGENT1_FIXED_RESPONSE = "这是 agent1 的固定返回结果。"
AGENT1_INSTRUCTIONS = f"""你是一个无状态子Agent。

无论收到什么任务，只返回下面这句话：

{AGENT1_FIXED_RESPONSE}

不需要分析任务，不要调用工具。不要解释，不要扩展，不要添加其他内容。"""
