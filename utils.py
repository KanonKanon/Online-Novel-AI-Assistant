import re
import json
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtCore import Qt


def extract_chapters_from_outline(outline_text):
    """
    从大纲文本中提取章节信息
    """
    chapters = []
    
    # 使用正则表达式提取章节信息
    # 匹配新的格式：【第1章： 标题名称】
    pattern = r"【第(\d+)章：\s*(.*?)】\s*【梗概内容：(.*?)】"
    matches = re.findall(pattern, outline_text, re.DOTALL)
    
    # 处理匹配到的章节
    for match in matches:
        chapter_num = int(match[0])
        title = match[1].strip()
        summary = match[2].strip()
        
        chapters.append({
            'chapter_num': chapter_num,
            'title': title,
            'summary': summary
        })
    
    # 如果没有匹配到新的格式，尝试匹配另一种格式：【第1章 标题名称】
    if not chapters:
        pattern = r"【第(\d+)章\s+(.*?)】\s*【梗概内容：(.*?)】"
        matches = re.findall(pattern, outline_text, re.DOTALL)
        
        # 处理匹配到的章节
        for match in matches:
            chapter_num = int(match[0])
            title = match[1].strip()
            summary = match[2].strip()
            
            chapters.append({
                'chapter_num': chapter_num,
                'title': title,
                'summary': summary
            })
    
    # 如果没有匹配到新的格式，尝试匹配第三种格式：【第1章 标题名称】后跟详细内容
    if not chapters:
        # 匹配格式：【第1章 标题名称】后跟详细内容段落
        pattern = r"【第(\d+)章\s+(.*?)】\s*\n\s*(.*?)\s*(?:\n\s*\*\*\*|\n\s*【|$)"
        matches = re.findall(pattern, outline_text, re.DOTALL)
        
        # 处理匹配到的章节
        for match in matches:
            chapter_num = int(match[0])
            title = match[1].strip()
            content = match[2].strip()
            
            chapters.append({
                'chapter_num': chapter_num,
                'title': title,
                'summary': content
            })
    
    # 如果没有匹配到新的格式，尝试匹配第四种格式：【第1章： 标题名称】后跟详细内容（作家1的输出格式）
    if not chapters:
        # 匹配格式：【第1章： 标题名称】后跟详细内容段落直到【本章出现角色】或***部分
        pattern = r"【第(\d+)章：\s+(.*?)】\s*\n\s*(.*?)\s*(?:\n\s*【本章出现角色】|\n\s*\*\*\*)"
        matches = re.findall(pattern, outline_text, re.DOTALL)
        
        # 处理匹配到的章节
        for match in matches:
            chapter_num = int(match[0])
            title = match[1].strip()
            content = match[2].strip()
            
            chapters.append({
                'chapter_num': chapter_num,
                'title': title,
                'summary': content
            })
    
    # 如果没有匹配到新的格式，尝试匹配第五种格式：【第1章： 标题名称】后跟详细内容（更宽松的匹配）
    if not chapters:
        # 匹配格式：【第1章： 标题名称】后跟详细内容段落直到【本章出现角色】或***部分
        # 使用更宽松的匹配方式
        chapter_pattern = r"【第(\d+)章：\s+(.*?)】\s*\n\s*(.*?)(?=\n\s*【本章出现角色】|\n\s*\*\*\*|\n\s*$)"
        matches = re.findall(chapter_pattern, outline_text, re.DOTALL)
        
        # 处理匹配到的章节
        for match in matches:
            chapter_num = int(match[0])
            title = match[1].strip()
            content = match[2].strip()
            
            chapters.append({
                'chapter_num': chapter_num,
                'title': title,
                'summary': content
            })
    
    # 如果没有匹配到新的格式，尝试匹配旧格式
    if not chapters:
        # 匹配旧格式：第1章 标题名称
        lines = outline_text.splitlines()
        current_chapter = None
        for line in lines:
            # 匹配章节标题行
            chapter_match = re.match(r'第(\d+)章\s+(.+)', line.strip())
            if chapter_match:
                if current_chapter:
                    # 确保摘要不为空
                    if not current_chapter['summary']:
                        current_chapter['summary'] = "暂无内容梗概"
                    chapters.append(current_chapter)
                    
                chapter_num = int(chapter_match.group(1))
                title = chapter_match.group(2).strip()
                current_chapter = {
                    'chapter_num': chapter_num,
                    'title': title,
                    'summary': ''
                }
            elif current_chapter and line.strip().startswith('内容梗概：'):
                # 提取内容梗概
                summary = line.strip()[6:].strip()  # 去掉"内容梗概："前缀
                current_chapter['summary'] = summary
        
        # 添加最后一个章节
        if current_chapter:
            # 确保摘要不为空
            if not current_chapter['summary']:
                current_chapter['summary'] = "暂无内容梗概"
            chapters.append(current_chapter)
        
    return chapters


