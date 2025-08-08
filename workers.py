import sys
import asyncio
import threading
import json
import re
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QTextEdit, QLabel, QLineEdit, QComboBox, QMessageBox, QDialog, QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QListWidget, QListWidgetItem, QCheckBox, QGroupBox, QGridLayout)
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtGui import QTextDocument, QFont

# 导入ai_roles.py中定义的AI类
from ai_roles import AIWriter, AIReader, AIEditor

class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str, str)  # (role, content)
    error = pyqtSignal(str)
    # 新增信号用于更新小说结果窗口
    novel_title_generated = pyqtSignal(str)  # 小说书名生成信号
    chapter_generated = pyqtSignal(int, str, str)  # 章节生成信号 (章节号, 章节标题, 章节内容)
    
    def __init__(self, ai_writer, ai_reader, ai_editor, user_prompt, iteration_limit, novel_settings):
        super().__init__()
        self.ai_writer = ai_writer
        self.ai_reader = ai_reader
        self.ai_editor = ai_editor
        self.user_prompt = user_prompt
        self.iteration_limit = iteration_limit
        self.novel_settings = novel_settings  # 添加小说设置参数
        self.running = True
    
    def extract_rating(self, evaluation_text):
        """
        从AI读者的评价中提取评分
        """
        import re
        # 查找评分模式，例如"8.5分"、"9分"、"评分：9.2"等
        patterns = [
            r'(\d+(?:\.\d+)?)\s*分',  # X.X分 或 X分
            r'评分[：:]\s*(\d+(?:\.\d+)?)',  # 评分：X.X
            r'打分[：:]\s*(\d+(?:\.\d+)?)',  # 打分：X.X
            r'【最终评分：(\d+(?:\.\d+)?)分',  # 新格式：【最终评分：x.x分
        ]
        
        for pattern in patterns:
            match = re.search(pattern, evaluation_text)
            if match:
                try:
                    rating = float(match.group(1))
                    if 1 <= rating <= 10:  # 确保评分在合理范围内
                        return rating
                except ValueError:
                    continue
        return None

    def extract_evaluation_content(self, evaluation_text):
        """
        从AI读者的评价中提取评价内容
        """
        import re
        # 查找评价内容模式
        patterns = [
            r'【评价内容：\s*(.*?)】',  # 新格式：【评价内容：\nXXXX】
            r'【评价内容】\s*【(.*?)】',  # 旧格式：【评价内容】\n【XXXX】
            r'评价内容[：:]\s*(.*?)(?=\n\s*【|\*\*\*|$)',  # 评价内容：XXX
        ]
        
        for pattern in patterns:
            match = re.search(pattern, evaluation_text, re.DOTALL)
            if match:
                return match.group(1).strip()
        return evaluation_text
    
    def run(self):
        try:
            content = ""
            feedback = None
            iteration = 0
            
            # 获取小说设置
            chapter_count = self.novel_settings.get("chapter_count", 30)
            words_per_chapter = self.novel_settings.get("words_per_chapter", 1500)
            
            # 生成小说整体框架和书名
            framework_prompt = f"你是一位有20年以上经验的大师级网文小说作家。根据以下要求生成一个详细的小说框架，包含{chapter_count}章，每章约{words_per_chapter}字：{self.user_prompt}\n\n请确保框架具有引人入胜的开头、扣人心弦的发展和令人满意的结局。"
            novel_framework = self.ai_writer.generate_content(framework_prompt)
            # 在AI角色输出窗口显示框架内容
            self.progress.emit("作家", f"小说框架: {novel_framework}")

            # AI作家生成小说书名
            title_prompt = f"你是一位有20年以上经验的大师级网文小说作家。基于以下小说内容生成一个吸引人的书名：{novel_framework}\n\n只返回书名本身，不要包含任何其他内容或解释。"
            book_title = self.ai_writer.generate_content(title_prompt)
            # 在AI角色输出窗口显示书名生成过程
            self.progress.emit("作家", f"生成的小说书名: {book_title}")
            # 发出小说书名生成信号
            self.novel_title_generated.emit(book_title)

            # 存储完整小说内容
            full_novel = f"书名：{book_title}\n\n"
            
            # 逐章生成小说内容
            for chapter_num in range(1, chapter_count + 1):
                # 构造章节标题
                chapter_title = f"第{chapter_num}章"
                
                # 构造章节提示
                if chapter_num == 1:
                    chapter_prompt = f"你是一位有20年以上经验的大师级网文小说作家。写小说的第一章，要求约{words_per_chapter}字。小说整体框架：{novel_framework}。小说开头需要吸引读者，建立故事基调并引入主要角色。"
                elif chapter_num == chapter_count:
                    chapter_prompt = f"你是一位有20年以上经验的大师级网文小说作家。写小说的最后一章（第{chapter_num}章），要求约{words_per_chapter}字。这是小说的结尾，需要给故事一个完整且令人满意的结局，解决所有主要冲突。小说整体框架：{novel_framework}。此前内容：{full_novel[-2000:]}"
                else:
                    chapter_prompt = f"你是一位有20年以上经验的大师级网文小说作家。写小说的第{chapter_num}章，要求约{words_per_chapter}字。推进故事情节发展，保持读者兴趣。小说整体框架：{novel_framework}。此前内容：{full_novel[-2000:]}"
            
                # 重置迭代参数
                chapter_content = ""
                feedback = None
                iteration = 0
                reader_satisfied = False
            
                # 获取选中的角色
                selected_characters = []
                if hasattr(self, 'characters'):
                    for character in self.characters:
                        if character.get('checkbox') and character['checkbox'].isChecked():
                            selected_characters.append({
                                'name': character['name'],
                                'background': character['background']
                            })
                
                # AI作家与AI读者对抗生成
                while iteration < iteration_limit and self.running:
                    # 在AI角色输出窗口显示生成过程
                    self.progress.emit("作家", f"### 生成第{chapter_num}章中... ###")
                    if feedback is not None:
                        content = self.ai_writer.generate_content(chapter_prompt, feedback=feedback, selected_characters=selected_characters)
                    else:
                        content = self.ai_writer.generate_content(chapter_prompt, selected_characters=selected_characters)
                    # 解析生成的内容
                    content_title, content_text = self._parse_chapter_content(content)
                    # 在AI角色输出窗口只显示生成的小说正文内容，并用【】标记
                    self.progress.emit("作家", f"【第{chapter_num}章 {content_title}】\n【{content_text}】")

                    # AI读者评价内容
                    # 在AI角色输出窗口显示评价过程
                    self.progress.emit("读者", "### 评价中... ###")
                    evaluation = self.ai_reader.evaluate_content(content_text)
                    # 在AI角色输出窗口显示AI读者的评价内容，使用指定格式
                    self.progress.emit("读者", f"【最终评分：x.x分（10分为满分）】\n【评价内容：\n{evaluation}】")

                    # 解析AI读者评分
                    reader_satisfied = False
                    rating = self.extract_rating(evaluation)
                    evaluation_content = self.extract_evaluation_content(evaluation)
                    
                    # 检查生成内容的字数是否符合要求
                    content_word_count = len(content)
                    if content_word_count < self.words_per_chapter:
                        # 如果字数不足，在评分上进行扣分
                        word_count_penalty = (self.words_per_chapter - content_word_count) / self.words_per_chapter * 2  # 最多扣2分
                        if rating is not None:
                            rating = max(1.0, rating - word_count_penalty)  # 不低于1分
                        self.progress.emit("读者", f"【字数检查：当前字数{content_word_count}，要求不少于{self.words_per_chapter}字，字数不足将影响评分】")
                    
                    if rating is not None:
                        self.progress.emit("读者", f"【最终评分：{rating}/10分】\n【评价内容：\n{evaluation_content}】")
                    else:
                        self.progress.emit("读者", f"【评价内容：\n{evaluation_content}】")
                    
                    # 检查AI读者是否满意
                    reader_satisfied = False
                    if rating is not None:
                        if rating >= 9.0:
                            reader_satisfied = True
                    else:
                        # 如果无法提取评分，则使用原来的判断方法
                        if evaluation and "满意" in evaluation.lower():
                            reader_satisfied = True
                    
                    if reader_satisfied:
                        self.progress.emit("读者", f"【第{chapter_num}章读者评价通过】\n### ✅ 最终结论：\n> **【第{chapter_num}章读者评价通过】**——AI读者对本章内容满意")
                        chapter_content = content
                        break  # AI读者满意，跳出循环
                    else:
                        if rating is not None:
                            self.progress.emit("读者", f"### AI 读者对第{chapter_num}章评价不满意（评分{rating}/10分），需要重新生成 ###")
                        else:
                            self.progress.emit("读者", f"### AI 读者对第{chapter_num}章评价不满意，需要修改 ###")
                        # 只将修改意见反馈给AI作家
                        feedback = evaluation
                        iteration += 1

                # 如果达到最大迭代次数仍未满足要求，但仍然需要进入编辑审核流程
                if not chapter_content:
                    # AI读者始终不满意，但达到最大迭代次数
                    self.progress.emit("警告", f"第{chapter_num}章已达到最大迭代次数，但AI读者仍不满意，使用最后一次生成的内容进入编辑审核流程")
                    chapter_content = content if content else ""

                # 第二阶段：AI作家与AI编辑对抗生成（无限循环直到编辑满意）
                self.progress.emit("系统", f"开始第{chapter_num}章编辑审核（第二阶段：作家-编辑对抗）")
                final_content = ""
                edit_feedback = None
                editor_satisfied = False
                
                # AI作家与AI编辑对抗生成（无限循环直到编辑满意）
                while self.running:
                    # 在AI角色输出窗口显示审核过程
                    self.progress.emit("编辑", "### 审核中... ###")
                    review = self.ai_editor.review_content(chapter_content)
                    # 在AI角色输出窗口显示审核内容，使用指定格式
                    self.progress.emit("编辑", f"【审核意见】\n【{review}】")

                    # 检查AI编辑是否满意（通过严格检查输出格式）
                    editor_satisfied = False
                    if review and "【最终审核结果：审核通过】" in review:
                        editor_satisfied = True
                    
                    if editor_satisfied:
                        self.progress.emit("编辑", f"【第{chapter_num}章审核通过】\n### ✅ 最终结论：\n> **【第{chapter_num}章审核通过】**——本章内容符合要求，可以使用")
                        final_content = chapter_content
                        break  # AI编辑满意，跳出循环
                    else:
                        # 严格检查审核结果格式
                        if review and "【最终审核结果：" in review and "】" in review:
                            # 检查是否明确不通过
                            if "【最终审核结果：审核不通过】" in review:
                                self.progress.emit("编辑", f"【第{chapter_num}章审核不通过】\n### ❌ 最终结论：\n> **【第{chapter_num}章审核不通过】**——需要根据以下意见进行修改:\n{review}")
                            else:
                                # 格式正确但不是"审核不通过"，也视为不通过
                                self.progress.emit("编辑", f"【第{chapter_num}章审核不通过】\n### ❌ 最终结论：\n> **【第{chapter_num}章审核不通过】**——编辑输出格式不正确或内容不符合要求:\n{review}")
                        else:
                            # 格式完全不正确
                            self.progress.emit("编辑", f"【第{chapter_num}章审核不通过】\n### ❌ 最终结论：\n> **【第{chapter_num}章审核不通过】**——编辑未按照指定格式输出审核结果:\n{review}")
                        
                        # AI编辑不满意，需要AI作家根据编辑意见修改内容
                        self.progress.emit("作家", "### 根据编辑意见修改中... ###")
                        modified_content = self.ai_writer.generate_content(chapter_prompt, feedback=review)
                        self.progress.emit("作家", f"【第{chapter_num}章： {chapter_title}】\n【章节正文：\n{modified_content}】")
                        chapter_content = modified_content  # 更新内容供下一轮审核
                
                # 第二阶段总是成功完成（因为是无限循环直到满意）
                if not final_content:
                    final_content = chapter_content
                
                # 将章节内容添加到完整小说中
                full_novel += f"\n\n第{chapter_num}章 {content_title}\n\n{content_to_send}"
                
                # 发出章节生成完成信号
                self.chapter_generated.emit(chapter_num, chapter_title, chapter_content)
            
            # 不再发送完整小说到对话窗口
            # self.progress.emit("完成", full_novel)
        
        except Exception as e:
            self.error.emit(str(e))
            return
        finally:
            self.finished.emit()


class ChapterQueueWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str, str)  # (role, content)
    error = pyqtSignal(str)
    chapter_generated = pyqtSignal(int, str, str)  # (chapter_num, chapter_title, content)
    
    def __init__(self, ai_writer, ai_reader, ai_editor, selected_chapters, user_prompt, chapter_count, words_per_chapter, novel_outline, generated_chapters=None):
        super().__init__()
        self.ai_writer = ai_writer
        self.ai_reader = ai_reader
        self.ai_editor = ai_editor
        self.selected_chapters = selected_chapters
        self.user_prompt = user_prompt
        self.chapter_count = chapter_count
        self.words_per_chapter = words_per_chapter
        self.novel_outline = novel_outline
        self.generated_chapters = generated_chapters if generated_chapters is not None else set()  # 记录已生成的章节
        self.running = True
        self.characters = []  # 添加角色信息属性
    
    def _model_progress_callback(self, message):
        """
        模型加载进度回调函数
        """
        self.progress.emit("系统", f"[模型加载进度] {message}")
    
    def extract_rating(self, evaluation_text):
        """
        从AI读者的评价中提取评分
        """
        import re
        # 查找评分模式，例如"8.5分"、"9分"、"评分：9.2"等
        patterns = [
            r'(\d+(?:\.\d+)?)\s*分',  # X.X分 或 X分
            r'评分[：:]\s*(\d+(?:\.\d+)?)',  # 评分：X.X
            r'打分[：:]\s*(\d+(?:\.\d+)?)',  # 打分：X.X
            r'【最终评分：(\d+(?:\.\d+)?)分',  # 新格式：【最终评分：x.x分
        ]
        
        for pattern in patterns:
            match = re.search(pattern, evaluation_text)
            if match:
                try:
                    rating = float(match.group(1))
                    if 1 <= rating <= 10:  # 确保评分在合理范围内
                        return rating
                except ValueError:
                    continue
        return None
    
    def extract_evaluation_content(self, evaluation_text):
        """
        从AI读者的评价中提取评价内容
        """
        import re
        # 查找评价内容模式
        patterns = [
            r'【评价内容：\s*(.*?)】',  # 新格式：【评价内容：\nXXXX】
            r'【评价内容】\s*【(.*?)】',  # 旧格式：【评价内容】\n【XXXX】
            r'评价内容[：:]\s*(.*?)(?=\n\s*【|\*\*\*|$)',  # 评价内容：XXX
        ]
        
        for pattern in patterns:
            match = re.search(pattern, evaluation_text, re.DOTALL)
            if match:
                return match.group(1).strip()
        return evaluation_text

    def run(self):
        try:
            # 如果使用本地模型，等待模型加载完成
            if self.ai_writer.use_local:
                self.progress.emit("系统", f"正在检查作家AI的本地模型: {self.ai_writer.local_model_path}")
                if not self.ai_writer.wait_for_model(timeout=180, progress_callback=self._model_progress_callback):
                    self.error.emit("作家AI的本地模型加载超时或失败")
                    return
                else:
                    self.progress.emit("系统", "作家AI的本地模型已准备就绪")
                    
            if self.ai_reader.use_local:
                self.progress.emit("系统", f"正在检查读者AI的本地模型: {self.ai_reader.local_model_path}")
                if not self.ai_reader.wait_for_model(timeout=180, progress_callback=self._model_progress_callback):
                    self.error.emit("读者AI的本地模型加载超时或失败")
                    return
                else:
                    self.progress.emit("系统", "读者AI的本地模型已准备就绪")
                    
            if self.ai_editor.use_local:
                self.progress.emit("系统", f"正在检查编辑AI的本地模型: {self.ai_editor.local_model_path}")
                if not self.ai_editor.wait_for_model(timeout=180, progress_callback=self._model_progress_callback):
                    self.error.emit("编辑AI的本地模型加载超时或失败")
                    return
                else:
                    self.progress.emit("系统", "编辑AI的本地模型已准备就绪")
            
            # 按章节号排序，确保按顺序生成
            sorted_chapters = sorted(self.selected_chapters, key=lambda x: x['chapter_num'])
            
            # 为选中的每个章节生成内容
            for outline in sorted_chapters:
                if not self.running:
                    break
                    
                chapter_num = outline['chapter_num']
                chapter_title = outline['title']
                chapter_summary = outline['summary']
                
                # 检查前一章节是否已生成（第一章不需要检查）
                if chapter_num > 1:
                    # 查找前一章节
                    prev_chapter = next((c for c in self.novel_outline if c['chapter_num'] == chapter_num - 1), None)
                    # 检查前一章节是否已生成
                    prev_chapter_generated = False
                    
                    # 首先检查前一章节是否在已生成章节集合中
                    if (chapter_num - 1) in self.generated_chapters:
                        prev_chapter_generated = True
                    # 然后检查大纲中的前一章节是否有内容
                    elif prev_chapter and prev_chapter.get('content') and prev_chapter['content'].strip():
                        prev_chapter_generated = True
                    
                    # 如果前一章节未生成，则报错并停止生成任务
                    if not prev_chapter_generated:
                        error_msg = f"第{chapter_num}章的前一章节（第{chapter_num-1}章）尚未生成，请先生成前一章节！"
                        self.progress.emit("系统", error_msg)
                        self.error.emit(error_msg)
                        return  # 停止生成任务
                
                # 构造章节提示 - 优化提示词，包含前面所有章节标题和前一章梗概
                if chapter_num == 1:
                    chapter_prompt = f"你是一位有20年以上经验的大师级网文小说作家。写小说的第一章，要求约{self.words_per_chapter}字，**严格要求生成内容不少于{self.words_per_chapter}字**。根据以下要求和章节大纲创作：\n小说整体要求：{self.user_prompt}\n章节标题：{chapter_title}\n章节内容梗概：{chapter_summary}\n\n小说开头需要吸引读者，建立故事基调并引入主要角色。"
                elif chapter_num == self.chapter_count:
                    # 收集前面所有章节的标题
                    previous_chapters_titles = "\n".join([f"第{c['chapter_num']}章: {c['title']}" for c in self.novel_outline if c['chapter_num'] < chapter_num])
                    
                    # 获取前一章的梗概
                    prev_chapter_summary = prev_chapter.get('summary', '') if prev_chapter else ''
                    
                    chapter_prompt = f"你是一位有20年以上经验的大师级网文小说作家。写小说的最后一章（第{chapter_num}章），要求约{self.words_per_chapter}字，**严格要求生成内容不少于{self.words_per_chapter}字**。根据以下要求和章节大纲创作：\n小说整体要求：{self.user_prompt}\n章节标题：{chapter_title}\n章节内容梗概：{chapter_summary}\n\n这是小说的结尾，需要给故事一个完整且令人满意的结局，解决所有主要冲突。\n\n前面所有章节标题：\n{previous_chapters_titles}\n\n前一章({chapter_num-1})内容梗概：{prev_chapter_summary}"
                else:
                    # 收集前面所有章节的标题
                    previous_chapters_titles = "\n".join([f"第{c['chapter_num']}章: {c['title']}" for c in self.novel_outline if c['chapter_num'] < chapter_num])
                    
                    # 获取前一章的梗概
                    prev_chapter_summary = prev_chapter.get('summary', '') if prev_chapter else ''
                    
                    chapter_prompt = f"你是一位有20年以上经验的大师级网文小说作家。写小说的第{chapter_num}章，要求约{self.words_per_chapter}字，**严格要求生成内容不少于{self.words_per_chapter}字**。根据以下要求和章节大纲创作：\n小说整体要求：{self.user_prompt}\n章节标题：{chapter_title}\n章节内容梗概：{chapter_summary}\n\n推进故事情节发展，保持读者兴趣。\n\n前面所有章节标题：\n{previous_chapters_titles}\n\n前一章({chapter_num-1})内容梗概：{prev_chapter_summary}"
                
                # 在AI角色输出窗口显示提示词
                self.progress.emit("系统", f"### 第{chapter_num}章提示词 ###\n{chapter_prompt}")
                
                # 第一阶段：AI作家与AI读者对抗生成，直到AI读者满意
                self.progress.emit("系统", f"开始第{chapter_num}章内容生成（第一阶段：作家-读者对抗）")
                chapter_content = ""
                feedback = None
                iteration = 0
                reader_satisfied = False
                
                # AI作家与AI读者对抗生成（无限循环直到读者满意）
                while self.running:
                    # 在AI角色输出窗口显示生成过程
                    self.progress.emit("作家", f"### 生成第{chapter_num}章中... ###")
                    if feedback is not None:
                        # 在AI角色输出窗口显示带反馈的提示词
                        writer_prompt_with_feedback = f"提示词：{chapter_prompt}\n\n反馈：{feedback}"
                        self.progress.emit("作家", f"### 提示词（带反馈） ###\n{writer_prompt_with_feedback}")
                        content = self.ai_writer.generate_content(chapter_prompt, feedback=feedback)
                    else:
                        content = self.ai_writer.generate_content(chapter_prompt)
                    # 在AI角色输出窗口只显示生成的小说正文内容，并用【】标记
                    self.progress.emit("作家", f"【第{chapter_num}章： {chapter_title}】\n【章节正文：\n{content}】")

                    # AI读者评价内容
                    # 在AI角色输出窗口显示评价过程
                    self.progress.emit("读者", "### 评价中... ###")
                    evaluation = self.ai_reader.evaluate_content(content)
                    # 在AI角色输出窗口显示AI读者的评价内容，使用指定格式
                    self.progress.emit("读者", f"【最终评分：x.x分（10分为满分）】\n【评价内容：\n{evaluation}】")

                    # 解析AI读者评分
                    reader_satisfied = False
                    rating = self.extract_rating(evaluation)
                    evaluation_content = self.extract_evaluation_content(evaluation)
                    
                    # 检查生成内容的字数是否符合要求
                    content_word_count = len(content)
                    if content_word_count < self.words_per_chapter:
                        # 如果字数不足，在评分上进行扣分
                        word_count_penalty = (self.words_per_chapter - content_word_count) / self.words_per_chapter * 2  # 最多扣2分
                        if rating is not None:
                            rating = max(1.0, rating - word_count_penalty)  # 不低于1分
                        self.progress.emit("读者", f"【字数检查：当前字数{content_word_count}，要求不少于{self.words_per_chapter}字，字数不足将影响评分】")
                    
                    if rating is not None:
                        self.progress.emit("读者", f"【最终评分：{rating}/10分】\n【评价内容：\n{evaluation_content}】")
                    else:
                        self.progress.emit("读者", f"【评价内容：\n{evaluation_content}】")
                    
                    # 检查AI读者是否满意
                    reader_satisfied = False
                    if rating is not None:
                        if rating >= 9.0:  # 修改为9.0分阈值
                            reader_satisfied = True
                    else:
                        # 如果无法提取评分，则使用原来的判断方法
                        if evaluation and "满意" in evaluation.lower():
                            reader_satisfied = True
                    
                    if reader_satisfied:
                        self.progress.emit("读者", f"【第{chapter_num}章读者评价通过】\n### ✅ 最终结论：\n> **【第{chapter_num}章读者评价通过】**——AI读者对本章内容满意")
                        chapter_content = content
                        break  # AI读者满意，跳出循环
                    else:
                        if rating is not None:
                            self.progress.emit("读者", f"### AI 读者对第{chapter_num}章评价不满意（评分{rating}/10分），需要重新生成 ###")
                        else:
                            self.progress.emit("读者", f"### AI 读者对第{chapter_num}章评价不满意，需要修改 ###")
                        # 将修改意见反馈给AI作家，如果评分低于9.0分，包含评价内容
                        if rating is not None and rating < 9.0:
                            feedback = f"章节标题：{chapter_title}\n章节内容梗概：{chapter_summary}\n读者评价：{evaluation_content}"
                        else:
                            feedback = evaluation_content
                        # 移除迭代次数限制，改为无限循环直到AI读者满意
                # 检查是否因用户中断而退出循环
                if not self.running:
                    self.progress.emit("系统", f"第{chapter_num}章生成过程被用户中断")
                    break  # 退出章节生成循环

                # 第一阶段总是成功完成（因为是无限循环直到满意）
                # 检查是否有内容用于第二阶段
                if not chapter_content:
                    chapter_content = content if content else ""
                if not chapter_content:
                    self.progress.emit("系统", f"第{chapter_num}章没有生成有效内容，跳过编辑审核阶段")
                    continue
                
                # 第二阶段：AI作家与AI编辑对抗生成，直到AI编辑满意
                self.progress.emit("系统", f"开始第{chapter_num}章编辑审核（第二阶段：作家-编辑对抗）")
                final_content = ""
                edit_feedback = None
                editor_satisfied = False
                
                # AI作家与AI编辑对抗生成（无限循环直到编辑满意）
                while self.running:
                    # 在AI角色输出窗口显示审核过程
                    self.progress.emit("编辑", "### 审核中... ###")
                    review = self.ai_editor.review_content(chapter_content)
                    # 在AI角色输出窗口显示审核内容，使用指定格式
                    self.progress.emit("编辑", f"【审核意见】\n【{review}】")

                    # 检查AI编辑是否满意（通过严格检查输出格式）
                    editor_satisfied = False
                    if review and "【最终审核结果：审核通过】" in review:
                        editor_satisfied = True
                    
                    if editor_satisfied:
                        self.progress.emit("编辑", f"【第{chapter_num}章审核通过】\n### ✅ 最终结论：\n> **【第{chapter_num}章审核通过】**——本章内容符合要求，可以使用")
                        final_content = chapter_content
                        break  # AI编辑满意，跳出循环
                    else:
                        # 严格检查审核不通过的格式
                        if review and "【最终审核结果：审核不通过】" in review:
                            self.progress.emit("编辑", f"【第{chapter_num}章审核不通过】\n### ❌ 最终结论：\n> **【第{chapter_num}章审核不通过】**——需要根据以下意见进行修改:\n{review}")
                        else:
                            # 如果格式不正确，也视为不通过
                            self.progress.emit("编辑", f"【第{chapter_num}章审核不通过】\n### ❌ 最终结论：\n> **【第{chapter_num}章审核不通过】**——编辑输出格式不正确或内容不符合要求:\n{review}")
                            # AI编辑不满意，需要AI作家根据编辑意见修改内容
                            self.progress.emit("作家", "### 根据编辑意见修改中... ###")
                            modified_content = self.ai_writer.generate_content(chapter_prompt, feedback=review)
                            self.progress.emit("作家", f"【第{chapter_num}章： {chapter_title}】\n【章节正文：\n{modified_content}】")
                            chapter_content = modified_content  # 更新内容供下一轮审核
                # 检查是否因用户中断而退出循环
                if not self.running:
                    self.progress.emit("系统", f"第{chapter_num}章审核过程被用户中断")
                    break  # 退出章节生成循环
                
                # 第二阶段总是成功完成（因为是无限循环直到满意）
                if not final_content:
                    final_content = chapter_content
                
                # 解析章节内容，提取章节标题
                parsed_title, parsed_content = self._parse_chapter_content(chapter_content)
                
                # 将内容发送到最终结果列表（尽可能发送内容）
                content_to_send = final_content or chapter_content
                if content_to_send:
                    # 有内容可发送
                    self.chapter_generated.emit(chapter_num, parsed_title, content_to_send)
                    # 记录已生成的章节
                    self.generated_chapters.add(chapter_num)
                    if final_content:
                        self.progress.emit("系统", f"第{chapter_num}章已通过所有审核，内容已添加到最终结果列表")
                    elif chapter_content:
                        self.progress.emit("系统", f"第{chapter_num}章内容已添加到最终结果列表（编辑审核未通过但使用现有内容）")
                    else:
                        self.progress.emit("系统", f"第{chapter_num}章内容已添加到最终结果列表（使用最后一次生成的内容）")
                else:
                    # 没有任何内容可发送
                    self.progress.emit("系统", f"第{chapter_num}章未能生成有效内容，未添加到最终结果列表")
            
            # 在AI角色输出窗口显示章节完成信息
            if self.running:  # 只有在没有被中断的情况下才显示完成信息
                self.progress.emit("系统", "所有章节处理完成")
            else:
                self.progress.emit("系统", "生成过程被用户中断")
            
        except Exception as e:
            self.error.emit(str(e))
            return
        finally:
            # 确保总是发出finished信号
            self.finished.emit()

    def _parse_chapter_content(self, content_text):
        """
        解析章节内容，提取章节标题和正文
        """
        import re
        
        # 提取章节标题，同时处理多种格式
        title_match = re.search(r'【第\d+章\s+(.*?)】', content_text)
        if not title_match:
            title_match = re.search(r'【第\d+章：\s+(.*?)】', content_text)
        if not title_match:
            title_match = re.search(r'【(第\d+章.*?)】', content_text)
        
        title = title_match.group(1) if title_match else "待定章节"
        
        # 提取章节内容
        content_match = re.search(r'【章节内容(.*?)】', content_text)
        if not content_match:
            # 如果上面的模式没有匹配到，尝试匹配通用的【】内容
            content_match = re.search(r'【(.*?)】', content_text[title_match.end():] if title_match else content_text, re.DOTALL)
        
        content = content_match.group(1).strip() if content_match else content_text
        
        # 如果内容中包含"其它说明内容"部分，则截取到该部分之前
        other_content_match = re.search(r'\*\*\*', content)
        if other_content_match:
            content = content[:other_content_match.start()].strip()
            
        return title, content


