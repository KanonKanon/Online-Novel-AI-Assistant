import json


def load_settings():
    """
    加载本地设置文件
    返回本地设置字典
    """
    try:
        # 确保正确指定 local_settings.json 文件路径
        settings_path = 'local_settings.json'
        with open(settings_path, 'r', encoding='utf-8') as file:
            settings = json.load(file)
            
            # 打印整个 settings 以检查其内容
            print(f"### 调试信息：读取的 settings 内容: {settings}")
            
            return settings

    except FileNotFoundError:
        print("### 错误信息：local_settings.json not found, using default settings.")
        return {}
    except json.JSONDecodeError as e:
        print(f"### 错误信息：Error decoding local_settings.json, using default settings. Error details: {e}")
        return {}