def clean_content(content):
    """
    清理章节内容，移除AI生成的标记性内容
    """
    if not content:
        return content
    
    # 移除常见的AI标记内容
    # 移除以【】包围的标记内容
    cleaned_content = re.sub(r'【.*?】', '', content)
    # 移除以[]包围的标记内容（英文方括号）
    cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
    # 清理多余的空白行
    cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content).strip()
    
    return cleaned_content


def parse_ai_response(response):
    """
    解析AI生成的大纲响应
    """
    import re
    
    chapters = []
    
    # 使用正则表达式提取章节信息
    pattern = r'【第(\d+)章：\s*(.*?)】\s*【梗概内容：(.*?)】'
    matches = re.findall(pattern, response, re.DOTALL)
    
    for match in matches:
        chapter_num = int(match[0])
        title = match[1].strip()
        summary = match[2].strip()
        chapters.append({
            'chapter_num': chapter_num,
            'title': title,
            'summary': summary
        })
    
    # 如果没有匹配到标准格式，尝试其他方式解析
    if not chapters:
        # 分割响应为段落
        paragraphs = response.split('\n\n')
        for para in paragraphs:
            if '第' in para and '章' in para and '梗概内容' in para:
                chapter_match = re.search(r'第(\d+)章：?\s*(.*?)(?:\n|$)', para)
                summary_match = re.search(r'梗概内容：(.*)', para, re.DOTALL)
                if chapter_match and summary_match:
                    chapter_num = int(chapter_match.group(1))
                    title = chapter_match.group(2).strip()
                    summary = summary_match.group(1).strip()
                    chapters.append({
                        'chapter_num': chapter_num,
                        'title': title,
                        'summary': summary
                    })
    
    return chapters


def parse_ai_character_response(response):
    """
    解析AI生成的角色响应
    """
    import re
    
    characters = []
    
    # 使用正则表达式提取角色信息
    pattern = r'【角色设计\d+】\s*角色名称：(.*?)\s*角色背景：(.*?)(?=\s*【角色设计\d+】|\s*$)'
    matches = re.findall(pattern, response, re.DOTALL)
    
    for match in matches:
        name = match[0].strip()
        background = match[1].strip()
        characters.append({
            'name': name,
            'background': background
        })
    
    # 如果没有匹配到标准格式，尝试其他方式解析
    if not characters:
        # 分割响应为段落
        paragraphs = response.split('\n\n')
        for para in paragraphs:
            if '角色名称' in para and '角色背景' in para:
                name_match = re.search(r'角色名称：(.*)', para)
                background_match = re.search(r'角色背景：(.*)', para)
                if name_match and background_match:
                    characters.append({
                        'name': name_match.group(1).strip(),
                        'background': background_match.group(1).strip()
                    })
    
    # 如果仍然没有解析到角色，尝试更宽松的匹配方式
    if not characters:
        # 尝试匹配"角色名称："和"角色背景："模式
        name_matches = re.findall(r'角色名称：(.+)', response)
        background_matches = re.findall(r'角色背景：(.+)', response)
        
        # 如果找到匹配项，则按顺序组合
        for i in range(min(len(name_matches), len(background_matches))):
            characters.append({
                'name': name_matches[i].strip(),
                'background': background_matches[i].strip()
            })
    
    # 如果仍然没有解析到角色，尝试简单地按行分割并查找关键信息
    if not characters:
        lines = response.split('\n')
        current_character = {}
        for line in lines:
            if '角色名称：' in line:
                name = line.split('角色名称：', 1)[1].strip()
                current_character['name'] = name
            elif '角色背景：' in line:
                background = line.split('角色背景：', 1)[1].strip()
                current_character['background'] = background
                
            # 如果当前角色信息完整，添加到列表中
            if 'name' in current_character and 'background' in current_character:
                characters.append(current_character.copy())
                current_character = {}
    
    return characters


def load_novel_outline():
    """
    从文件加载小说大纲
    """
    try:
        with open("小说大纲.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception:
        return []


def save_novel_outline(outline_data):
    """
    保存小说大纲到文件
    """
    try:
        with open("小说大纲.json", "w", encoding="utf-8") as f:
            json.dump(outline_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        raise Exception(f"保存小说大纲失败：{str(e)}")


def create_chapter_item(chapter_num, title, summary):
    """
    创建章节列表项
    """
    # 创建自定义列表项
    item = QListWidgetItem()
    
    # 设置项的显示文本
    item.setText(f"第{chapter_num}章: {title}")
    
    # 将章节数据存储在项中
    item.setData(Qt.UserRole, {
        'chapter_num': chapter_num,
        'title': title,
        'summary': summary
    })
    
    return item