class OutlineWorker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str, str)  # (role, content)
    error = pyqtSignal(str)
    # 新增信号用于更新单章大纲生成
    chapter_outline_generated = pyqtSignal(int, str, str)  # (chapter_num, chapter_title, chapter_summary)
    # 添加完整大纲生成信号
    outline_generated = pyqtSignal(str, int, str)  # (outline_content, expected_chapter_count, characters)
    # 新增信号：角色信息更新
    characters_updated = pyqtSignal()

    def __init__(self, ai_senior_writer1, ai_senior_writer2, start_chapter, chapter_count, user_prompt, novel_outline, selected_chapters, characters=None):
        super().__init__()
        self.ai_senior_writer1 = ai_senior_writer1
        self.ai_senior_writer2 = ai_senior_writer2
        self.start_chapter = start_chapter
        self.chapter_count = chapter_count
        self.user_prompt = user_prompt
        self.novel_outline = novel_outline
        self.selected_chapters = selected_chapters
        self.characters = characters
        self.running = True  # 用于控制线程是否继续运行
    
    def _model_progress_callback(self, message):
        """
        模型加载进度回调函数
        """
        self.progress.emit("系统", f"[模型加载进度] {message}")
    
    def run(self):
        try:
            # 如果使用本地模型，等待模型加载完成
            if self.ai_senior_writer1.use_local:
                self.progress.emit("系统", f"正在检查本地模型: {self.ai_senior_writer1.local_model_path}")
                if not self.ai_senior_writer1.wait_for_model(progress_callback=self._model_progress_callback):
                    self.error.emit("本地模型加载超时或失败")
                    return
                else:
                    self.progress.emit("系统", "本地模型已准备就绪，开始生成大纲...")
                    
            # 如果有选中的章节，则只重新生成这些章节
            if self.selected_chapters:
                self._regenerate_selected_chapters()
            else:
                # 否则按原来的逻辑生成大纲
                self._generate_full_outline()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
            # 注意：不要在这里重置running标志，应该在停止生成时由UI控制

    def _regenerate_selected_chapters(self):
        """
        重新生成选中的章节
        """
        # 确保selected_chapters中的元素是章节号而不是字典
        selected_chapter_nums = []
        for item in self.selected_chapters:
            if isinstance(item, dict):
                selected_chapter_nums.append(item['chapter_num'])
            else:
                selected_chapter_nums.append(item)
        
        # 按章节号排序，确保按顺序生成
        selected_chapter_nums.sort()
        
        # 逐个重新生成选中的章节
        for idx, chapter_num in enumerate(selected_chapter_nums):
            # 检查是否被中断
            if not self.running:
                return
                
            # 发送进度信息
            self.progress.emit("系统", f"正在重新生成第{chapter_num}章...")
            
            # 收集前面章节的内容作为上下文，确保情节连贯性
            previous_chapters_context = ""
            if chapter_num == 1:
                # 第一章不需要前面章节的内容
                pass
            else:
                # 收集前面所有章节的标题
                previous_chapters_titles = "\n".join([f"第{c['chapter_num']}章: {c['title']}" for c in self.novel_outline if c['chapter_num'] < chapter_num])
                
                # 对于第二章及以后的章节，使用前一章的标题和梗概以及所有前面章节的标题
                prev_chapter_num = chapter_num - 1
                prev_chapter_info = None
                for chapter in self.novel_outline:
                    if chapter['chapter_num'] == prev_chapter_num:
                        prev_chapter_info = chapter
                        break
                
                # 如果找到了前一章的信息，则添加到上下文
                if prev_chapter_info and 'summary' in prev_chapter_info and prev_chapter_info['summary'].strip():
                    previous_chapters_context = f"前面所有章节标题：\n{previous_chapters_titles}\n\n前一章内容：第{prev_chapter_num}章 {prev_chapter_info['title']}：{prev_chapter_info['summary']}"
            
            # 获取当前章节的标题和梗概（如果存在）
            current_chapter_info = None
            for chapter in self.novel_outline:
                if chapter['chapter_num'] == chapter_num:
                    current_chapter_info = chapter
                    break
            
            # 构造反馈信息（如果存在原章节内容）
            feedback = None
            if current_chapter_info and current_chapter_info.get('summary'):
                # 保留原始章节信息用于提示词，但不直接传递给AI模型
                original_content = f"原章节标题：{current_chapter_info['title']}\n原章节梗概：{current_chapter_info['summary']}"
            
            # 获取选中的角色信息（只在有选中角色时才传递）
            selected_characters = []
            if hasattr(self, 'characters') and self.characters:
                # 检查是否有选中的角色（checkbox被选中）
                for character in self.characters:
                    # 安全检查：确保checkbox对象仍然有效
                    checkbox = character.get('checkbox')
                    if checkbox:
                        try:
                            if checkbox.isChecked():
                                selected_characters.append({
                                    'name': character['name'],
                                    'background': character['background']
                                })
                        except RuntimeError as e:
                            # 捕获"wrapped C/C++ object of type QCheckBox has been deleted"错误
                            self.progress.emit("系统", f"警告：无法访问角色'{character['name']}'的复选框状态: {str(e)}")
                            # 即使无法访问复选框状态，也添加角色信息（保守做法）
                            selected_characters.append({
                                'name': character['name'],
                                'background': character['background']
                            })
            
            # 构造提示词
            professional_background = "你是一位有20年以上经验的网文小说资深作家，擅长创作各种类型的长篇小说，具有丰富的写作经验和深厚的文学功底。"
            
            # 构造角色信息字符串
            character_info = ""
            if selected_characters:
                character_info = "\n\n要求在本章中包含以下角色的互动情节：\n"
                for character in selected_characters:
                    character_info += f"角色名称：{character['name']}，角色背景关系：{character['background']}\n"
                character_info += "\n请在创作中安排这些角色与主角之间的互动，互动内容可以包括但不限于（战斗、聊天、谈情等）。"
            
            # 更严格的格式要求说明
            format_requirements = """请严格按照以下格式输出，格式要求如下：
1. 使用【】方括号包围各个部分
2. 章节标题必须使用"第X章："格式开头
3. 梗概内容部分必须以"【梗概内容： XXX】"格式输出
4. 角色部分必须以"【本章出现角色："开头，每个角色使用"<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>"格式
5. 角色说明必须包含角色能力、社会关系、与主角之间关系等描述内容
6. 最后以"***其它说明或描述内容***"结尾，后面可以添加额外内容

示例格式：
【第1章： 初入仙途】
【梗概内容： 主角林峰在一次意外中穿越到修仙界，发现自己拥有下品灵根。在天机AI的帮助下，他开始了自己的修仙之路。】
【本章出现角色：
<角色名称：林峰,角色说明(主角, 地球2050年意外穿越到修仙界的年轻人，拥有下品灵根，脑中有AI助手"天机", 通过结合现代科技与修真知识不断创新)>
<角色名称：天机AI,角色说明(存储有2050年地球科技知识的人工智能, 主角的得力助手，帮助主角进行各种发明创造)>
】
***其它说明或描述内容***
本章为小说开篇，主要介绍主角背景和世界观设定。
"""
            
            if feedback:
                if chapter_num == 1:
                    prompt = f"{professional_background}\n根据另一位资深作家的反馈修改第{chapter_num}章的内容。\n\n小说整体要求：{self.user_prompt}\n\n反馈意见：{feedback}{character_info}\n\n{format_requirements}\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 角色名称要与前几章保持一致，不要串改角色名称"
                else:
                    prompt = f"{professional_background}\n根据另一位资深作家的反馈修改第{chapter_num}章的内容。\n\n小说整体要求：{self.user_prompt}\n\n{previous_chapters_context}\n\n反馈意见：{feedback}{character_info}\n\n{format_requirements}\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 重点参考前一章的情节发展\n4. 角色名称要与前几章保持一致，不要串改角色名称"
            else:
                if chapter_num == 1:
                    prompt = f"{professional_background}\n请为小说创作第{chapter_num}章的标题和梗概。\n\n小说整体要求：{self.user_prompt}\n\n这是小说的开始章节{character_info}\n\n{format_requirements}\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 角色名称要与前几章保持一致，不要串改角色名称"
                else:
                    prompt = f"{professional_background}\n请为小说创作第{chapter_num}章的标题和梗概。\n\n小说整体要求：{self.user_prompt}\n\n{previous_chapters_context}{character_info}\n\n{format_requirements}\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 重点参考前一章的情节发展\n4. 角色名称要与前几章保持一致，不要串改角色名称"
            
            # 在AI角色输出窗口显示提示词
            self.progress.emit("系统", f"### 第{chapter_num}章重新生成提示词 ###\n{prompt}")
            
            # 生成单章大纲
            chapter_outline = self.ai_senior_writer1.generate_chapter_outline(
                chapter_num, 
                self.user_prompt, 
                previous_chapters_context,
                feedback=feedback,
                selected_characters=selected_characters if selected_characters else None
            )
            
            # 检查是否被中断
            if not self.running:
                return
                
            # 发送AI生成的大纲内容到输出窗口
            self.progress.emit("作家1", chapter_outline)
            
            # 发送进度信息
            self.progress.emit("系统", f"第{chapter_num}章生成完成，开始评估...")
            
            # 评估单章大纲
            evaluation = self.ai_senior_writer2.evaluate_chapter_outline(
                chapter_outline, 
                self.user_prompt, 
                previous_chapters_context  # 使用前面章节的上下文进行评估
            )
            
            # 检查是否被中断
            if not self.running:
                return
                
            # 发送AI评估内容到输出窗口
            self.progress.emit("作家2", evaluation)
            
            # 解析评分
            score = self._parse_score(evaluation)
            
            # 发送进度信息
            self.progress.emit("系统", f"第{chapter_num}章评估完成，评分: {score}分")
            
            # 如果评分低于9.0分，则需要重新生成
            if score < 9.0:
                # 发送进度信息
                self.progress.emit("系统", f"第{chapter_num}章评分低于9.0分，需要重新生成...")
                
                # 提取改进意见
                improvement_suggestion = self._extract_improvement_suggestion(evaluation)
                
                # 只在重新生成章节时使用原始反馈信息（包含旧章节标题和梗概）用于提示词显示
                prompt_feedback = None
                if current_chapter_info and current_chapter_info.get('summary'):
                    prompt_feedback = f"{original_content}\n请根据以下AI读者的反馈进行修改：\n{improvement_suggestion}"
                else:
                    prompt_feedback = improvement_suggestion
                # 构造反馈信息（如果存在原章节内容）
                feedback = improvement_suggestion
                
                # 构造反馈提示词
                feedback_prompt = f"{professional_background}\n根据另一位资深作家的反馈修改第{chapter_num}章的内容。\n\n小说整体要求：{self.user_prompt}\n\n前面章节内容：{previous_chapters_context}\n\n反馈意见：{improvement_suggestion}{character_info}\n\n{format_requirements}\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 重点参考前面章节的情节发展，不要参考尚未发生的后续章节内容\n4. 角色名称要与前几章保持一致，不要串改角色名称"
                
                # 在AI角色输出窗口显示带反馈的提示词
                self.progress.emit("系统", f"### 第{chapter_num}章重新生成提示词（带反馈）###\n{feedback_prompt}")
                
                # 重新生成单章大纲
                chapter_outline = self.ai_senior_writer1.generate_chapter_outline(
                    chapter_num, 
                    self.user_prompt, 
                    previous_chapters_context,
                    feedback=improvement_suggestion,
                    selected_characters=selected_characters if selected_characters else None
                )
                
                # 检查是否被中断
                if not self.running:
                    return
                    
                # 发送重新生成的大纲内容到输出窗口
                self.progress.emit("作家1", chapter_outline)
                
                # 重新评估单章大纲
                re_evaluation = self.ai_senior_writer2.evaluate_chapter_outline(
                    chapter_outline, 
                    self.user_prompt, 
                    previous_chapters_context
                )
                
                # 发送重新评估内容到输出窗口
                self.progress.emit("作家2", re_evaluation)
            # 如果评分达到9.0分或以上，则不需要重新生成，直接使用当前结果
            
            # 解析章节大纲
            title, summary, characters = self._parse_chapter_outline(chapter_outline)
            
            # 构造角色信息字符串
            characters_info = ""
            if characters:
                characters_info = "\n角色信息：\n"
                for character in characters:
                    characters_info += f"  {character['name']}: {character['background']}\n"
            
            # 发送进度信息
            self.progress.emit("系统", f"第{chapter_num}章:\n标题: {title}\n梗概: {summary}{characters_info}")
            
            # 发射单章大纲生成信号
            self.chapter_outline_generated.emit(chapter_num, title, summary)
            
            # 更新上下文，添加新生成的章节内容（用于后续章节的连贯性）
            previous_chapters_context += f"第{chapter_num}章 {title}：{summary}\n"
            
            # 提取并保存本章的角色信息
            self._extract_and_save_single_chapter_characters(characters)

    def _generate_full_outline(self):
        """
        生成完整的小说大纲
        """
        # 获取选中的角色信息（只在有选中角色时才传递）
        selected_characters = []
        if hasattr(self, 'characters') and self.characters:
            # 检查是否有选中的角色（checkbox被选中）
            for character in self.characters:
                # 安全检查：确保checkbox对象仍然有效
                checkbox = character.get('checkbox')
                if checkbox:
                    try:
                        if checkbox.isChecked():
                            selected_characters.append({
                                'name': character['name'],
                                'background': character['background']
                            })
                    except RuntimeError as e:
                        # 捕获"wrapped C/C++ object of type QCheckBox has been deleted"错误
                        self.progress.emit("系统", f"警告：无法访问角色'{character['name']}'的复选框状态: {str(e)}")
                        # 即使无法访问复选框状态，也添加角色信息（保守做法）
                        selected_characters.append({
                            'name': character['name'],
                            'background': character['background']
                        })
        
        # 构造提示词
        professional_background = "你是一位有20年以上经验的网文小说资深作家，擅长创作各种类型的长篇小说，具有丰富的写作经验和深厚的文学功底。"
        
        # 构造角色信息字符串
        character_info = ""
        if selected_characters:
            character_info = "\n\n要求在大纲中包含以下角色的互动情节：\n"
            for character in selected_characters:
                character_info += f"角色名称：{character['name']}，角色背景关系：{character['background']}\n"
            character_info += "\n请在创作中安排这些角色与主角之间的互动，互动内容可以包括但不限于（战斗、聊天、谈情等）。"
        
        prompt = f"{professional_background}\n请为小说创作一个包含{self.chapter_count}章的大纲，从第{self.start_chapter}章开始。\n\n小说整体要求：{self.user_prompt}{character_info}\n\n每章需要包含章节标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：\n【第x章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明：XXX(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 各章节之间要有连贯性，情节发展要合理\n4. 角色名称要保持一致，不要串改角色名称"
        
        # 在AI角色输出窗口显示提示词
        self.progress.emit("系统", f"### 大纲生成提示词 ###\n{prompt}")
        
        # 生成完整大纲
        full_outline = self.ai_senior_writer1.generate_outline(
            self.start_chapter, 
            self.chapter_count, 
            self.user_prompt,
            selected_characters=selected_characters if selected_characters else None
        )
        
        # 检查是否被中断
        if not self.running:
            return
            
        # 发送进度信息
        self.progress.emit("系统", f"大纲生成完成，开始评估...")
        
        # 评估完整大纲
        evaluation = self.ai_senior_writer2.evaluate_outline(
            full_outline, 
            self.user_prompt
        )
        
        # 检查是否被中断
        if not self.running:
            return
            
        # 发送AI评估内容到输出窗口
        self.progress.emit("作家2", evaluation)
        
        # 解析评分
        score = self._parse_score(evaluation)
        
        # 发送进度信息
        self.progress.emit("系统", f"评估完成，评分: {score}分")
        
        # 如果评分低于9.0分，则需要重新生成
        if score < 9.0:
            # 发送进度信息
            self.progress.emit("系统", f"评分低于9.0分，需要重新生成...")
            
            # 提取改进意见
            improvement_suggestion = self._extract_improvement_suggestion(evaluation)
            
            # 构造反馈提示词
            feedback_prompt = f"{professional_background}\n根据另一位资深作家的反馈修改小说大纲。\n\n小说整体要求：{self.user_prompt}\n\n反馈意见：{improvement_suggestion}{character_info}\n\n请提供一个包含{self.chapter_count}章的小说大纲，从第{self.start_chapter}章开始。每章需要包含章节标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：\n【第x章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明：XXX(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 各章节之间要有连贯性，情节发展要合理\n4. 角色名称要保持一致，不要串改角色名称"
            
            # 在AI角色输出窗口显示带反馈的提示词
            self.progress.emit("系统", f"### 大纲重新生成提示词（带反馈）###\n{feedback_prompt}")
            
            # 重新生成大纲，只传递AI读者的评价内容作为反馈
            full_outline = self.ai_senior_writer1.generate_outline(
                self.start_chapter, 
                self.chapter_count, 
                self.user_prompt, 
                feedback=improvement_suggestion,
                selected_characters=selected_characters if selected_characters else None
            )
            
            # 检查是否被中断
            if not self.running:
                return
                
            # 重新评估完整大纲
            re_evaluation = self.ai_senior_writer2.evaluate_outline(
                full_outline, 
                self.user_prompt
            )
            
            # 发送重新评估内容到输出窗口
            self.progress.emit("作家2", re_evaluation)
                
        # 发送最终大纲内容
        self.progress.emit("系统", full_outline)
        
        # 提取所有章节中的角色信息并添加到角色列表中
        characters = self._extract_all_characters(full_outline)
        
        # 发射完整大纲生成信号，包含提取的角色信息
        self.outline_generated.emit(full_outline, self.chapter_count, full_outline)
        
        # 将角色信息保存到角色文件中
        self._extract_and_save_characters(full_outline)
        
        # 发射角色更新信号
        self.characters_updated.emit()
    
    def _extract_all_characters(self, outline_text):
        """
        从大纲中提取所有角色信息
        """
        import re
        
        # 提取所有章节中的角色信息
        all_characters = []
        
        # 匹配每个章节的角色部分
        chapter_character_pattern = r'【本章出现角色：(.*?)】'
        chapter_matches = re.findall(chapter_character_pattern, outline_text, re.DOTALL)
        
        for characters_text in chapter_matches:
            # 匹配每个角色 <角色名称：xxx，角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>
            # 注意：作家1使用的是中文顿号"，"而非英文逗号","
            character_pattern = r'<角色名称：(.*?)，角色说明\(包括角色能力，社会关系，与主角之间关系等等描述内容\)：(.*?)>'
            character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
            for name, background in character_matches:
                all_characters.append({
                    'name': name.strip(),
                    'background': background.strip()
                })
            
            # 如果没有匹配到新格式，尝试匹配使用英文逗号的格式
            if not character_matches:
                # 匹配每个角色 <角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>
                # 使用英文逗号的格式
                character_pattern = r'<角色名称：(.*?)，角色说明\(包括角色能力，社会关系，与主角之间关系等等描述内容\)：(.*?)>'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
                for name, background in character_matches:
                    all_characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
            
            # 如果仍没有匹配到，尝试匹配新格式（用户提供的格式）
            if not character_matches:
                # 匹配新格式 <角色名称：林峰, 角色说明(主角, 地球2050年意外穿越到修仙界的年轻人，拥有下品灵根，脑中有AI助手"天机", 通过结合现代科技与修真知识不断创新)>
                # 支持逗号分隔或无分隔符的格式
                character_pattern = r'<角色名称：([^<>\n]*?)\s*,*\s*角色说明\(([^<>\n]*)\)>'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
                for name, background in character_matches:
                    all_characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
            
            # 如果仍没有匹配到，尝试匹配旧格式
            if not character_matches:
                # 匹配每个角色 (角色名称：XXX，角色背景关系：XXX)
                old_character_pattern = r'\(\s*角色\d*名称：(.*?)，\s*角色\d*背景关系.*?：(.*?)\s*\)'
                old_character_matches = re.findall(old_character_pattern, characters_text, re.DOTALL)
                for name, background in old_character_matches:
                    all_characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
        
        return all_characters

    def _parse_chapter_content(self, content_text):
        """
        解析章节内容，提取章节标题和正文
        """
        import re
        
        # 提取章节标题
        title_match = re.search(r'【第\d+章\s+(.*?)】', content_text)
        title = title_match.group(1) if title_match else "待定章节"
        
        # 提取章节内容
        content_match = re.search(r'【章节内容(.*?)】', content_text)
        if not content_match:
            # 如果上面的模式没有匹配到，尝试匹配通用的【】内容
            content_match = re.search(r'【(.*?)】', content_text[title_match.end():] if title_match else content_text, re.DOTALL)
        
        content = content_match.group(1).strip() if content_match else content_text
        
        # 如果内容中包含"其它说明内容"部分，则截取到该部分之前
        other_content_match = re.search(r'\*\*\*', content)
        if other_content_match:
            content = content[:other_content_match.start()].strip()
            
        return title, content

    def _parse_score(self, evaluation_text):
        """
        从评估文本中解析评分
        """
        import re
        # 匹配评分格式 [最终评分：X.X分] 或 【最终评分：X.X分】
        # 首先尝试匹配方括号格式
        score_match = re.search(r'\[最终评分：(\d+\.?\d*)分\]', evaluation_text)
        if not score_match:
            # 如果没有匹配到，尝试匹配花括号格式
            score_match = re.search(r'【最终评分：(\d+\.?\d*)分】', evaluation_text)
        
        if score_match:
            try:
                return float(score_match.group(1))
            except ValueError:
                return 0.0
        return 0.0
    
    def _parse_chapter_outline(self, outline_text):
        """
        解析章节大纲，提取标题和梗概
        """
        import re
        
        # 提取标题（保留"第XX章"标识）
        title_match = re.search(r'【(第\d+章[：:]?\s*.*?)】', outline_text)
        if not title_match:
            # 兼容旧格式
            title_match = re.search(r'【(第\d+章\s*.*?)】', outline_text)
        title = title_match.group(1) if title_match else "待定章节"
        
        # 提取梗概 - 优先匹配"梗概内容：XXX"格式
        summary_match = re.search(r'【梗概内容：(.*?)】', outline_text, re.DOTALL)
        if not summary_match:
            # 如果上面的模式没有匹配到，尝试匹配"章节梗概：XXX"格式
            summary_match = re.search(r'【章节梗概：(.*?)】', outline_text, re.DOTALL)
        if not summary_match:
            # 如果上面的模式没有匹配到，尝试匹配"本章梗概内容"格式
            summary_match = re.search(r'【本章梗概内容】\s*(.*?)(?=\n\s*【|\n\s*\*\*\*|$)', outline_text, re.DOTALL)
        if not summary_match:
            # 如果上面的模式没有匹配到，尝试匹配详细内容段落（在标题后直到***或【本章出现角色】之前的内容）
            title_end_pos = title_match.end() if title_match else 0
            content_after_title = outline_text[title_end_pos:] if title_end_pos < len(outline_text) else ""
            # 查找内容结束标记
            end_marker_match = re.search(r'\*\*\*|【本章出现角色', content_after_title)
            if end_marker_match:
                content_end_pos = title_end_pos + end_marker_match.start()
                summary_content = outline_text[title_end_pos:content_end_pos]
                # 清理内容，移除前后的空白字符
                summary_content = summary_content.strip()
                if summary_content:
                    summary_match = type('Match', (), {'group': lambda: summary_content})()
            else:
                # 如果没有找到结束标记，则取标题后所有内容直到最后
                summary_content = content_after_title.strip()
                if summary_content:
                    summary_match = type('Match', (), {'group': lambda: summary_content})()
        
        summary = summary_match.group(1).strip() if summary_match and hasattr(summary_match, 'group') else "暂无内容梗概"
        
        # 如果摘要中包含"其它说明内容"部分或"本章出现角色"部分，则截取到该部分之前
        other_content_match = re.search(r'(\*\*\*|【本章出现角色：)', summary)
        if other_content_match:
            summary = summary[:other_content_match.start()].strip()
            
        # 特殊处理：如果summary中包含完整的章节标题格式，则截取到标题之前
        chapter_title_in_summary = re.search(r'【第\d+章', summary)
        if chapter_title_in_summary:
            summary = summary[:chapter_title_in_summary.start()].strip()
            
        # 提取本章出现的角色信息
        characters = []
        characters_match = re.search(r'【本章出现角色：(.*?)】', outline_text, re.DOTALL)
        if characters_match:
            characters_text = characters_match.group(1)
            # 匹配每个角色 <角色名称：xxx，角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>
            # 优先匹配作家1使用的中文顿号"，"格式
            character_pattern = r'<角色名称：(.*?)，角色说明\(包括角色能力，社会关系，与主角之间关系等等描述内容\)：(.*?)>'
            character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
            
            # 如果没有找到匹配，尝试匹配使用英文逗号","的格式
            if not character_matches:
                character_pattern = r'<角色名称：(.*?),角色说明\(包括角色能力，社会关系，与主角之间关系等等描述内容\)：(.*?)>'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
            
            # 如果仍然没有找到匹配，尝试更宽松的匹配方式
            if not character_matches:
                # 匹配包含"角色名称"和"角色说明"的任意内容，直到遇到换行或特殊标记
                character_pattern = r'角色名称：(.*?)，角色说明.*?：(.*?)(?=\n|<角色名称|\*\*\*|【本章出现角色|$)'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
            
            # 处理匹配结果
            for name, background in character_matches:
                characters.append({
                    'name': name.strip(),
                    'background': background.strip()
                })
            
            # 如果仍没有匹配到，尝试匹配新格式（用户提供的格式）
            if not character_matches:
                # 匹配新格式 <角色名称：林峰, 角色说明(主角, 地球2050年意外穿越到修仙界的年轻人，拥有下品灵根，脑中有AI助手"天机", 通过结合现代科技与修真知识不断创新)>
                # 支持逗号分隔或无分隔符的格式
                character_pattern = r'<角色名称：([^<>\n]*?)\s*,*\s*角色说明\(([^<>\n]*)\)>'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
                for name, background in character_matches:
                    characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
            
            # 如果仍没有匹配到，尝试匹配旧格式
            if not character_matches:
                # 匹配每个角色 (角色名称：XXX，角色背景关系：XXX)
                character_pattern = r'\(\s*角色\d*名称：(.*?)，\s*角色\d*背景关系.*?：(.*?)\s*\)'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
                for name, background in character_matches:
                    characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
        
        return title, summary, characters
    
    def _extract_and_save_single_chapter_characters(self, characters):
        """
        从单章中提取角色信息并保存到角色文件中
        """
        import json
        import os
        
        # 如果找到了角色信息，则更新角色文件
        if characters:
            # 读取现有角色文件（如果存在）
            existing_characters = []
            if os.path.exists("角色.json"):
                try:
                    with open("角色.json", "r", encoding="utf-8") as f:
                        existing_characters = json.load(f)
                except:
                    existing_characters = []
            
            # 创建一个集合来跟踪已经存在的角色名称
            existing_names = {char['name'] for char in existing_characters}
            
            # 添加新角色（不重复）
            new_characters_added = 0
            for character in characters:
                if character['name'] not in existing_names:
                    existing_characters.append(character)
                    existing_names.add(character['name'])
                    new_characters_added += 1
            
            # 如果有新角色添加，则保存到文件
            if new_characters_added > 0:
                try:
                    with open("角色.json", "w", encoding="utf-8") as f:
                        json.dump(existing_characters, f, ensure_ascii=False, indent=4)
                    self.progress.emit("系统", f"已提取并保存 {new_characters_added} 个新角色到角色列表中")
                    self.characters_updated.emit()  # 发射角色更新信号
                except Exception as e:
                    self.progress.emit("系统", f"保存角色信息时出错: {str(e)}")

    def _extract_and_save_characters(self, outline_text):
        """
        从大纲中提取所有角色信息并保存到角色文件中
        """
        import re
        import json
        import os
        
        # 提取所有章节中的角色信息
        all_characters = []
        
        # 匹配每个章节的角色部分
        chapter_character_pattern = r'【本章出现角色：(.*?)】'
        chapter_matches = re.findall(chapter_character_pattern, outline_text, re.DOTALL)
        
        for characters_text in chapter_matches:
            # 匹配每个角色 <角色名称：xxx，角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>
            # 作家1使用的是中文顿号"，"而非英文逗号","
            character_pattern = r'<角色名称：(.*?)，角色说明\(包括角色能力，社会关系，与主角之间关系等等描述内容\)：(.*?)>'
            character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
            for name, background in character_matches:
                all_characters.append({
                    'name': name.strip(),
                    'background': background.strip()
                })
            
            # 如果没有匹配到新格式，尝试匹配旧格式
            if not character_matches:
                # 匹配每个角色 <角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>
                # 使用英文逗号的格式
                character_pattern = r'<角色名称：(.*?)，角色说明\(包括角色能力，社会关系，与主角之间关系等等描述内容\)：(.*?)>'
                character_matches = re.findall(character_pattern, characters_text, re.DOTALL)
                for name, background in character_matches:
                    all_characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
            
            # 如果仍没有匹配到，尝试匹配旧格式
            if not character_matches:
                # 匹配每个角色 (角色名称：XXX，角色背景关系：XXX)
                old_character_pattern = r'\(\s*角色\d*名称：(.*?)，\s*角色\d*背景关系.*?：(.*?)\s*\)'
                old_character_matches = re.findall(old_character_pattern, characters_text, re.DOTALL)
                for name, background in old_character_matches:
                    all_characters.append({
                        'name': name.strip(),
                        'background': background.strip()
                    })
        
        # 如果找到了角色信息，则更新角色文件
        if all_characters:
            # 读取现有角色文件（如果存在）
            existing_characters = []
            if os.path.exists("角色.json"):
                try:
                    with open("角色.json", "r", encoding="utf-8") as f:
                        existing_characters = json.load(f)
                except:
                    existing_characters = []
            
            # 创建一个集合来跟踪已经存在的角色名称
            existing_names = {char['name'] for char in existing_characters}
            
            # 添加新角色（不重复）
            new_characters_added = 0
            for character in all_characters:
                if character['name'] not in existing_names:
                    existing_characters.append(character)
                    existing_names.add(character['name'])
                    new_characters_added += 1
            
            # 如果有新角色添加，则保存到文件
            if new_characters_added > 0:
                try:
                    with open("角色.json", "w", encoding="utf-8") as f:
                        json.dump(existing_characters, f, ensure_ascii=False, indent=4)
                    self.progress.emit("系统", f"已从大纲中提取并保存 {new_characters_added} 个新角色到角色列表中")
                    self.characters_updated.emit()  # 发射角色更新信号
                except Exception as e:
                    self.progress.emit("系统", f"保存角色信息时出错: {str(e)}")

    def _extract_improvement_suggestion(self, evaluation_text):
        """
        从评估文本中提取改进意见
        """
        import re
        # 匹配改进意见格式 【改进意见："XXX"】
        improvement_match = re.search(r'【改进意见：“([^”]+)”】', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配带方括号的改进意见格式 [改进意见："XXX"]
        improvement_match = re.search(r'$改进意见：“([^”]+)”$', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配不带引号的改进意见格式 【改进意见：XXX】
        improvement_match = re.search(r'【改进意见：([^】]+)】', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配英文引号格式 【改进意见:"XXX"】
        improvement_match = re.search(r'【改进意见:"([^"]+)】', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配带冒号和空格的改进意见 - 改进意见：XXX
        improvement_match = re.search(r'-\s*改进意见：\s*(.*?)(?=\n|$)', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配带项目符号的改进意见 · 改进意见：XXX
        improvement_match = re.search(r'·\s*改进意见：\s*(.*?)(?=\n|$)', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配带编号的改进意见 1. 改进意见：XXX
        improvement_match = re.search(r'\d+\.\s*改进意见：\s*(.*?)(?=\n|$)', evaluation_text)
        if improvement_match:
            return improvement_match.group(1)
            
        # 匹配HTML标签格式 <improvement>XXX</improvement>
        improvement_match = re.search(r'<improvement>(.*?)</improvement>', evaluation_text, re.DOTALL)
        if improvement_match:
            return improvement_match.group(1).strip()
            
        # 如果仍然没有找到，返回整个评估文本作为反馈
        return evaluation_text
