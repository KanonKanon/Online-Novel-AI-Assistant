import sys
import json
import os
import threading
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QGroupBox, QListWidget, QPushButton, QTextEdit, QLineEdit, 
                             QLabel, QComboBox, QMessageBox, QCheckBox, QDialog, 
                             QDialogButtonBox, QListWidgetItem, QProgressBar, QFileDialog,
                             QDesktopWidget, QAction, QAbstractItemView)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QMetaObject, QThread, pyqtSignal
from PyQt5.QtGui import QTextCursor

# 导入AI类
from ai_roles import AIWriter, AIReader, AIEditor, AISeniorWriter, GlobalModelManager

# 导入工作线程类
from workers import OutlineWorker, ChapterQueueWorker, Worker

# 导入工具函数
from utils import (extract_chapters_from_outline, clean_content, load_novel_outline, 
                   save_novel_outline, create_chapter_item, parse_ai_response, parse_ai_character_response)

# 导入对话框类
from dialogs import NovelSettingsDialog, SettingsDialog, LocalSettingsDialog

# 导入设置加载模块
from path.to.settings_loader import load_settings

class MainWindow(QMainWindow):
    # 添加一个信号用于更新UI
    worldview_generated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.initUI()
        # 连接信号到槽
        self.worldview_generated.connect(self.update_ui_from_signal)
        
    def initUI(self):
        self.setWindowTitle("网文小说AI助手")
        self.setGeometry(100, 100, 1400, 900)
        
        # 创建菜单栏
        menubar = self.menuBar()
        
        # 创建"设置"菜单
        settings_menu = menubar.addMenu('设置')
        
        # 添加"参数设置"菜单项
        settings_action = QAction('参数设置', self)
        settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(settings_action)
        
        # 添加"本地设置"菜单项
        local_settings_action = QAction('本地设置', self)
        local_settings_action.triggered.connect(self.show_local_settings)
        settings_menu.addAction(local_settings_action)
        
        # 创建"文件"菜单
        file_menu = menubar.addMenu('文件')
        
        # 添加"导出小说"菜单项
        export_action = QAction('导出小说', self)
        export_action.triggered.connect(self.export_novel)
        file_menu.addAction(export_action)
        
        # 创建中央部件和主布局（上下结构）
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 上部分：选择小说类型
        type_layout = QHBoxLayout()
        type_label = QLabel("小说类型:")
        self.novel_type = QComboBox()
        self.novel_type.addItems(["玄幻", "仙侠", "都市", "言情", "历史", "科幻", "游戏", "悬疑", "其它"])
        
        # 清空小说内容要求按钮
        self.clear_btn = QPushButton("清空小说内容要求")
        self.clear_btn.clicked.connect(self.clear_all)
        
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.novel_type)
        type_layout.addWidget(self.clear_btn)
        type_layout.addStretch()
        
        main_layout.addLayout(type_layout)
        
        # 下部分：左中右结构
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        
        # 左边：上下结构（小说大纲）
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 上部分：大纲列表
        outline_group = QGroupBox("小说大纲")
        outline_layout = QVBoxLayout(outline_group)
        
        # 创建全选复选框
        self.select_all_checkbox = QCheckBox("全选")
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        outline_layout.addWidget(self.select_all_checkbox)
        
        # 创建大纲列表
        self.outline_list = QListWidget()
        self.outline_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.outline_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.outline_list.setWordWrap(True)
        # 连接大纲列表项点击信号
        self.outline_list.itemClicked.connect(self.on_outline_item_clicked)
        outline_layout.addWidget(self.outline_list)
        
        left_layout.addWidget(outline_group)
        
        # 下部分：【生成大纲】【保存】按钮
        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("生成大纲")
        self.generate_btn.clicked.connect(self.generate_outline)
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_novel_outline)
        # 添加中断生成按钮
        self.stop_outline_btn = QPushButton("中断生成")
        self.stop_outline_btn.clicked.connect(self.stop_outline_generation)
        self.stop_outline_btn.setEnabled(False)  # 默认禁用
        
        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.stop_outline_btn)
        button_layout.addStretch()
        
        left_layout.addLayout(button_layout)
        
        # 中间：上中下结构
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        
        # 上部分：小说内容要求
        input_group = QGroupBox("小说内容要求")
        input_layout = QVBoxLayout(input_group)
        
        self.user_input = QTextEdit()
        self.user_input.setPlaceholderText("请输入小说内容要求...")
        self.user_input.setMinimumHeight(100)  # 保持最小高度为100像素
        # 移除最大高度限制，让其根据父元素高度自动调整
        input_layout.addWidget(self.user_input)
        
        middle_layout.addWidget(input_group)
        
        # 中部分：AI角色输出窗口
        role_output_group = QGroupBox("AI角色输出窗口")
        role_output_layout = QVBoxLayout(role_output_group)
        self.role_output = QTextEdit()
        self.role_output.setReadOnly(True)
        role_output_layout.addWidget(self.role_output)
        middle_layout.addWidget(role_output_group)
        
        # 下部分：小说最终结果列表
        result_group = QGroupBox("小说最终结果窗口")
        result_layout = QVBoxLayout(result_group)
        self.final_result = QListWidget()
        self.final_result.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.final_result.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.final_result.setWordWrap(True)
        # 连接最终结果列表项点击信号
        self.final_result.itemClicked.connect(self.on_final_result_item_clicked)
        result_layout.addWidget(self.final_result)
        middle_layout.addWidget(result_group)
        
        # 添加按钮到中间底部
        bottom_button_layout = QHBoxLayout()
        self.generate_chapter_btn = QPushButton("开始生成")
        self.generate_chapter_btn.clicked.connect(self.start_chapter_generation)
        self.novel_settings_btn = QPushButton("小说设置")
        self.novel_settings_btn.clicked.connect(self.show_novel_settings)
        # 添加生成世界观按钮
        self.generate_worldview_btn = QPushButton("生成世界观")
        self.generate_worldview_btn.clicked.connect(self.generate_worldview)
        # 添加中断生成按钮
        self.stop_generation_btn = QPushButton("中断生成")
        self.stop_generation_btn.clicked.connect(self.stop_chapter_generation)
        self.stop_generation_btn.setEnabled(False)  # 默认禁用
        
        bottom_button_layout.addWidget(self.generate_chapter_btn)
        bottom_button_layout.addWidget(self.novel_settings_btn)
        bottom_button_layout.addWidget(self.generate_worldview_btn)
        bottom_button_layout.addWidget(self.stop_generation_btn)
        bottom_button_layout.addStretch()
        
        middle_layout.addLayout(bottom_button_layout)
        
        # 右边：角色列表
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 添加角色列表
        character_group = QGroupBox("角色列表")
        character_layout = QVBoxLayout(character_group)
        
        # 创建角色列表
        self.character_list = QListWidget()
        self.character_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.character_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用横向滚动条
        self.character_list.setWordWrap(True)  # 启用自动换行
        self.character_list.setSelectionMode(QAbstractItemView.MultiSelection)  # 启用多选模式
        character_layout.addWidget(self.character_list)
        
        # 添加角色操作按钮
        character_button_layout = QHBoxLayout()
        self.save_character_btn = QPushButton("保存角色")
        self.save_character_btn.clicked.connect(self.save_characters)
        self.add_character_btn = QPushButton("添加角色")
        self.add_character_btn.clicked.connect(self.add_character)
        self.delete_character_btn = QPushButton("删除角色")
        self.delete_character_btn.clicked.connect(self.delete_selected_character)
        character_button_layout.addWidget(self.save_character_btn)
        character_button_layout.addWidget(self.add_character_btn)
        character_button_layout.addWidget(self.delete_character_btn)
        character_button_layout.addStretch()
        character_layout.addLayout(character_button_layout)
        
        right_layout.addWidget(character_group)
        
        # 将左中右部分添加到底部布局
        bottom_layout.addWidget(left_widget, 1)
        bottom_layout.addWidget(middle_widget, 2)
        bottom_layout.addWidget(right_widget, 1)
        
        main_layout.addWidget(bottom_widget)
        
        # 初始化AI实例和数据结构
        self.init_ai_instances()
        self.init_data_structures()
        
        # Load saved settings
        self.load_settings()
        # 加载小说大纲和已生成内容
        self.load_novel_outline()
        
        # 加载角色信息
        self.load_characters()

    def init_ai_instances(self):
        """Initialize AI instances"""
        # 读取配置
        settings = load_settings()
        
        # 获取API密钥和模型配置
        api_key = settings.get('api_keys', {}).get('qwen', '')
        novel_outline_model = settings.get('models', {}).get('novel_outline', 'qwen-plus')
        chapter_outline_model = settings.get('models', {}).get('chapter_outline', 'qwen-plus')
        character_model = settings.get('models', {}).get('character', 'qwen-plus')
        
        # 获取本地模型配置
        use_local = settings.get('local_settings', {}).get('use_local', False)
        local_model_path = settings.get('local_settings', {}).get('local_model_path', '')
        
        # 创建AI实例
        self.ai_writer = AIWriter(api_key=api_key, model=character_model)
        self.ai_reader = AIReader(api_key=api_key, model=chapter_outline_model)
        self.ai_editor = AIEditor(api_key=api_key, model=chapter_outline_model)
        self.ai_senior_writer1 = AISeniorWriter(api_key=api_key, model=novel_outline_model,
                                               use_local=use_local, local_model_path=local_model_path)
        self.ai_senior_writer2 = AISeniorWriter(api_key=api_key, model=novel_outline_model,
                                               use_local=use_local, local_model_path=local_model_path)
        
        # 设置AISeniorWriter的主窗口引用
        self.ai_senior_writer1.set_main_window(self)
        self.ai_senior_writer2.set_main_window(self)
    
    def delete_selected_character(self):
        """删除选中的角色"""
        self.log_message("开始执行删除角色操作", "debug")
        try:
            # 获取当前选中的角色 - 使用另一种方法检测选中项
            selected_names = []
            
            # 遍历所有角色项，检查复选框状态
            for i in range(self.character_list.count()):
                item = self.character_list.item(i)
                widget = self.character_list.itemWidget(item)
                if widget:
                    # 获取复选框组件（第一个子组件）
                    checkbox = widget.layout().itemAt(0).widget()
                    if checkbox and checkbox.isChecked():
                        # 获取name_edit组件（右侧widget中的第一个子组件）
                        right_widget = widget.layout().itemAt(1).widget()
                        if right_widget and right_widget.layout().count() > 0:
                            name_edit = right_widget.layout().itemAt(0).widget()
                            if name_edit:
                                selected_names.append(name_edit.text())
            
            self.log_message(f"选中了 {len(selected_names)} 个角色", "debug")
            
            if not selected_names:
                self.log_message("没有选中的角色", "debug")
                return

            # 读取角色.json文件中的现有数据
            try:
                with open("角色.json", "r", encoding="utf-8") as f:
                    characters_data = json.load(f)
            except FileNotFoundError:
                characters_data = []
            except json.JSONDecodeError:
                QMessageBox.critical(self, "错误", "角色文件格式错误，无法读取数据")
                return
            
            # 从角色数据中过滤掉选中的角色
            filtered_characters = [
                char for char in characters_data 
                if char.get('name') not in selected_names
            ]
            
            # 将更新后的数据写回文件
            with open("角色.json", "w", encoding="utf-8") as f:
                json.dump(filtered_characters, f, ensure_ascii=False, indent=4)
            
            # 重新加载角色列表
            self.load_characters()
            
            # 显示成功消息
            success_msg = f"成功删除 {len(selected_names)} 个角色"
            self.role_output.append(f"[系统] {success_msg}")
            QMessageBox.information(self, "成功", success_msg)
            
        except Exception as e:
            error_msg = f"删除角色失败：{str(e)}"
            self.log_message(error_msg, "error")
            self.role_output.append(f"[系统] {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)

    def save_characters(self):
        """保存角色到文件"""
        try:
            # 准备保存的数据
            characters_data = []
            for character in self.characters:
                characters_data.append({
                    'name': character['name'],
                    'background': character['background']
                })
            
            # 保存到文件
            with open("角色.json", "w", encoding="utf-8") as f:
                json.dump(characters_data, f, ensure_ascii=False, indent=4)
            
            self.role_output.append("[系统] 角色信息已保存到 角色.json 文件！")
        except Exception as e:
            error_msg = f"保存角色信息失败：{str(e)}"
            self.role_output.append(f"[系统] {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)

    def init_data_structures(self):
        """Initialize data structures"""
        self.novel_outline = []  # 存储大纲信息 [{chapter_num, title, summary, item_widget}]
        self.chapter_items_map = {}  # 映射章节号到最终结果列表中的项
        self.characters = []  # 存储角色信息 [{name, background, item_widget}]
        
    def initialize_ai_instances(self):
        """Initialize AI writer, reader and editor instances"""
        self.ai_writer = AIWriter()
        self.ai_reader = AIReader()
        self.ai_editor = AIEditor()
        
    def create_character_item(self, name, background):
        """创建角色列表项"""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)  # 改为水平布局
        item_layout.setContentsMargins(5, 5, 5, 5)
        item_layout.setSpacing(5)
        
        # 左侧：复选框
        checkbox = QCheckBox()
        
        # 右侧：上下结构
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)
        
        # 上部分：角色名称（可编辑）
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("角色名称")
        
        # 下部分：角色说明（可编辑）- 包含个人能力，社会关系等
        background_edit = QTextEdit()
        background_edit.setPlaceholderText("角色说明（包含个人能力，社会关系等）")
        background_edit.setMaximumHeight(80)
        background_edit.setPlainText(background)
        
        right_layout.addWidget(name_edit)
        right_layout.addWidget(background_edit)
        
        # 连接信号，当内容改变时更新数据
        def on_name_changed(text):
            for character in self.characters:
                if character['item_widget'] == item_widget:
                    character['name'] = text
                    break
        
        def on_background_changed():
            for character in self.characters:
                if character['item_widget'] == item_widget:
                    character['background'] = background_edit.toPlainText()
                    break
        
        name_edit.textChanged.connect(on_name_changed)
        background_edit.textChanged.connect(on_background_changed)
        
        # 添加到水平布局
        item_layout.addWidget(checkbox)
        item_layout.addWidget(right_widget, 1)  # 添加伸展因子，使右侧组件填充剩余空间
        
        # 创建列表项并设置自定义widget
        item = QListWidgetItem()
        item.setSizeHint(item_widget.sizeHint())
        self.character_list.addItem(item)
        self.character_list.setItemWidget(item, item_widget)
        
        return {
            'name': name,
            'background': background,
            'checkbox': checkbox,
            'item_widget': item_widget,
            'name_edit': name_edit,
            'background_edit': background_edit,
            'list_item': item
        }

    def add_character(self):
        """添加新角色"""
        self.log_message("开始添加新角色", "info")
        # 创建添加角色对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("添加角色")
        dialog.setGeometry(0, 0, 400, 250)  # 设置窗口大小，位置暂时设置为(0,0)
        
        # 将对话框居中显示在主窗口中央
        dialog.move(
            self.geometry().center().x() - dialog.width() // 2,
            self.geometry().center().y() - dialog.height() // 2
        )
    
        layout = QVBoxLayout(dialog)
        layout.setSpacing(5)  # 设置组件之间垂直间距为5px
        layout.setContentsMargins(10, 10, 10, 10)  # 设置边距

        # 角色名称输入
        name_label = QLabel("角色名称:")
        layout.addWidget(name_label)
        name_edit = QLineEdit()
        layout.addWidget(name_edit)

        # 角色说明输入（包含个人能力，社会关系等）
        background_label = QLabel("角色说明（包含个人能力，社会关系等）:")
        layout.addWidget(background_label)
        background_edit = QTextEdit()
        background_edit.setMaximumHeight(80)  # 减小高度以进一步压缩空间
        layout.addWidget(background_edit)

        # AI生成按钮
        ai_generate_button = QPushButton("AI生成")
        ai_generate_button.clicked.connect(lambda: self.generate_character_with_ai(name_edit, background_edit))
        layout.addWidget(ai_generate_button)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 设置布局伸展因子，确保所有组件靠上排列
        layout.addStretch(1)

        if dialog.exec_() == QDialog.Accepted:
            name = name_edit.text().strip()
            background = background_edit.toPlainText().strip()

            if name:
                self.log_message(f"创建角色: {name}", "debug")
                character = self.create_character_item(name, background)
                self.characters.append(character)
                self.log_message(f"角色 {name} 添加成功", "info")
            else:
                self.log_message("角色添加失败: 名称为空", "warning")
                QMessageBox.warning(self, "警告", "角色名称不能为空！")
    
    def generate_character_with_ai(self, name_edit, background_edit):
        """使用AI生成角色信息"""
        self.log_message(">>> 进入generate_character_with_ai方法", "debug")
        from PyQt5.QtCore import QTimer
        
        # 获取用户输入的小说主题
        novel_theme = self.user_input.toPlainText().strip()
        self.log_message(f"检查用户输入的小说主题，长度: {len(novel_theme)} 字符", "debug")
        if not novel_theme:
            self.log_message("小说主题为空，准备显示警告", "debug")
            def show_warning():
                self.log_message("警告：请先输入小说主题内容！", "warning")
                QMessageBox.warning(self, "警告", "请先输入小说主题内容！")
            QTimer.singleShot(0, show_warning)
            self.log_message("<<< 因小说主题为空退出generate_character_with_ai方法", "debug")
            return
        
        self.log_message("小说主题检查通过", "debug")
        # 显示生成进度信息到AI角色输出窗口
        self.log_message("开始AI角色生成...")
        
        # 在新线程中生成内容
        def generate_in_thread():
            self.log_message("开始在工作线程中生成角色...", "debug")
            self.log_message(f"小说主题长度: {len(novel_theme)} 字符", "debug")
            try:
                # 使用ai_senior_writer1.generate_character_design替代ai_writer.generate_content
                self.log_message("调用AI生成角色设计...", "debug")
                ai_response = self.ai_senior_writer1.generate_character_design(novel_theme)
                self.log_message("<<< 退出generate_in_thread函数", "debug")
                self.log_message(f"工作线程中AI响应完成，长度: {len(ai_response) if ai_response else 0} 字符", "debug")
                self.log_message(f"AI响应前100字符: {ai_response[:100] if ai_response else 'None'}", "debug")
                self.log_message("准备处理AI响应结果...", "debug")
                
                # 检查AI响应是否为空或包含错误
                if not ai_response:
                    self.log_message("检查AI响应: 空响应", "debug")
                    error_msg = "AI生成角色失败：空响应"
                    self.log_message(error_msg, "error")
                    # 在主线程中显示错误
                    def show_error():
                        self.log_message("准备显示空响应错误对话框", "debug")
                        QMessageBox.critical(self, "错误", "AI生成角色失败：空响应")
                    QTimer.singleShot(0, show_error)
                elif "Error" in ai_response:
                    self.log_message("检查AI响应: 包含错误信息", "debug")
                    error_msg = f"AI生成角色失败：{ai_response}"
                    self.log_message(error_msg, "error")
                    # 在主线程中显示错误
                    def show_error():
                        self.log_message("准备显示错误信息对话框", "debug")
                        QMessageBox.critical(self, "错误", f"AI生成角色失败：{ai_response}")
                    QTimer.singleShot(0, show_error)
                else:
                    self.log_message("AI响应检查通过，准备在主线程中处理结果...", "debug")
                    # 将AI返回的完整内容输出到AI角色输出窗口中
                    def show_success():
                        self.log_message("在主线程中处理AI响应结果...", "debug")
                        self.role_output.append("[AI] " + ai_response)
                        self.log_message("AI生成角色成功，准备显示选择窗口...")
                        # 在主线程中处理结果并显示选择窗口
                        self.after_character_generation(ai_response, name_edit, background_edit)
                        self.log_message("after_character_generation方法调用完成", "debug")
                    
                    # 确保在主线程中执行show_success
                    from PyQt5.QtCore import Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "invoke_show_success", Qt.QueuedConnection, 
                                           Q_ARG(object, show_success))
                    self.log_message("已安排show_success任务", "debug")
            except Exception as e:
                self.log_message("<<< 异常退出generate_in_thread函数", "debug")
                error_msg = f"AI生成角色失败：{str(e)}"
                import traceback
                self.log_message(f"异常详情: {error_msg}", "error")
                self.log_message(f"异常堆栈: {traceback.format_exc()}", "error")
                # 在主线程中显示错误
                def show_error():
                    self.log_message("准备显示异常对话框", "debug")
                    QMessageBox.critical(self, "错误", f"AI生成角色失败：{str(e)}")
                QTimer.singleShot(0, show_error)
    
        @pyqtSlot(object)
        def invoke_show_success(self, show_success):
            """在主线程中执行show_success函数"""
            self.log_message("进入invoke_show_success方法", "debug")
            try:
                show_success()
                self.log_message("show_success函数执行完成", "debug")
            except Exception as e:
                self.log_message(f"执行show_success时发生错误: {str(e)}", "error")
                import traceback
                self.log_message(f"错误堆栈: {traceback.format_exc()}", "error")
            self.log_message("退出invoke_show_success方法", "debug")
    
    def generate_worldview(self):
        """使用AI生成世界观"""
        # 获取用户输入的小说内容要求
        user_prompt = self.user_input.toPlainText().strip()
        if not user_prompt:
            QMessageBox.warning(self, "警告", "请先输入小说内容要求！")
            return
        
        # 显示生成进度信息到AI角色输出窗口
        self.role_output.append("[系统] 开始生成世界观...")
        
        # 构造提示词
        prompt = f"""你是一位专业的小说世界观构建师，擅长创造各种类型的奇幻世界。请根据以下小说内容要求，构建一个完整的世界观设定：

小说内容要求：{user_prompt}

请提供以下内容的详细描述：
1. 世界名称和基本描述
2. 世界的地理分布描述
3. 世界的势力分布描述
4. 世界的修炼体系或能力体系描述

要求总字数不少于800字。请严格按照以下格式输出：
世界观设定
世界名称
[世界名称和基本描述]
地理分布
[世界的地理分布描述]
势力分布
[世界的势力分布描述]
修炼体系
[世界的修炼体系或能力体系描述]
"""
        
        # 在AI角色输出窗口显示提示词
        self.role_output.append(f"### 世界观生成提示词 ###\n{prompt}")
        
        # 在新线程中生成内容，避免阻塞UI
        def generate_in_thread():
            try:
                # 使用AI作家生成世界观
                worldview_content = self.ai_writer.generate_worldview(prompt)
                
                # 使用信号在主线程中执行UI更新
                self.worldview_generated.emit(worldview_content)
                
            except Exception as e:
                # 在主线程中显示错误
                def show_error():
                    error_msg = f"生成世界观时发生异常：{str(e)}"
                    self.role_output.append(f"[系统] {error_msg}")
                    QMessageBox.critical(self, "错误", error_msg)
                QTimer.singleShot(0, show_error)
        
        # 启动线程执行生成任务
        thread = threading.Thread(target=generate_in_thread)
        thread.daemon = True
        thread.start()

        self.role_output.append("[系统] 已启动世界观生成线程，请稍候...")


# 导入工作线程类
from workers import OutlineWorker, ChapterQueueWorker, Worker

# 导入工具函数
from utils import (extract_chapters_from_outline, clean_content, load_novel_outline, 
                   save_novel_outline, create_chapter_item, parse_ai_response, parse_ai_character_response)

# 导入对话框类
from dialogs import NovelSettingsDialog, SettingsDialog, LocalSettingsDialog

# 导入设置加载模块
from path.to.settings_loader import load_settings

class MainWindow(QMainWindow):
    # 添加一个信号用于更新UI
    worldview_generated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.initUI()
        # 连接信号到槽
        self.worldview_generated.connect(self.update_ui_from_signal)
        
    def initUI(self):
        self.setWindowTitle("网文小说AI助手")
        self.setGeometry(100, 100, 1400, 900)
        
        # 创建菜单栏
        menubar = self.menuBar()
        
        # 创建"设置"菜单
        settings_menu = menubar.addMenu('设置')
        
        # 添加"参数设置"菜单项
        settings_action = QAction('参数设置', self)
        settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(settings_action)
        
        # 添加"本地设置"菜单项
        local_settings_action = QAction('本地设置', self)
        local_settings_action.triggered.connect(self.show_local_settings)
        settings_menu.addAction(local_settings_action)
        
        # 创建"文件"菜单
        file_menu = menubar.addMenu('文件')
        
        # 添加"导出小说"菜单项
        export_action = QAction('导出小说', self)
        export_action.triggered.connect(self.export_novel)
        file_menu.addAction(export_action)
        
        # 创建中央部件和主布局（上下结构）
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 上部分：选择小说类型
        type_layout = QHBoxLayout()
        type_label = QLabel("小说类型:")
        self.novel_type = QComboBox()
        self.novel_type.addItems(["玄幻", "仙侠", "都市", "言情", "历史", "科幻", "游戏", "悬疑", "其它"])
        
        # 清空小说内容要求按钮
        self.clear_btn = QPushButton("清空小说内容要求")
        self.clear_btn.clicked.connect(self.clear_all)
        
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.novel_type)
        type_layout.addWidget(self.clear_btn)
        type_layout.addStretch()
        
        main_layout.addLayout(type_layout)
        
        # 下部分：左中右结构
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        
        # 左边：上下结构（小说大纲）
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 上部分：大纲列表
        outline_group = QGroupBox("小说大纲")
        outline_layout = QVBoxLayout(outline_group)
        
        # 创建全选复选框
        self.select_all_checkbox = QCheckBox("全选")
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        outline_layout.addWidget(self.select_all_checkbox)
        
        # 创建大纲列表
        self.outline_list = QListWidget()
        self.outline_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.outline_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.outline_list.setWordWrap(True)
        # 连接大纲列表项点击信号
        self.outline_list.itemClicked.connect(self.on_outline_item_clicked)
        outline_layout.addWidget(self.outline_list)
        
        left_layout.addWidget(outline_group)
        
        # 下部分：【生成大纲】【保存】按钮
        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("生成大纲")
        self.generate_btn.clicked.connect(self.generate_outline)
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_novel_outline)
        # 添加中断生成按钮
        self.stop_outline_btn = QPushButton("中断生成")
        self.stop_outline_btn.clicked.connect(self.stop_outline_generation)
        self.stop_outline_btn.setEnabled(False)  # 默认禁用
        
        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.stop_outline_btn)
        button_layout.addStretch()
        
        left_layout.addLayout(button_layout)
        
        # 中间：上中下结构
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        
        # 上部分：小说内容要求
        input_group = QGroupBox("小说内容要求")
        input_layout = QVBoxLayout(input_group)
        
        self.user_input = QTextEdit()
        self.user_input.setPlaceholderText("请输入小说内容要求...")
        self.user_input.setMinimumHeight(100)  # 保持最小高度为100像素
        # 移除最大高度限制，让其根据父元素高度自动调整
        input_layout.addWidget(self.user_input)
        
        middle_layout.addWidget(input_group)
        
        # 中部分：AI角色输出窗口
        role_output_group = QGroupBox("AI角色输出窗口")
        role_output_layout = QVBoxLayout(role_output_group)
        self.role_output = QTextEdit()
        self.role_output.setReadOnly(True)
        role_output_layout.addWidget(self.role_output)
        middle_layout.addWidget(role_output_group)
        
        # 下部分：小说最终结果列表
        result_group = QGroupBox("小说最终结果窗口")
        result_layout = QVBoxLayout(result_group)
        self.final_result = QListWidget()
        self.final_result.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.final_result.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.final_result.setWordWrap(True)
        # 连接最终结果列表项点击信号
        self.final_result.itemClicked.connect(self.on_final_result_item_clicked)
        result_layout.addWidget(self.final_result)
        middle_layout.addWidget(result_group)
        
        # 添加按钮到中间底部
        bottom_button_layout = QHBoxLayout()
        self.generate_chapter_btn = QPushButton("开始生成")
        self.generate_chapter_btn.clicked.connect(self.start_chapter_generation)
        self.novel_settings_btn = QPushButton("小说设置")
        self.novel_settings_btn.clicked.connect(self.show_novel_settings)
        # 添加生成世界观按钮
        self.generate_worldview_btn = QPushButton("生成世界观")
        self.generate_worldview_btn.clicked.connect(self.generate_worldview)
        # 添加中断生成按钮
        self.stop_generation_btn = QPushButton("中断生成")
        self.stop_generation_btn.clicked.connect(self.stop_chapter_generation)
        self.stop_generation_btn.setEnabled(False)  # 默认禁用
        
        bottom_button_layout.addWidget(self.generate_chapter_btn)
        bottom_button_layout.addWidget(self.novel_settings_btn)
        bottom_button_layout.addWidget(self.generate_worldview_btn)
        bottom_button_layout.addWidget(self.stop_generation_btn)
        bottom_button_layout.addStretch()
        
        middle_layout.addLayout(bottom_button_layout)
        
        # 右边：角色列表
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 添加角色列表
        character_group = QGroupBox("角色列表")
        character_layout = QVBoxLayout(character_group)
        
        # 创建角色列表
        self.character_list = QListWidget()
        self.character_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.character_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用横向滚动条
        self.character_list.setWordWrap(True)  # 启用自动换行
        self.character_list.setSelectionMode(QAbstractItemView.MultiSelection)  # 启用多选模式
        character_layout.addWidget(self.character_list)
        
        # 添加角色操作按钮
        character_button_layout = QHBoxLayout()
        self.save_character_btn = QPushButton("保存角色")
        self.save_character_btn.clicked.connect(self.save_characters)
        self.add_character_btn = QPushButton("添加角色")
        self.add_character_btn.clicked.connect(self.add_character)
        self.delete_character_btn = QPushButton("删除角色")
        self.delete_character_btn.clicked.connect(self.delete_selected_character)
        character_button_layout.addWidget(self.save_character_btn)
        character_button_layout.addWidget(self.add_character_btn)
        character_button_layout.addWidget(self.delete_character_btn)
        character_button_layout.addStretch()
        character_layout.addLayout(character_button_layout)
        
        right_layout.addWidget(character_group)
        
        # 将左中右部分添加到底部布局
        bottom_layout.addWidget(left_widget, 1)
        bottom_layout.addWidget(middle_widget, 2)
        bottom_layout.addWidget(right_widget, 1)
        
        main_layout.addWidget(bottom_widget)
        
        # 初始化AI实例和数据结构
        self.init_ai_instances()
        self.init_data_structures()
        
        # Load saved settings
        self.load_settings()
        # 加载小说大纲和已生成内容
        self.load_novel_outline()
        
        # 加载角色信息
        self.load_characters()

    def init_ai_instances(self):
        """Initialize AI instances"""
        # 读取配置
        settings = load_settings()
        
        # 获取API密钥和模型配置
        api_key = settings.get('api_keys', {}).get('qwen', '')
        novel_outline_model = settings.get('models', {}).get('novel_outline', 'qwen-plus')
        chapter_outline_model = settings.get('models', {}).get('chapter_outline', 'qwen-plus')
        character_model = settings.get('models', {}).get('character', 'qwen-plus')
        
        # 获取本地模型配置
        use_local = settings.get('local_settings', {}).get('use_local', False)
        local_model_path = settings.get('local_settings', {}).get('local_model_path', '')
        
        # 创建AI实例
        self.ai_writer = AIWriter(api_key=api_key, model=character_model)
        self.ai_reader = AIReader(api_key=api_key, model=chapter_outline_model)
        self.ai_editor = AIEditor(api_key=api_key, model=chapter_outline_model)
        self.ai_senior_writer1 = AISeniorWriter(api_key=api_key, model=novel_outline_model,
                                               use_local=use_local, local_model_path=local_model_path)
        self.ai_senior_writer2 = AISeniorWriter(api_key=api_key, model=novel_outline_model,
                                               use_local=use_local, local_model_path=local_model_path)
        
        # 设置AISeniorWriter的主窗口引用
        self.ai_senior_writer1.set_main_window(self)
        self.ai_senior_writer2.set_main_window(self)
    
    def delete_selected_character(self):
        """删除选中的角色"""
        self.log_message("开始执行删除角色操作", "debug")
        try:
            # 获取当前选中的角色 - 使用另一种方法检测选中项
            selected_names = []
            
            # 遍历所有角色项，检查复选框状态
            for i in range(self.character_list.count()):
                item = self.character_list.item(i)
                widget = self.character_list.itemWidget(item)
                if widget:
                    # 获取复选框组件（第一个子组件）
                    checkbox = widget.layout().itemAt(0).widget()
                    if checkbox and checkbox.isChecked():
                        # 获取name_edit组件（右侧widget中的第一个子组件）
                        right_widget = widget.layout().itemAt(1).widget()
                        if right_widget and right_widget.layout().count() > 0:
                            name_edit = right_widget.layout().itemAt(0).widget()
                            if name_edit:
                                selected_names.append(name_edit.text())
            
            self.log_message(f"选中了 {len(selected_names)} 个角色", "debug")
            
            if not selected_names:
                self.log_message("没有选中的角色", "debug")
                return

            # 读取角色.json文件中的现有数据
            try:
                with open("角色.json", "r", encoding="utf-8") as f:
                    characters_data = json.load(f)
            except FileNotFoundError:
                characters_data = []
            except json.JSONDecodeError:
                QMessageBox.critical(self, "错误", "角色文件格式错误，无法读取数据")
                return
            
            # 从角色数据中过滤掉选中的角色
            filtered_characters = [
                char for char in characters_data 
                if char.get('name') not in selected_names
            ]
            
            # 将更新后的数据写回文件
            with open("角色.json", "w", encoding="utf-8") as f:
                json.dump(filtered_characters, f, ensure_ascii=False, indent=4)
            
            # 重新加载角色列表
            self.load_characters()
            
            # 显示成功消息
            success_msg = f"成功删除 {len(selected_names)} 个角色"
            self.role_output.append(f"[系统] {success_msg}")
            QMessageBox.information(self, "成功", success_msg)
            
        except Exception as e:
            error_msg = f"删除角色失败：{str(e)}"
            self.log_message(error_msg, "error")
            self.role_output.append(f"[系统] {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)

    def save_characters(self):
        """保存角色到文件"""
        try:
            # 准备保存的数据
            characters_data = []
            for character in self.characters:
                characters_data.append({
                    'name': character['name'],
                    'background': character['background']
                })
            
            # 保存到文件
            with open("角色.json", "w", encoding="utf-8") as f:
                json.dump(characters_data, f, ensure_ascii=False, indent=4)
            
            self.role_output.append("[系统] 角色信息已保存到 角色.json 文件！")
        except Exception as e:
            error_msg = f"保存角色信息失败：{str(e)}"
            self.role_output.append(f"[系统] {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)

    def init_data_structures(self):
        """Initialize data structures"""
        self.novel_outline = []  # 存储大纲信息 [{chapter_num, title, summary, item_widget}]
        self.chapter_items_map = {}  # 映射章节号到最终结果列表中的项
        self.characters = []  # 存储角色信息 [{name, background, item_widget}]
        
    def initialize_ai_instances(self):
        """Initialize AI writer, reader and editor instances"""
        self.ai_writer = AIWriter()
        self.ai_reader = AIReader()
        self.ai_editor = AIEditor()
        
    def create_character_item(self, name, background):
        """创建角色列表项"""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)  # 改为水平布局
        item_layout.setContentsMargins(5, 5, 5, 5)
        item_layout.setSpacing(5)
        
        # 左侧：复选框
        checkbox = QCheckBox()
        
        # 右侧：上下结构
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)
        
        # 上部分：角色名称（可编辑）
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("角色名称")
        
        # 下部分：角色说明（可编辑）- 包含个人能力，社会关系等
        background_edit = QTextEdit()
        background_edit.setPlaceholderText("角色说明（包含个人能力，社会关系等）")
        background_edit.setMaximumHeight(80)
        background_edit.setPlainText(background)
        
        right_layout.addWidget(name_edit)
        right_layout.addWidget(background_edit)
        
        # 连接信号，当内容改变时更新数据
        def on_name_changed(text):
            for character in self.characters:
                if character['item_widget'] == item_widget:
                    character['name'] = text
                    break
        
        def on_background_changed():
            for character in self.characters:
                if character['item_widget'] == item_widget:
                    character['background'] = background_edit.toPlainText()
                    break
        
        name_edit.textChanged.connect(on_name_changed)
        background_edit.textChanged.connect(on_background_changed)
        
        # 添加到水平布局
        item_layout.addWidget(checkbox)
        item_layout.addWidget(right_widget, 1)  # 添加伸展因子，使右侧组件填充剩余空间
        
        # 创建列表项并设置自定义widget
        item = QListWidgetItem()
        item.setSizeHint(item_widget.sizeHint())
        self.character_list.addItem(item)
        self.character_list.setItemWidget(item, item_widget)
        
        return {
            'name': name,
            'background': background,
            'checkbox': checkbox,
            'item_widget': item_widget,
            'name_edit': name_edit,
            'background_edit': background_edit,
            'list_item': item
        }

    def add_character(self):
        """添加新角色"""
        self.log_message("开始添加新角色", "info")
        # 创建添加角色对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("添加角色")
        dialog.setGeometry(0, 0, 400, 250)  # 设置窗口大小，位置暂时设置为(0,0)
        
        # 将对话框居中显示在主窗口中央
        dialog.move(
            self.geometry().center().x() - dialog.width() // 2,
            self.geometry().center().y() - dialog.height() // 2
        )
    
        layout = QVBoxLayout(dialog)
        layout.setSpacing(5)  # 设置组件之间垂直间距为5px
        layout.setContentsMargins(10, 10, 10, 10)  # 设置边距

        # 角色名称输入
        name_label = QLabel("角色名称:")
        layout.addWidget(name_label)
        name_edit = QLineEdit()
        layout.addWidget(name_edit)

        # 角色说明输入（包含个人能力，社会关系等）
        background_label = QLabel("角色说明（包含个人能力，社会关系等）:")
        layout.addWidget(background_label)
        background_edit = QTextEdit()
        background_edit.setMaximumHeight(80)  # 减小高度以进一步压缩空间
        layout.addWidget(background_edit)

        # AI生成按钮
        ai_generate_button = QPushButton("AI生成")
        ai_generate_button.clicked.connect(lambda: self.generate_character_with_ai(name_edit, background_edit))
        layout.addWidget(ai_generate_button)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 设置布局伸展因子，确保所有组件靠上排列
        layout.addStretch(1)

        if dialog.exec_() == QDialog.Accepted:
            name = name_edit.text().strip()
            background = background_edit.toPlainText().strip()

            if name:
                self.log_message(f"创建角色: {name}", "debug")
                character = self.create_character_item(name, background)
                self.characters.append(character)
                self.log_message(f"角色 {name} 添加成功", "info")
            else:
                self.log_message("角色添加失败: 名称为空", "warning")
                QMessageBox.warning(self, "警告", "角色名称不能为空！")
    
    def generate_character_with_ai(self, name_edit, background_edit):
        """使用AI生成角色信息"""
        self.log_message(">>> 进入generate_character_with_ai方法", "debug")
        from PyQt5.QtCore import QTimer
        
        # 获取用户输入的小说主题
        novel_theme = self.user_input.toPlainText().strip()
        self.log_message(f"检查用户输入的小说主题，长度: {len(novel_theme)} 字符", "debug")
        if not novel_theme:
            self.log_message("小说主题为空，准备显示警告", "debug")
            def show_warning():
                self.log_message("警告：请先输入小说主题内容！", "warning")
                QMessageBox.warning(self, "警告", "请先输入小说主题内容！")
            QTimer.singleShot(0, show_warning)
            self.log_message("<<< 因小说主题为空退出generate_character_with_ai方法", "debug")
            return
        
        self.log_message("小说主题检查通过", "debug")
        # 显示生成进度信息到AI角色输出窗口
        self.log_message("开始AI角色生成...")
        
        # 在新线程中生成内容
        def generate_in_thread():
            self.log_message("开始在工作线程中生成角色...", "debug")
            self.log_message(f"小说主题长度: {len(novel_theme)} 字符", "debug")
            try:
                # 使用ai_senior_writer1.generate_character_design替代ai_writer.generate_content
                self.log_message("调用AI生成角色设计...", "debug")
                ai_response = self.ai_senior_writer1.generate_character_design(novel_theme)
                self.log_message("<<< 退出generate_in_thread函数", "debug")
                self.log_message(f"工作线程中AI响应完成，长度: {len(ai_response) if ai_response else 0} 字符", "debug")
                self.log_message(f"AI响应前100字符: {ai_response[:100] if ai_response else 'None'}", "debug")
                self.log_message("准备处理AI响应结果...", "debug")
                
                # 检查AI响应是否为空或包含错误
                if not ai_response:
                    self.log_message("检查AI响应: 空响应", "debug")
                    error_msg = "AI生成角色失败：空响应"
                    self.log_message(error_msg, "error")
                    # 在主线程中显示错误
                    def show_error():
                        self.log_message("准备显示空响应错误对话框", "debug")
                        QMessageBox.critical(self, "错误", "AI生成角色失败：空响应")
                    QTimer.singleShot(0, show_error)
                elif "Error" in ai_response:
                    self.log_message("检查AI响应: 包含错误信息", "debug")
                    error_msg = f"AI生成角色失败：{ai_response}"
                    self.log_message(error_msg, "error")
                    # 在主线程中显示错误
                    def show_error():
                        self.log_message("准备显示错误信息对话框", "debug")
                        QMessageBox.critical(self, "错误", f"AI生成角色失败：{ai_response}")
                    QTimer.singleShot(0, show_error)
                else:
                    self.log_message("AI响应检查通过，准备在主线程中处理结果...", "debug")
                    # 将AI返回的完整内容输出到AI角色输出窗口中
                    def show_success():
                        self.log_message("在主线程中处理AI响应结果...", "debug")
                        self.role_output.append("[AI] " + ai_response)
                        self.log_message("AI生成角色成功，准备显示选择窗口...")
                        # 在主线程中处理结果并显示选择窗口
                        self.after_character_generation(ai_response, name_edit, background_edit)
                        self.log_message("after_character_generation方法调用完成", "debug")
                    
                    # 确保在主线程中执行show_success
                    from PyQt5.QtCore import Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "invoke_show_success", Qt.QueuedConnection, 
                                           Q_ARG(object, show_success))
                    self.log_message("已安排show_success任务", "debug")
            except Exception as e:
                self.log_message("<<< 异常退出generate_in_thread函数", "debug")
                error_msg = f"AI生成角色失败：{str(e)}"
                import traceback
                self.log_message(f"异常详情: {error_msg}", "error")
                self.log_message(f"异常堆栈: {traceback.format_exc()}", "error")
                # 在主线程中显示错误
                def show_error():
                    self.log_message("准备显示异常对话框", "debug")
                    QMessageBox.critical(self, "错误", f"AI生成角色失败：{str(e)}")
                QTimer.singleShot(0, show_error)
    
        @pyqtSlot(object)
        def invoke_show_success(self, show_success):
            """在主线程中执行show_success函数"""
            self.log_message("进入invoke_show_success方法", "debug")
            try:
                show_success()
                self.log_message("show_success函数执行完成", "debug")
            except Exception as e:
                self.log_message(f"执行show_success时发生错误: {str(e)}", "error")
                import traceback
                self.log_message(f"错误堆栈: {traceback.format_exc()}", "error")
            self.log_message("退出invoke_show_success方法", "debug")
    
    def generate_worldview(self):
        """使用AI生成世界观"""
        # 获取用户输入的小说内容要求
        user_prompt = self.user_input.toPlainText().strip()
        if not user_prompt:
            QMessageBox.warning(self, "警告", "请先输入小说内容要求！")
            return
        
        # 显示生成进度信息到AI角色输出窗口
        self.role_output.append("[系统] 开始生成世界观...")
        
        # 构造提示词
        prompt = f"""你是一位专业的小说世界观构建师，擅长创造各种类型的奇幻世界。请根据以下小说内容要求，构建一个完整的世界观设定：

小说内容要求：{user_prompt}

请提供以下内容的详细描述：
1. 世界名称和基本描述
2. 世界的地理分布描述
3. 世界的势力分布描述
4. 世界的修炼体系或能力体系描述

要求总字数不少于800字。请严格按照以下格式输出：
世界观设定
世界名称
[世界名称和基本描述]
地理分布
[世界的地理分布描述]
势力分布
[世界的势力分布描述]
修炼体系
[世界的修炼体系或能力体系描述]
"""
        
        # 在AI角色输出窗口显示提示词
        self.role_output.append(f"### 世界观生成提示词 ###\n{prompt}")
        
        # 在新线程中生成内容，避免阻塞UI
        def generate_in_thread():
            try:
                # 使用AI作家生成世界观
                worldview_content = self.ai_writer.generate_worldview(prompt)
                
                # 使用信号在主线程中执行UI更新
                self.worldview_generated.emit(worldview_content)
                
            except Exception as e:
                # 在主线程中显示错误
                def show_error():
                    error_msg = f"生成世界观时发生异常：{str(e)}"
                    self.role_output.append(f"[系统] {error_msg}")
                    QMessageBox.critical(self, "错误", error_msg)
                QTimer.singleShot(0, show_error)
        
        # 启动线程执行生成任务
        thread = threading.Thread(target=generate_in_thread)
        thread.daemon = True
        thread.start()

        self.role_output.append("[系统] 已启动世界观生成线程，请稍候...")
    
    @pyqtSlot(str)
    def update_ui_from_signal(self, worldview_content):
        """通过信号更新UI的槽函数"""
        try:
            # 在AI角色输出窗口显示AI生成的世界观内容
            self.role_output.append(f"### AI生成的世界观内容 ###\n{worldview_content}")
            
            # 检查是否有错误信息
            if "Error" in worldview_content:
                error_msg = f"AI生成世界观失败：{worldview_content}"
                self.role_output.append(f"[系统] {error_msg}")
                # 使用QTimer避免可能的递归问题
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, "错误", error_msg))
                return
            
            # 格式化世界观内容，按照指定格式【世界观：\nXXX】
            formatted_worldview = f"【世界观：\n{worldview_content}】"
            
            # 将生成的世界观内容添加到小说内容要求窗口中
            current_content = self.user_input.toPlainText()
            if current_content:
                # 如果当前有内容，添加两个换行符再添加新内容
                new_content = f"{current_content}\n\n{formatted_worldview}"
            else:
                # 如果当前无内容，直接添加新内容
                new_content = formatted_worldview
            
            # 更新小说内容要求窗口
            self.user_input.setPlainText(new_content)
            
            # 保存小说内容要求到文件
            try:
                with open("novel_requirements.txt", "w", encoding="utf-8") as f:
                    f.write(new_content)
                self.role_output.append("[系统] 世界观已生成并添加到小说内容要求窗口，同时保存到novel_requirements.txt文件中。")
            except Exception as e:
                self.role_output.append(f"[系统] 警告：保存小说内容要求失败：{str(e)}")
                
        except Exception as e:
            error_msg = f"更新UI时发生异常：{str(e)}"
            self.role_output.append(f"[系统] {error_msg}")
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "错误", error_msg))

            # 将生成的世界观内容添加到小说内容要求窗口中
            print("[调试] 准备将生成的世界观内容添加到小说内容要求窗口中")
            current_content = self.user_input.toPlainText()
            self.log_message(f"当前小说内容要求窗口内容长度: {len(current_content)} 字符", "debug")
            print(f"[调试] 当前小说内容要求窗口内容长度: {len(current_content)} 字符")
            if current_content:
                # 如果当前有内容，添加两个换行符再添加新内容
                new_content = f"{current_content}\n\n{formatted_worldview}"
            else:
                # 如果当前无内容，直接添加新内容
                new_content = formatted_worldview
            
            self.log_message(f"新内容长度: {len(new_content)} 字符", "debug")
            print(f"[调试] 新内容长度: {len(new_content)} 字符")
            # 更新小说内容要求窗口
            print("[调试] 准备更新小说内容要求窗口")
            self.user_input.setPlainText(new_content)
            print("[调试] 已更新小说内容要求窗口")
            self.log_message("已更新小说内容要求窗口", "debug")
            
            # 保存小说内容要求到文件
            print("[调试] 准备保存小说内容要求到文件")
            try:
                with open("novel_requirements.txt", "w", encoding="utf-8") as f:
                    f.write(new_content)
                self.log_message("小说内容要求已成功保存到novel_requirements.txt", "info")
                self.role_output.append("[系统] 世界观已生成并添加到小说内容要求窗口，同时保存到novel_requirements.txt文件中。")
                self.log_message("已添加完成提示信息到AI角色输出窗口", "debug")
                print("[调试] 已添加完成提示信息到AI角色输出窗口")
            except Exception as e:
                self.log_message(f"保存小说内容要求失败: {str(e)}", "error")
                self.role_output.append(f"[系统] 警告：保存小说内容要求失败：{str(e)}")
                self.log_message("已添加保存失败提示信息到AI角色输出窗口", "debug")
                print(f"[调试] 保存小说内容要求失败: {str(e)}")
                
        except Exception as e:
            print(f"[调试] update_ui_from_signal执行过程中发生异常: {e}")
            self.log_message(f"update_ui_from_signal执行过程中发生异常: {e}", "error")
            import traceback
            self.log_message(f"update_ui_from_signal异常堆栈: {traceback.format_exc()}", "error")

        def check_thread_status():
            for i in range(1, 11):  # 检查10次，每次间隔5秒
                time.sleep(5)
                print(f"[调试] 线程状态检查 {i}/10 - 是否存活: {thread.is_alive()}")
                self.log_message(f"线程状态检查 {i}/10 - 是否存活: {thread.is_alive()}", "debug")
                if not thread.is_alive():
                    print("[调试] 线程已结束运行")
                    self.log_message("线程已结束运行", "debug")
                    break
            print("[调试] 线程状态检查完成")
            self.log_message("线程状态检查完成", "debug")
        threading.Thread(target=check_thread_status, daemon=True).start()
        self.log_message("世界观生成线程已启动", "debug")

        self.role_output.append("[系统] 已启动世界观生成线程，请稍候...")
        self.log_message("已启动世界观生成线程", "debug")
    
    def parse_ai_character_response(self, response):
        """解析AI生成的角色响应"""
        import re
        
        characters = []
        
        # 使用正则表达式提取角色信息
        pattern = r'【角色设计\d+】\s*角色名称：(.*?)\s*角色背景：(.*?)(?=\s*【角色设计\d+】|\s*$)'
        matches = re.findall(pattern, response, re.DOTALL)
        
        for match in matches:
            name = match[0].strip()
            background = match[1].strip()
            
            # 确保名称和背景都不为空
            if name and background:
                characters.append({
                    'name': name,
                    'background': background
                })
        
        # 如果没有匹配到角色，尝试其他可能的格式
        if not characters:
            # 尝试匹配简单的"名称: 背景"格式
            simple_pattern = r'([^:\n]+):\s*(.*?)(?=\n[^:\n]+:|\s*$)'

            simple_matches = re.findall(simple_pattern, response, re.DOTALL)
            
            for match in simple_matches:
                name = match[0].strip()
                background = match[1].strip()
                
                # 确保名称和背景都不为空且不是太短
                if len(name) > 1 and len(background) > 10:
                    characters.append({
                        'name': name,
                        'background': background
                    })
        
        # 如果仍然没有匹配到角色，尝试按行解析
        if not characters:
            lines = response.strip().split('\n')
            current_character = {}
            for line in lines:
                if '角色名称：' in line:
                    name = line.split('角色名称：', 1)[1].strip()
                    current_character['name'] = name
                elif '角色背景：' in line:
                    background = line.split('角色背景：', 1)[1].strip()
                    current_character['background'] = background
                    
                    # 当我们有了名称和背景，就添加到角色列表中
                    if 'name' in current_character and 'background' in current_character:
                        characters.append({
                            'name': current_character['name'],
                            'background': current_character['background']
                        })
                        current_character = {}  # 重置为下一个角色做准备
        
        return characters

    def save_characters(self):
        """保存角色到文件"""
        try:
            # 准备保存的数据
            characters_data = []
            for character in self.characters:
                characters_data.append({
                    'name': character['name'],
                    'background': character['background']
                })
            
            # 保存到文件
            with open("角色.json", "w", encoding="utf-8") as f:
                json.dump(characters_data, f, ensure_ascii=False, indent=4)
            
            self.role_output.append("[系统] 角色信息已保存到 角色.json 文件！")
        except Exception as e:
            error_msg = f"保存角色信息失败：{str(e)}"
            self.role_output.append(f"[系统] {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)

    def load_characters(self):
        """从文件加载角色信息"""
        try:
            with open("角色.json", "r", encoding="utf-8") as f:
                characters_data = json.load(f)
                
            # 清空当前角色列表
            self.character_list.clear()
            self.characters = []
            
            # 添加角色到列表
            for character_data in characters_data:
                character = self.create_character_item(
                    character_data.get('name', ''), 
                    character_data.get('background', '')
                )
                self.characters.append(character)
                
        except FileNotFoundError:
            # 文件不存在，创建默认主角
            self.character_list.clear()
            self.characters = []
            # 添加默认主角
            character = self.create_character_item("主角", "小说的主人公，拥有独特的个人能力和复杂的社会关系")
            self.characters.append(character)
        except Exception as e:
            error_msg = f"加载角色信息失败：{str(e)}"
            self.role_output.append(f"[系统] {error_msg}")
            self.character_list.clear()
            self.characters = []

    # 添加导出小说的方法
    def export_novel(self):
        content = self.final_result.toPlainText()
        if not content:
            QMessageBox.warning(self, "警告", "没有可导出的小说内容！")
            return
            
        # 获取小说标题（使用用户输入作为文件名）
        novel_title = self.user_input.toPlainText().strip()[:20]  # 限制文件名长度
        if not novel_title:
            novel_title = "未命名小说"
            
        # 清理文件名中的非法字符
        import re
        novel_title = re.sub(r'[\\/:*?"<>|]', '_', novel_title)
        
        # 保存文件
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "导出小说", 
            f"{novel_title}.txt", 
            "文本文件 (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                QMessageBox.information(self, "成功", f"小说已成功导出到:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败：{str(e)}")

    def show_local_settings(self):
        """显示本地设置对话框"""
        dialog = LocalSettingsDialog(self)
        
        # Load current local settings
        try:
            with open("local_settings.json", "r", encoding="utf-8") as f:
                local_settings = json.load(f)
                dialog.set_settings(local_settings)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            pass

        if dialog.exec_() == QDialog.Accepted:
            # Save local settings
            local_settings = dialog.get_settings()
            try:
                with open("local_settings.json", "w", encoding="utf-8") as f:
                    json.dump(local_settings, f, ensure_ascii=False, indent=4)
                # 更新AI实例
                self.update_ai_instances()
                QMessageBox.information(self, "成功", "本地设置已保存！")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存设置失败：{str(e)}")

    def show_novel_settings(self):
        dialog = NovelSettingsDialog(self)
        # Load settings from novel_settings.json and apply to dialog
        try:
            with open("novel_settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
                dialog.chapter_count.setValue(settings.get("chapter_count", 30))
                dialog.words_per_chapter.setValue(settings.get("words_per_chapter", 1500))
                # 不再加载total_words，因为它现在是计算得出的
        except FileNotFoundError:
            # If file not found, use default values already set in dialog initialization
            pass
        except json.JSONDecodeError:
            # If JSON is invalid, use default values already set in dialog initialization
            pass
        
        if dialog.exec_() == QDialog.Accepted:
            # Save settings to novel_settings.json
            settings = dialog.get_settings()
            with open("novel_settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)

    def load_settings(self):
        """加载设置并初始化AI实例"""
        try:
            # Load settings from file
            with open("settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
            
            # Load local settings using the settings loader module
            local_settings = load_settings()
            use_local = local_settings.get("use_local", False)
            local_models = {
                "writer": local_settings.get("writer_local_model"),
                "reader": local_settings.get("reader_local_model"),
                "editor": local_settings.get("editor_local_model"),
                "senior_writer1": local_settings.get("senior_writer1_local_model"),
                "senior_writer2": local_settings.get("senior_writer2_local_model")
            }
            
            # Preload local models if needed
            model_manager = GlobalModelManager()
            if use_local:
                # 创建进度回调函数，用于在AI角色输出窗口中显示加载进度
                def create_progress_callback(role_name, model_path):
                    def progress_callback(message):
                        self.update_progress("系统", f"[{role_name}模型预加载] {message}")
                    return progress_callback
                
                unique_models = {}  # 用于存储模型路径和对应的角色名称
                for role, model_path in local_models.items():
                    if model_path and model_path not in unique_models:
                        unique_models[model_path] = role
                
                for model_path, role in unique_models.items():
                    # 为每个唯一模型路径启动预加载
                    progress_callback = create_progress_callback(role, model_path)
                    model_manager.load_model_async(model_path, progress_callback)
            
            # Initialize AI instances with settings
            self.ai_writer = AIWriter(
                api_key=settings.get("writer_key", ""), 
                model=settings.get("writer_model", "qwen-plus"),
                use_local=use_local,
                local_model_path=local_models.get("writer") if use_local else None
            )
            
            # 如果使用本地模型，更新模型实例
            if use_local and local_models.get("writer"):
                self.ai_writer.llm = model_manager.get_model(local_models.get("writer"))
            
            self.ai_reader = AIReader(
                api_key=settings.get("reader_key", ""), 
                model=settings.get("reader_model", "qwen-plus"),
                use_local=use_local,
                local_model_path=local_models.get("reader") if use_local else None
            )
            
            # 如果使用本地模型，更新模型实例
            if use_local and local_models.get("reader"):
                self.ai_reader.llm = model_manager.get_model(local_models.get("reader"))
            
            self.ai_editor = AIEditor(
                api_key=settings.get("editor_key", ""), 
                model=settings.get("editor_model", "qwen-plus"),
                use_local=use_local,
                local_model_path=local_models.get("editor") if use_local else None
            )
            
            # 如果使用本地模型，更新模型实例
            if use_local and local_models.get("editor"):
                self.ai_editor.llm = model_manager.get_model(local_models.get("editor"))
                
            # Initialize Senior Writer instances
            self.ai_senior_writer1 = AISeniorWriter(
                api_key=settings.get("senior_writer1_key", ""), 
                model=settings.get("senior_writer1_model", "qwen-plus"),
                use_local=use_local,
                local_model_path=local_models.get("senior_writer1") if use_local else None
            )
            
            # 如果使用本地模型，更新模型实例
            if use_local and local_models.get("senior_writer1"):
                self.ai_senior_writer1.llm = model_manager.get_model(local_models.get("senior_writer1"))
            
            self.ai_senior_writer2 = AISeniorWriter(
                api_key=settings.get("senior_writer2_key", ""), 
                model=settings.get("senior_writer2_model", "qwen-plus"),
                use_local=use_local,
                local_model_path=local_models.get("senior_writer2") if use_local else None
            )
            
            # 如果使用本地模型，更新模型实例
            if use_local and local_models.get("senior_writer2"):
                self.ai_senior_writer2.llm = model_manager.get_model(local_models.get("senior_writer2"))
                
            # 设置AISeniorWriter的主窗口引用
            self.ai_senior_writer1.set_main_window(self)
            self.ai_senior_writer2.set_main_window(self)
                
        except FileNotFoundError:
            QMessageBox.warning(self, "警告", "未找到配置文件，使用默认设置。")
        except json.JSONDecodeError:
            QMessageBox.warning(self, "警告", "配置文件格式错误，使用默认设置。")
        except Exception as e:
            QMessageBox.warning(self, "警告", f"加载设置时发生错误: {str(e)}")

    def show_settings(self):
        """显示参数设置对话框"""
        dialog = SettingsDialog(self)
        
        # Load current settings
        try:
            with open("settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
                dialog.temperature_spin.setValue(settings.get("temperature", 0.5))
                dialog.writer_key.setText(settings.get("writer_key", ""))
                dialog.reader_key.setText(settings.get("reader_key", ""))
                dialog.editor_key.setText(settings.get("editor_key", ""))
                dialog.writer_model.setText(settings.get("writer_model", "qwen-plus"))
                dialog.reader_model.setText(settings.get("reader_model", "qwen-plus"))
                dialog.editor_model.setText(settings.get("editor_model", "qwen-plus"))
                dialog.senior_writer1_key.setText(settings.get("senior_writer1_key", ""))
                dialog.senior_writer1_model.setText(settings.get("senior_writer1_model", "qwen-plus"))
                dialog.senior_writer2_key.setText(settings.get("senior_writer2_key", ""))
                dialog.senior_writer2_model.setText(settings.get("senior_writer2_model", "qwen-plus"))
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            pass

        if dialog.exec_() == QDialog.Accepted:
            # Save settings
            settings = dialog.get_settings()
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            
            # Reload AI instances
            self.load_settings()

    def generate_outline(self):
        # 获取用户输入
        user_prompt = self.user_input.toPlainText().strip()
        novel_type = self.novel_type.currentText()
        
        # 检查用户输入
        if not user_prompt:
            QMessageBox.warning(self, "警告", "请先输入小说内容要求！")
            return
        
        # 先检查是否有选中的章节（在加载大纲之前）
        selected_chapters = []
        # 创建一个临时列表保存当前选中章节的章节号
        selected_chapter_nums = []
        for chapter in self.novel_outline:
            if chapter.get('checkbox') and chapter['checkbox'].isChecked():
                selected_chapters.append(chapter)
                selected_chapter_nums.append(chapter['chapter_num'])
        
        # 如果有选中的章节，则只重新生成这些章节
        if selected_chapters:
            reply = QMessageBox.question(self, "确认", f"确定要重新生成选中的{len(selected_chapters)}个章节吗？", 
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.regenerate_selected_chapters(selected_chapters, user_prompt, novel_type)
            return
        
        # 加载小说大纲和已生成内容
        self.load_novel_outline()
        
        # 加载角色信息
        self.load_characters()
        
        # 重新检查是否有选中的章节（加载大纲后）
        selected_chapters = []
        for chapter in self.novel_outline:
            if chapter.get('checkbox') and chapter['checkbox'].isChecked():
                selected_chapters.append(chapter)
        
        # 如果有选中的章节，则只重新生成这些章节
        if selected_chapters:
            reply = QMessageBox.question(self, "确认", f"确定要重新生成选中的{len(selected_chapters)}个章节吗？", 
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.regenerate_selected_chapters(selected_chapters, user_prompt, novel_type)
            return
        
        # 加载小说设置
        try:
            with open("novel_settings.json", "r", encoding="utf-8") as f:
                novel_settings = json.load(f)
                chapter_count = novel_settings.get("chapter_count", 30)
        except FileNotFoundError:
            chapter_count = 30
        except json.JSONDecodeError:
            QMessageBox.warning(self, "警告", "小说参数配置文件格式错误！")
            return

        # 清空大纲列表（如果没有选中的章节需要重新生成）
        self.outline_list.clear()
        self.novel_outline = []
        
        # 确定起始章节号
        start_chapter = 1
        if hasattr(self, 'novel_outline') and self.novel_outline:
            # 如果大纲列表不为空，找到最大的章节号并加1
            max_chapter = max([chapter['chapter_num'] for chapter in self.novel_outline])
            # 检查最后一章是否已有内容
            last_chapter = next((chapter for chapter in self.novel_outline if chapter['chapter_num'] == max_chapter), None)
            if last_chapter and last_chapter.get('content') and last_chapter['content'].strip():
                # 如果最后一章已有内容，则从下一章开始
                start_chapter = max_chapter + 1
            else:
                # 如果最后一章没有内容，则从最后一章开始（重新生成）
                start_chapter = max_chapter
                # 清空最后一章的内容
                if last_chapter:
                    last_chapter['content'] = ""
                    # 从大纲列表中移除最后一章（如果它在UI中）
                    for i in range(self.outline_list.count()):
                        item = self.outline_list.item(i)
                        item_data = self.outline_list.itemWidget(item).findChild(QCheckBox).parent().chapter_data
                        if item_data['chapter_num'] == max_chapter:
                            self.outline_list.takeItem(i)
                            break
                self.novel_outline = [chapter for chapter in self.novel_outline if chapter['chapter_num'] < start_chapter]

        # 清理之前的线程和worker（如果存在）
        if hasattr(self, 'outline_thread') and self.outline_thread:
            try:
                if self.outline_thread.isRunning():
                    self.outline_thread.quit()
                    self.outline_thread.wait()
            except RuntimeError:
                # 如果线程对象已被删除，忽略异常
                pass
        
        try:
            # 创建大纲生成线程和worker
            self.outline_thread = QThread()
            self.outline_worker = OutlineWorker(
                self.ai_senior_writer1,
                self.ai_senior_writer2,
                start_chapter,
                chapter_count,
                user_prompt,
                self.novel_outline,
                None,  # 没有选中的章节
                self.characters  # 传递角色信息
            )
            # 传递角色信息给worker
            self.outline_worker.characters = self.characters
            
            self.outline_worker.moveToThread(self.outline_thread)
            
            # 连接信号
            self.outline_thread.started.connect(self.outline_worker.run)
            self.outline_worker.outline_generated.connect(self.update_outline)
            self.outline_worker.chapter_outline_generated.connect(self.add_outline_item_single)  # 连接单章大纲生成信号
            self.outline_worker.error.connect(self.handle_outline_error)
            self.outline_worker.progress.connect(self.update_progress)  # 连接进度信号
            self.outline_worker.finished.connect(self.outline_thread.quit)
            self.outline_worker.finished.connect(self.outline_worker.deleteLater)
            self.outline_thread.finished.connect(self.outline_thread.deleteLater)
            
            # 启动线程
            self.generate_btn.setEnabled(False)
            self.generate_btn.setText("生成中...")
            self.stop_outline_btn.setEnabled(True)  # 启用中断按钮
            self.outline_thread.start()
        except Exception as e:
            # 如果创建线程或启动过程中出现异常，恢复按钮状态
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("生成大纲")
            self.stop_outline_btn.setEnabled(False)  # 禁用中断按钮
            QMessageBox.critical(self, "错误", f"启动大纲生成时出错：{str(e)}")

    def get_selected_chapters(self):
        """获取选中的章节列表"""
        selected_chapters = []
        for chapter in self.novel_outline:
            if chapter.get('checkbox') and chapter['checkbox'].isChecked():
                selected_chapters.append(chapter)
        return selected_chapters

    def stop_chapter_generation(self):
        """中断章节生成"""
        # 确认是否要中断生成
        reply = QMessageBox.question(self, "确认中断", "确定要中断当前的生成过程吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 设置worker的running标志为False以中断生成过程
            if hasattr(self, 'chapter_queue_worker') and self.chapter_queue_worker:
                try:
                    self.chapter_queue_worker.running = False
                except RuntimeError:
                    # 如果worker对象已被删除，忽略异常
                    pass
            
            # 更新UI状态
            self.stop_generation_btn.setEnabled(False)
            self.generate_chapter_btn.setEnabled(True)
            self.generate_chapter_btn.setText("开始生成")
            
            # 显示中断信息
            self.role_output.append("[系统] 章节生成已中断")

    def regenerate_selected_chapters(self, selected_chapters, user_prompt, novel_type):
        """重新生成选中的章节"""
        # 获取小说设置
        try:
            with open("novel_settings.json", "r", encoding="utf-8") as f:
                novel_settings = json.load(f)
                words_per_chapter = novel_settings.get("words_per_chapter", 1500)
        except FileNotFoundError:
            words_per_chapter = 1500
        except json.JSONDecodeError:
            words_per_chapter = 1500
        
        # 清理之前的线程和worker（如果存在）
        if hasattr(self, 'outline_thread') and self.outline_thread:
            try:
                if self.outline_thread.isRunning():
                    self.outline_thread.quit()
                    self.outline_thread.wait()
            except RuntimeError:
                # 如果线程对象已被删除，忽略异常
                pass
        
        try:
            # 提取选中的章节号列表
            selected_chapter_nums = [chapter['chapter_num'] for chapter in selected_chapters]
            
            # 创建大纲重新生成线程和worker
            self.outline_thread = QThread()
            self.outline_worker = OutlineWorker(
                self.ai_senior_writer1,
                self.ai_senior_writer2,
                1,  # start_chapter参数在这里不使用，但需要传递
                len(selected_chapter_nums),  # 只传递选中章节的数量
                user_prompt,
                self.novel_outline,
                selected_chapters,  # 修复：直接传递原始selected_chapters而不是selected_chapter_nums
                self.characters  # 传递角色信息
            )
            # 将完整大纲传递给worker，用于情节连贯性检查
            self.outline_worker.full_outline = self.novel_outline
            
            self.outline_worker.moveToThread(self.outline_thread)
            
            # 连接信号
            self.outline_thread.started.connect(self.outline_worker.run)
            # 使用新的信号处理选中章节的重新生成
            self.outline_worker.chapter_outline_generated.connect(self.update_outline_item_single)
            self.outline_worker.error.connect(self.handle_outline_error)
            self.outline_worker.progress.connect(self.update_progress)  # 连接进度信号
            self.outline_worker.finished.connect(self.finish_selected_chapters_regeneration)
            self.outline_worker.finished.connect(self.outline_thread.quit)
            self.outline_worker.finished.connect(self.outline_worker.deleteLater)
            self.outline_thread.finished.connect(self.outline_thread.deleteLater)
            
            # 启动线程
            self.generate_btn.setEnabled(False)
            self.generate_btn.setText("生成中...")
            self.stop_outline_btn.setEnabled(True)  # 启用中断按钮
            self.outline_thread.start()
        except Exception as e:
            # 如果创建线程或启动过程中出现异常，恢复按钮状态
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("生成大纲")
            self.stop_outline_btn.setEnabled(False)  # 禁用中断按钮
            QMessageBox.critical(self, "错误", f"启动章节重新生成时出错：{str(e)}")
    
    def add_outline_item_single(self, chapter_num, title, summary):
        """添加单个大纲项到UI列表中"""
        # 创建包含复选框的自定义项
        item = QListWidgetItem()
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 左侧：复选框
        checkbox = QCheckBox()
        
        # 右侧：上下结构
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        # 设置章节标题与梗概之间无间隔
        right_layout.setSpacing(0)
        
        # 上部分：章节标题（可编辑）
        title_edit = QLineEdit(f"第{chapter_num}章 {title}")
        title_edit.setPlaceholderText(f"第{chapter_num}章 标题")
        
        # 下部分：章节梗概（可编辑）
        summary_edit = QTextEdit(summary)
        summary_edit.setPlaceholderText("章节梗概")
        summary_edit.setMaximumHeight(60)  # 限制高度
        summary_edit.setWordWrapMode(True)
        
        right_layout.addWidget(title_edit)
        right_layout.addWidget(summary_edit)
        
        layout.addWidget(checkbox)
        layout.addWidget(right_widget)
        
        widget.setLayout(layout)
        
        # 设置项的高度
        item.setSizeHint(widget.sizeHint())
        
        # 添加到列表
        self.outline_list.addItem(item)
        self.outline_list.setItemWidget(item, widget)
        
        # 保存章节信息
        chapter = {
            'chapter_num': chapter_num,
            'title': title,
            'summary': summary,
            'content': "",  # 新增 content 字段
            'item': item,
            'checkbox': checkbox,
            'title_edit': title_edit,
            'summary_edit': summary_edit
        }
        self.novel_outline.append(chapter)
        
        # 保存大纲到文件
        self.save_novel_outline()

    def update_outline(self, outline_content, expected_chapter_count, characters=None):
        """更新小说大纲显示"""
        try:
            # 在AI角色输出窗口中显示AI返回的原始大纲内容
            self.role_output.append("[系统] AI生成的大纲原始内容:")
            self.role_output.append(outline_content)
            self.role_output.append("[系统] 开始解析大纲内容...")
            
            # 清空现有大纲
            self.outline_list.clear()
            self.novel_outline = []
            
            # 解析大纲内容
            chapters = extract_chapters_from_outline(outline_content)
            
            # 在AI角色输出窗口中显示解析结果
            self.role_output.append(f"[系统] 解析完成，共找到 {len(chapters)} 个章节")
            for chapter in chapters:
                self.role_output.append(f"[系统] 第{chapter['chapter_num']}章: {chapter['title']}")
            
            # 如果解析出的章节数与预期不符，给出警告
            if len(chapters) < expected_chapter_count:
                warning_msg = f"生成的大纲章节数({len(chapters)})少于预期({expected_chapter_count})，系统将尝试补充缺失的章节。"
                self.role_output.append(f"[系统] 警告: {warning_msg}")
                
                # 补充缺失的章节
                missing_count = expected_chapter_count - len(chapters)
                for i in range(missing_count):
                    chapter_num = len(chapters) + i + 1
                    self.add_outline_item(chapter_num, "待定章节", "暂无内容梗概")
                    self.role_output.append(f"[系统] 补充第{chapter_num}章")
            
            # 添加解析出的章节到大纲列表
            for chapter in chapters:
                self.add_outline_item(chapter['chapter_num'], chapter['title'], chapter['summary'])
            
            # 保存大纲到文件
            self.save_novel_outline()
            
            # 如果有角色信息，更新角色列表
            if characters is not None and len(characters) > 0:
                # 保存当前的角色信息
                self.characters = []
                for character in characters:
                    # 创建角色项
                    character_item = self.create_character_item(
                        character.get('name', ''), 
                        character.get('background', '')
                    )
                    self.characters.append(character_item)
                
                # 保存角色到文件
                self.save_characters()
            
            # 重新加载角色列表（可能有新角色添加）
            self.load_characters()
            
        except Exception as e:
            error_msg = f"解析大纲内容时发生错误：{str(e)}"
            self.role_output.append(f"[系统] 错误: {error_msg}")
            self.error.emit(error_msg)

    def handle_outline_error(self, error_msg):
        """处理大纲生成错误"""
        # 显示错误信息
        self.role_output.append(f"[系统] 大纲生成出错：{error_msg}")
        # 恢复按钮状态
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("生成大纲")
        self.stop_outline_btn.setEnabled(False)  # 禁用中断按钮


    def on_outline_item_changed(self, item):
        """当大纲项发生变化时更新全选状态"""
        self.update_select_all_state()


    def start_chapter_generation(self):
        """开始生成章节"""
        # 获取用户输入的小说内容要求
        user_prompt = self.user_input.toPlainText().strip()
        if not user_prompt:
            QMessageBox.warning(self, "警告", "请输入小说内容要求！")
            return
        
        # 获取小说设置
        try:
            with open("novel_settings.json", "r", encoding="utf-8") as f:
                novel_settings = json.load(f)
        except FileNotFoundError:
            QMessageBox.warning(self, "警告", "请先设置小说参数！")
            return
        except json.JSONDecodeError:
            QMessageBox.warning(self, "警告", "小说参数配置文件格式错误！")
            return
        
        if not novel_settings:
            QMessageBox.warning(self, "警告", "请先设置小说参数！")
            return
        
        # 获取选中的章节
        selected_chapters = self.get_outline_selected_chapters()
        if not selected_chapters:
            QMessageBox.warning(self, "警告", "请选择要生成的章节！")
            return
        
        # 创建ChapterQueueWorker实例
        self.chapter_queue_worker = ChapterQueueWorker(
            self.ai_writer, 
            self.ai_reader, 
            self.ai_editor, 
            selected_chapters, 
            user_prompt, 
            novel_settings.get("chapter_count", 30), 
            novel_settings.get("words_per_chapter", 1500), 
            self.novel_outline
        )
        
        # 创建线程并移动worker到线程中
        self.chapter_thread = QThread()
        self.chapter_queue_worker.moveToThread(self.chapter_thread)
        
        # 连接信号与槽
        self.chapter_thread.started.connect(self.chapter_queue_worker.run)
        self.chapter_queue_worker.chapter_generated.connect(self.on_chapter_generated)
        self.chapter_queue_worker.progress.connect(self.update_progress)
        self.chapter_queue_worker.error.connect(self.show_error)
        self.chapter_queue_worker.finished.connect(self.generation_finished)
        self.chapter_queue_worker.finished.connect(self.chapter_thread.quit)
        self.chapter_queue_worker.finished.connect(self.chapter_queue_worker.deleteLater)
        self.chapter_thread.finished.connect(self.chapter_thread.deleteLater)
        
        # 禁用生成按钮，启用停止按钮
        self.generate_chapter_btn.setEnabled(False)
        self.generate_chapter_btn.setText("生成中...")
        self.stop_generation_btn.setEnabled(True)
        
        # 开始生成
        self.chapter_thread.start()

    def stop_chapter_generation(self):
        """中断章节生成"""
        # 确认是否要中断生成
        reply = QMessageBox.question(self, "确认中断", "确定要中断当前的生成过程吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 设置worker的running标志为False以中断生成过程
            if hasattr(self, 'chapter_queue_worker') and self.chapter_queue_worker:
                try:
                    self.chapter_queue_worker.running = False
                except RuntimeError:
                    # 如果worker对象已被删除，忽略异常
                    pass
            
            # 使用临时变量保存对当前线程和worker的引用
            # 这样可以让线程自然结束，避免"QThread: Destroyed while thread is still running"错误
            old_thread = None
            old_worker = None
            
            if hasattr(self, 'chapter_thread') and self.chapter_thread:
                old_thread = self.chapter_thread
                self.chapter_thread = None  # 立即清除引用，防止其他地方误操作
            
            if hasattr(self, 'chapter_queue_worker') and self.chapter_queue_worker:
                old_worker = self.chapter_queue_worker
                self.chapter_queue_worker = None  # 立即清除引用，防止其他地方误操作
            
            # 更新UI状态
            self.stop_generation_btn.setEnabled(False)
            self.generate_chapter_btn.setEnabled(True)
            self.generate_chapter_btn.setText("开始生成")
            
            # 显示中断信息
            self.role_output.append("[系统] 章节生成已中断")
            
            # 注意：我们不主动终止线程，而是让其自然结束
            # old_thread和old_worker会在线程结束后被自动清理
    def generation_finished(self):
        """
        章节生成完成处理
        """
        # 安全地停止和清理线程
        if hasattr(self, 'chapter_thread') and self.chapter_thread:
            try:
                if self.chapter_thread.isRunning():
                    self.chapter_thread.quit()
                    # 等待线程结束，但不要无限期等待
                    self.chapter_thread.wait(3000)  # 最多等待3秒
            except RuntimeError:
                # 如果线程对象已被删除，忽略异常
                pass
        
        # 彻底清理线程和worker对象
        try:
            # 断开所有信号连接
            if hasattr(self, 'chapter_queue_worker') and self.chapter_queue_worker:
                try:
                    self.chapter_queue_worker.chapter_generated.disconnect()
                    self.chapter_queue_worker.progress.disconnect()
                    self.chapter_queue_worker.error.disconnect()
                    self.chapter_queue_worker.finished.disconnect()
                except:
                    pass
                self.chapter_queue_worker = None
            
            if hasattr(self, 'chapter_thread') and self.chapter_thread:
                try:
                    self.chapter_thread.started.disconnect()
                    self.chapter_thread.finished.disconnect()
                except:
                    pass
                
                # 设置为None，确保被垃圾回收
                self.chapter_thread = None
        except:
            # 发生任何异常都清除引用
            self.chapter_queue_worker = None
            self.chapter_thread = None
        
        self.generate_chapter_btn.setEnabled(True)
        self.generate_chapter_btn.setText("开始生成")
        self.stop_generation_btn.setEnabled(False)  # 禁用中断按钮
        
        # 确保UI更新
        self.final_result.update()
        
        # 在AI角色输出窗口中显示系统提示，替代弹窗
        self.role_output.append("[系统] 选中的章节已生成完成！")

    def stop_outline_generation(self):
        """中断大纲生成"""
        # 确认是否要中断生成
        reply = QMessageBox.question(self, "确认中断", "确定要中断当前的大纲生成过程吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 设置worker的running标志为False以中断生成过程
            if hasattr(self, 'outline_worker') and self.outline_worker:
                try:
                    self.outline_worker.running = False
                except RuntimeError:
                    # 如果worker对象已被删除，忽略异常
                    pass
            
            # 更新UI状态
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("生成大纲")
            self.stop_outline_btn.setEnabled(False)  # 禁用中断按钮
            
            # 显示中断信息
            self.role_output.append("[系统] 大纲生成已中断")

    def update_chapter_content_from_queue(self, chapter_num, chapter_title, content):
        """
        从队列中更新章节内容
        """
        # 清理章节内容，移除AI生成的标记性内容，但保留换行符和必要空格
        cleaned_content = content
        # 移除常见的AI标记内容
        import re
        # 移除以【】包围的标记内容
        cleaned_content = re.sub(r'【.*?】', '', cleaned_content)
        # 移除以[]包围的标记内容（英文方括号）
        cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
        # 清理过多的连续空白行，但保留单个换行符
        cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
        # 去除首尾空白字符
        cleaned_content = cleaned_content.strip()
        
        # 查找该章节在大纲中的信息
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break
    
        # 优化章节标题显示逻辑，避免重复显示"第X章"前缀
        if chapter_title.startswith(f"第{chapter_num}章"):
            # 如果chapter_title已经包含"第X章"前缀，则直接使用
            display_title = chapter_title
        elif chapter_outline:
            # 如果没有前缀但有大纲信息，则添加前缀
            display_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            # 如果既没有前缀也没有大纲信息，则使用默认格式
            display_title = f"第{chapter_num}章 {chapter_title}"
        
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{display_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, display_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 更新大纲列表相应章节的信息
        # 根据要求，只更新content字段，不更新章节标题和梗概
        if chapter_outline:
            # 保存章节内容到大纲数据结构中（只更新content字段）
            chapter_outline['content'] = cleaned_content
    
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()

    def on_chapter_generated(self, chapter_num, chapter_title, content):
        """
        处理章节生成完成事件
        """
        # 清理章节内容，移除AI生成的标记性内容
        cleaned_content = content
        # 移除常见的AI标记内容
        import re
        # 移除以【】包围的标记内容
        cleaned_content = re.sub(r'【.*?】', '', cleaned_content)
        # 移除以[]包围的标记内容（英文方括号）
        cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
        # 清理多余的空白行
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content).strip()
        
        # 查找该章节在大纲中的信息
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break
    
        # 优化章节标题显示逻辑，避免重复显示"第X章"前缀
        if chapter_title.startswith(f"第{chapter_num}章"):
            # 如果chapter_title已经包含"第X章"前缀，则直接使用
            display_title = chapter_title
        elif chapter_outline:
            # 如果没有前缀但有大纲信息，则添加前缀
            display_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            # 如果既没有前缀也没有大纲信息，则使用默认格式
            display_title = f"第{chapter_num}章 {chapter_title}"
        
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{display_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, display_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 更新大纲列表相应章节的信息
        if chapter_outline:
            # 更新大纲列表中该章节的标题（如果需要）
            title_edit = chapter_outline.get('title_edit')
            
            if title_edit:
                # 只更新章节标题部分，不包含"第X章"前缀
                if display_title.startswith(f"第{chapter_num}章 "):
                    title_edit.setText(display_title[len(f"第{chapter_num}章 "):])
                else:
                    title_edit.setText(display_title)
                
            # 保存章节内容到大纲数据结构中（正确保存到content字段）
            chapter_outline['content'] = cleaned_content
    
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()

    def on_chapter_generated(self, chapter_num, chapter_title, content):
        """
        处理章节生成完成事件
        """
        # 清理章节内容，移除AI生成的标记性内容
        cleaned_content = content
        # 移除常见的AI标记内容
        import re
        # 移除以【】包围的标记内容
        cleaned_content = re.sub(r'【.*?】', '', cleaned_content)
        # 移除以[]包围的标记内容（英文方括号）
        cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
        # 清理多余的空白行
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content).strip()
        
        # 查找该章节在大纲中的信息
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break
    
        # 优化章节标题显示逻辑，避免重复显示"第X章"前缀
        if chapter_title.startswith(f"第{chapter_num}章"):
            # 如果chapter_title已经包含"第X章"前缀，则直接使用
            display_title = chapter_title
        elif chapter_outline:
            # 如果没有前缀但有大纲信息，则添加前缀
            display_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            # 如果既没有前缀也没有大纲信息，则使用默认格式
            display_title = f"第{chapter_num}章 {chapter_title}"
        
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{display_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, display_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 更新大纲列表相应章节的信息
        # 根据要求，只更新content字段，不更新章节标题和梗概
        if chapter_outline:
            # 保存章节内容到大纲数据结构中（只更新content字段）
            chapter_outline['content'] = cleaned_content
    
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()

    def update_chapter_content_from_queue(self, chapter_num, chapter_title, content):
        """
        从队列中更新章节内容
        """
        # 清理章节内容，移除AI生成的标记性内容
        cleaned_content = content
        # 移除常见的AI标记内容
        import re
        # 移除以【】包围的标记内容
        cleaned_content = re.sub(r'【.*?】', '', cleaned_content)
        # 移除以[]包围的标记内容（英文方括号）
        cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
        # 只清理过多的空白行，但保留原有的换行符结构
        # 将3个或以上的连续空行替换为2个空行，保留正常的段落间距
        cleaned_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_content)
        # 只去除首尾空白，但保留内容中的换行符
        cleaned_content = cleaned_content.strip()
        
        # 查找该章节在大纲中的信息
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break
    
        # 优化章节标题显示逻辑，避免重复显示"第X章"前缀
        if chapter_title.startswith(f"第{chapter_num}章"):
            # 如果chapter_title已经包含"第X章"前缀，则直接使用
            display_title = chapter_title
        elif chapter_outline:
            # 如果没有前缀但有大纲信息，则添加前缀
            display_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            # 如果既没有前缀也没有大纲信息，则使用默认格式
            display_title = f"第{chapter_num}章 {chapter_title}"
        
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{display_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, display_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 更新大纲列表相应章节的信息
        # 根据要求，只更新content字段，不更新章节标题和梗概
        if chapter_outline:
            # 保存章节内容到大纲数据结构中（只更新content字段）
            chapter_outline['content'] = cleaned_content
    
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()

        cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
        # 清理多余的空白行
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content).strip()
        
        # 查找该章节在大纲中的信息
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break
    
        # 优化章节标题显示逻辑，避免重复显示"第X章"前缀
        if chapter_title.startswith(f"第{chapter_num}章"):
            # 如果chapter_title已经包含"第X章"前缀，则直接使用
            display_title = chapter_title
        elif chapter_outline:
            # 如果没有前缀但有大纲信息，则添加前缀
            display_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            # 如果既没有前缀也没有大纲信息，则使用默认格式
            display_title = f"第{chapter_num}章 {chapter_title}"
        
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{display_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, display_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 更新大纲列表相应章节的信息
        # 根据要求，只更新content字段，不更新章节标题和梗概
        if chapter_outline:
            # 保存章节内容到大纲数据结构中（只更新content字段）
            chapter_outline['content'] = cleaned_content
    
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()

        import re
        # 移除以【】包围的标记内容
        cleaned_content = re.sub(r'【.*?】', '', cleaned_content)
        # 移除以[]包围的标记内容（英文方括号）
        cleaned_content = re.sub(r'\[.*?\]', '', cleaned_content)
        # 清理多余的空白行
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content).strip()
        
        # 查找该章节在大纲中的信息
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break
    
        # 优化章节标题显示逻辑，避免重复显示"第X章"前缀
        if chapter_title.startswith(f"第{chapter_num}章"):
            # 如果chapter_title已经包含"第X章"前缀，则直接使用
            display_title = chapter_title
        elif chapter_outline:
            # 如果没有前缀但有大纲信息，则添加前缀
            display_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            # 如果既没有前缀也没有大纲信息，则使用默认格式
            display_title = f"第{chapter_num}章 {chapter_title}"
        
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{display_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, display_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 更新大纲列表相应章节的信息
        if chapter_outline:
            # 更新大纲列表中该章节的标题（如果需要）
            title_edit = chapter_outline.get('title_edit')
            
            if title_edit:
                # 只更新章节标题部分，不包含"第X章"前缀
                if display_title.startswith(f"第{chapter_num}章 "):
                    title_edit.setText(display_title[len(f"第{chapter_num}章 "):])
                else:
                    title_edit.setText(display_title)
                
            # 保存章节内容到大纲数据结构中（正确保存到content字段）
            chapter_outline['content'] = cleaned_content
    
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()


    def get_outline_selected_chapters(self):
        """获取大纲中选中的章节列表"""
        selected_chapters = []
        for chapter in self.novel_outline:
            if chapter.get('checkbox') and chapter['checkbox'].isChecked():
                selected_chapters.append(chapter)
        return selected_chapters

    def update_chapter_item(self, chapter_num, display_title, cleaned_content):
        """更新章节项"""
        chapter_outline = None
        for outline in self.novel_outline:
            if outline['chapter_num'] == chapter_num:
                chapter_outline = outline
                break

        if chapter_outline:
            chapter_title = f"第{chapter_num}章 {chapter_outline['title']}"
        else:
            chapter_title = f"第{chapter_num}章"
    
        # 计算字数
        char_count = len(cleaned_content.strip()) if cleaned_content else 0
        chapter_title_with_count = f"{chapter_title}（本章正文共{char_count}字）"
        
        # 检查是否已经存在该章节项
        if chapter_num in self.chapter_items_map:
            # 更新现有项
            chapter_item = self.chapter_items_map[chapter_num]
            chapter_item['title_label'].setText(chapter_title_with_count)
            chapter_item['content_text'].setPlainText(cleaned_content)
        else:
            # 添加新项
            chapter_item = self.add_chapter_item(chapter_num, chapter_title, cleaned_content)
            self.chapter_items_map[chapter_num] = chapter_item
        
        # 将内容关联到大纲列表中的相应章节，不更新标题
        if chapter_outline:
            # 保存章节内容到大纲数据结构中（正确保存到content字段）
            chapter_outline['content'] = cleaned_content
        # 强制更新UI
        self.final_result.repaint()
        self.final_result.scrollToBottom()
        
        # 自动保存小说大纲
        self.save_novel_outline()


    def get_outline_selected_chapters(self):
        """获取大纲中选中的章节列表"""
        selected_chapters = []
        for chapter in self.novel_outline:
            if chapter.get('checkbox') and chapter['checkbox'].isChecked():
                selected_chapters.append(chapter)
        return selected_chapters

    def get_selected_chapters(self):
        """
        获取最终结果中选中的章节列表
        """
        selected_chapters = []
        for item in self.final_result.selectedItems():
            item_data = item.data(Qt.UserRole)
            if item_data:
                selected_chapters.append(item_data['chapter_num'])
        return selected_chapters

    def on_stop_chapter_generation(self):
        """
        中断章节生成
        """
        reply = QMessageBox.question(self, "确认中断", "确定要中断当前的章节生成过程吗？", 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 设置worker的running标志为False以中断生成过程
            if hasattr(self, 'chapter_queue_worker') and self.chapter_queue_worker:
                try:
                    self.chapter_queue_worker.running = False
                except RuntimeError:
                    # 如果worker对象已被删除，忽略异常
                    pass
            
            # 更新UI状态
            self.generate_chapter_btn.setEnabled(True)
            self.generate_chapter_btn.setText("开始生成")
            self.stop_generation_btn.setEnabled(False)  # 禁用中断按钮
            
            # 显示中断信息
            self.role_output.append("[系统] 章节生成已中断")

    def finish_chapter_generation_queue(self):
        """
        完成章节生成队列
        """
        print(f"=== 章节生成队列完成 ===")
        print(f"最终结果列表项数: {self.final_result.count()}")
        for i in range(self.final_result.count()):
            item = self.final_result.item(i)
            item_data = item.data(Qt.UserRole)
            chapter_num = item_data.get('chapter_num') if item_data else 'N/A'
            print(f"  项 {i}: 章节号: {chapter_num}, 文本: {item.text()[:50]}..." if len(item.text()) > 50 else f"  项 {i}: 章节号: {chapter_num}, 文本: {item.text()}")
        print("=== 结束 ===")
        
        self.generate_chapter_btn.setEnabled(True)
        self.generate_chapter_btn.setText("开始生成")
        self.stop_generation_btn.setEnabled(False)  # 禁用中断按钮
        
        # 清除worker引用，避免在中断后再次触发信号
        self.chapter_queue_worker = None
        
        # 确保UI更新
        self.final_result.update()
        
        # 在AI角色输出窗口中显示系统提示，替代弹窗
        self.role_output.append("[系统] 选中的章节已生成完成！")

    def generation_finished(self):
        """
        章节生成完成处理
        """
        # 更新UI状态
        self.generate_chapter_btn.setEnabled(True)
        self.generate_chapter_btn.setText("开始生成")
        self.stop_generation_btn.setEnabled(False)  # 禁用中断按钮
        
        # 确保UI更新
        self.final_result.update()
        
        # 在AI角色输出窗口中显示系统提示，替代弹窗
        self.role_output.append("[系统] 选中的章节已生成完成！")
        
        # 注意：线程和worker对象会通过信号槽机制自动清理
        # self.chapter_queue_worker.finished.connect(self.chapter_thread.quit)
        # self.chapter_queue_worker.finished.connect(self.chapter_queue_worker.deleteLater)
        # self.chapter_thread.finished.connect(self.chapter_thread.deleteLater)
        # 所以我们不需要手动清理线程和worker对象

    def stop_outline_generation(self):
        """
        中断大纲生成
        """
        self.stop_generation_btn.setEnabled(False)  # 禁用中断按钮
        
        # 清除worker引用，避免在中断后再次触发信号
        self.chapter_queue_worker = None
        
        # 确保UI更新
        self.final_result.update()
        
        # 在AI角色输出窗口中显示系统提示，替代弹窗
        self.role_output.append("[系统] 选中的章节已生成完成！")

    def get_outline_selected_chapters(self):
        """获取大纲中选中的章节列表"""
        selected_chapters = []
        for chapter in self.novel_outline:
            if chapter.get('checkbox') and chapter['checkbox'].isChecked():
                selected_chapters.append(chapter)
        return selected_chapters

    def log_message(self, message, msg_type="info"):
        """
        公共日志输出方法
        :param message: 要输出的消息
        :param msg_type: 消息类型 (info, debug, warning, error)
        """
        from PyQt5.QtCore import QTimer
        prefix = {
            "info": "[系统]",
            "debug": "[调试]",
            "warning": "[警告]",
            "error": "[错误]"
        }.get(msg_type, "[系统]")
        
        formatted_message = f"{prefix} {message}"
        QTimer.singleShot(0, lambda: self.role_output.append(formatted_message))
    
    def update_progress(self, role, content):
        """更新AI角色输出窗口"""
        # 在AI角色输出窗口中显示信息
        self.log_message(f"{content}", "info")
        # 使用 QTimer 来处理滚动操作，确保在主线程中执行
        from PyQt5.QtCore import QTimer
        def scroll_to_end():
            cursor = self.role_output.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.role_output.setTextCursor(cursor)
        QTimer.singleShot(0, scroll_to_end)

    @pyqtSlot(object)
    def invoke_show_success(self, func):
        """在主线程中执行传入的函数"""
        print(">>> PRINT: 进入invoke_show_success方法")  # 使用print确保输出
        try:
            func()
            print(">>> PRINT: 退出invoke_show_success方法")  # 使用print确保输出
        except Exception as e:
            print(f"Error in invoke_show_success: {str(e)}")
            import traceback
            traceback.print_exc()
        
    def load_novel_outline(self):
        """加载小说大纲"""
        try:
            # 加载小说内容要求
            with open("小说内容要求.txt", "r", encoding="utf-8") as f:
                content = f.read()
                self.user_input.setPlainText(content)
        except FileNotFoundError:
            pass  # 文件不存在就不加载
        except Exception as e:
            print(f"加载小说内容要求时出错: {e}")
        
        # 加载小说大纲
        try:
            import json
            import os
            
            # 检查文件是否存在
            if not os.path.exists("小说大纲.json"):
                return  # 文件不存在，直接返回
            
            # 读取文件内容并打印，便于调试
            with open("小说大纲.json", "r", encoding="utf-8") as f:
                file_content = f.read()
                print(f"=== 小说大纲.json 内容 ===\n{file_content}\n=== 结束 ===")
                
                # 检查文件是否为空
                if not file_content.strip():
                    print("小说大纲.json 文件为空")
                    return
                
                # 尝试解析 JSON
                outline_data = json.loads(file_content)
        
            # 检查数据格式是否正确
            if not isinstance(outline_data, dict):
                raise ValueError("大纲数据格式不正确")
            
            # 清空现有大纲
            self.outline_list.clear()
            self.novel_outline = []
            self.select_all_checkbox.setCheckState(Qt.Unchecked)
            
            # 加载大纲章节
            chapters = outline_data.get("chapters", [])
            if not isinstance(chapters, list):
                raise ValueError("章节数据格式不正确")
                
            for chapter_data in chapters:
                # 确保章节数据是字典类型
                if not isinstance(chapter_data, dict):
                    continue
                    
                chapter_num = chapter_data.get("chapter_num")
                title = chapter_data.get("title", "")
                summary = chapter_data.get("summary", "")
                content = chapter_data.get("content", "")  # 读取 content 字段
                
                # 确保章节号是整数
                if not isinstance(chapter_num, int):
                    continue
                
                # 添加大纲项（使用add_outline_item方法确保UI正确显示）
                self.add_outline_item(chapter_num, title, summary)
                
                # 设置复选框和编辑框状态
                outline = self.novel_outline[-1]
                # 修复：确保selected字段是布尔值而不是其他类型
                selected_value = chapter_data.get("selected", False)
                if isinstance(selected_value, bool) and selected_value:
                    outline['checkbox'].setChecked(True)
                
                # 恢复可编辑字段内容（如果存在）
                if 'title_edit' in outline and 'title' in chapter_data:
                    outline['title_edit'].setText(chapter_data['title'])
                if 'summary_edit' in outline and 'summary' in chapter_data:
                    outline['summary_edit'].setPlainText(chapter_data['summary'])
                if 'content' in chapter_data:  # 更新 content 字段
                    outline['content'] = chapter_data['content']
        
            # 更新全选状态
            self.update_select_all_state()
            
            # 加载已生成的内容
            self.final_result.clear()
            self.chapter_items_map = {}
            
            # 首先检查是否有生成的内容
            generated_content = outline_data.get("generated_content", {})
            
            # 创建一个集合来跟踪已经处理过的章节号
            processed_chapters = set()
            
            # 先处理generated_content中的内容（如果存在）
            if isinstance(generated_content, dict) and generated_content:
                # 按章节号排序
                sorted_chapters = sorted(generated_content.items(), key=lambda x: int(x[0]))
                
                for chapter_num, content_data in sorted_chapters:
                    # 确保内容数据是字典类型
                    if not isinstance(content_data, dict):
                        continue
                        
                    try:
                        chapter_num = int(chapter_num)
                        title = content_data.get("title", f"第{chapter_num}章")
                        content = content_data.get("content", "")
                        
                        # 添加章节项
                        chapter_item = self.add_chapter_item(chapter_num, title, content)
                        self.chapter_items_map[chapter_num] = chapter_item
                        
                        # 标记为已处理
                        processed_chapters.add(chapter_num)
                        
                    except (ValueError, TypeError):
                        # 跽过无效的章节号
                        continue
            
            # 然后处理大纲章节中的内容（如果该章节尚未处理且有内容）
            for outline in self.novel_outline:
                chapter_num = outline['chapter_num']
                content = outline.get('content', '')
                
                # 如果该章节还没有被处理过且有内容，则添加到最终结果列表
                if chapter_num not in processed_chapters and content:
                    title = f"第{chapter_num}章 {outline['title']}"
                    chapter_item = self.add_chapter_item(chapter_num, title, content)
                    self.chapter_items_map[chapter_num] = chapter_item
                    
                    # 标记为已处理
                    processed_chapters.add(chapter_num)
            
            # 移除读取成功后的弹窗显示
            # QMessageBox.information(self, "成功", "小说大纲和已生成内容已加载")
            
        except json.JSONDecodeError as e:
            error_msg = f"加载小说大纲时发生JSON解析错误: {str(e)}"
            print(error_msg)
            self.role_output.append(f"[系统] {error_msg}")
        except Exception as e:
            error_msg = f"加载小说大纲时发生错误: {str(e)}"
            print(error_msg)
            self.role_output.append(f"[系统] {error_msg}")

    def clear_all(self):
        """清除所有内容"""
        # 清空用户输入
        self.user_input.clear()
        
        # 清空AI角色输出窗口
        self.role_output.clear()
        
        # 清空小说最终结果窗口
        self.final_result.clear()
        self.chapter_items_map.clear()
        
        # 清空大纲
        self.outline_list.clear()
        self.novel_outline.clear()
        
        # 重置全选复选框
        self.select_all_checkbox.setChecked(False)
        
        # 删除持久化文件
        import os
        try:
            if os.path.exists("小说大纲.json"):
                os.remove("小说大纲.json")
        except Exception as e:
            QMessageBox.warning(self, "警告", f"删除小说大纲文件时出错：{str(e)}")

    def save_novel_outline(self):
        """
        保存小说大纲到文件
        """
        try:
            # 保存小说内容要求到txt文件
            content = self.user_input.toPlainText()
            with open("小说内容要求.txt", "w", encoding="utf-8") as f:
                f.write(content)
            
            import json
            
            # 准备大纲数据
            outline_data = {
                "chapters": [],
                "generated_content": {}
            }
            
            # 从大纲列表数据中提取纯净数据，重新生成一个不包含Qt对象的新列表
            for outline in self.novel_outline:
                # 提取纯净的章节数据
                chapter_data = {
                    "chapter_num": outline.get('chapter_num', 0),
                    "title": outline.get('title', ''),
                    "summary": outline.get('summary', ''),
                    "content": outline.get('content', ''),
                    "selected": False  # 默认未选中
                }
                
                # 安全地获取复选框状态
                checkbox = outline.get('checkbox')
                if checkbox is not None:
                    try:
                        chapter_data["selected"] = checkbox.isChecked()
                    except:
                        pass  # 如果获取失败，保持默认值False
                
                # 安全地从编辑控件中获取最新数据
                title_edit = outline.get('title_edit')
                if title_edit is not None:
                    try:
                        chapter_data["title"] = title_edit.text()
                    except:
                        pass  # 如果获取失败，使用之前获取的值
                
                summary_edit = outline.get('summary_edit')
                if summary_edit is not None:
                    try:
                        chapter_data["summary"] = summary_edit.toPlainText()
                    except:
                        pass  # 如果获取失败，使用之前获取的值
                
                outline_data["chapters"].append(chapter_data)
            
            # 收集已生成的小说内容
            for i in range(self.final_result.count()):
                item = self.final_result.item(i)
                item_data = item.data(Qt.UserRole)
                if item_data and 'chapter_num' in item_data:
                    chapter_num = item_data['chapter_num']
                    outline_data["generated_content"][chapter_num] = {
                        "title": item_data.get('title', ''),
                        "content": item_data.get('content', ''),
                        "display_text": item.text()
                    }
            
            # 保存到文件
            with open("小说大纲.json", "w", encoding="utf-8") as f:
                json.dump(outline_data, f, ensure_ascii=False, indent=4)
            
            # 在AI角色输出窗口中显示系统提示，替代弹窗
            self.role_output.append("[系统] 小说大纲已保存到小说大纲.json")
            
        except Exception as e:
            # 在AI角色输出窗口中显示系统提示，替代弹窗
            self.role_output.append(f"[系统] 保存小说大纲时发生错误：{str(e)}")

    def add_chapter_item(self, chapter_num, title, content):
        """向小说最终结果列表中添加一个新的章节项"""
        # 创建自定义项
        item = QListWidgetItem()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # 添加内边距10px，类似于大纲项
        layout.setContentsMargins(10, 10, 10, 10)
        # 设置标题与内容之间无间隔
        layout.setSpacing(0)
        
        # 计算字数
        char_count = len(content.strip()) if content else 0
        
        # 上部分：章节标题（包含字数统计）
        # 优化：检查title是否已经包含"第X章"前缀，避免重复显示
        if title.startswith(f"第{chapter_num}章"):
            title_with_count = f"{title}（本章正文共{char_count}字）"
        else:
            title_with_count = f"第{chapter_num}章 {title}（本章正文共{char_count}字）"
            
        title_label = QLabel(title_with_count)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        # 下部分：章节内容
        content_text = QTextEdit(content)
        content_text.setMaximumHeight(200)  # 限制高度
        content_text.setReadOnly(True)
        content_text.setWordWrapMode(True)
        
        layout.addWidget(title_label)
        layout.addWidget(content_text)
        
        widget.setLayout(layout)
        
        # 设置项的高度
        item.setSizeHint(widget.sizeHint())
        
        # 添加到列表
        self.final_result.addItem(item)
        self.final_result.setItemWidget(item, widget)
        
        # 返回创建的项和组件引用
        return {
            'item': item,
            'widget': widget,
            'title_label': title_label,
            'content_text': content_text
        }
        # 阻止信号触发，避免递归
        self.select_all_checkbox.blockSignals(True)
        
        is_checked = state == Qt.Checked
        
        for chapter in self.novel_outline:
            chapter['checkbox'].setChecked(is_checked)
            
        self.select_all_checkbox.blockSignals(False)

    def toggle_select_all(self, state):
        """全选/取消全选所有章节"""
        # 阻止信号触发，避免递归
        self.select_all_checkbox.blockSignals(True)
        
        is_checked = state == Qt.Checked
        
        for chapter in self.novel_outline:
            chapter['checkbox'].setChecked(is_checked)
            
        self.select_all_checkbox.blockSignals(False)

    def on_outline_item_clicked(self, item):
        """处理大纲项点击事件"""
        # 获取点击的项的组件引用
        widget = self.final_result.itemWidget(item)
        title_label = widget.findChild(QLabel, 'title_label')
        content_text = widget.findChild(QTextEdit, 'content_text')
        
        # 显示详细信息
        self.title_input.setText(title_label.text())
        self.content_input.setPlainText(content_text.toPlainText())

    def add_outline_item(self, chapter_num, title, summary):
        """向大纲列表中添加一个新的大纲项"""
        # 创建包含复选框的自定义项
        item = QListWidgetItem()
        widget = QWidget()
        layout = QHBoxLayout(widget)
        # 添加内边距10px
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 左侧：复选框
        checkbox = QCheckBox()
        
        # 右侧：上下结构
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        # 设置章节标题与梗概之间无间隔
        right_layout.setSpacing(0)
        
        # 上部分：章节标题（可编辑）
        title_edit = QLineEdit(title)
        title_edit.setPlaceholderText(f"第{chapter_num}章 标题")
        
        # 下部分：章节梗概（可编辑）
        summary_edit = QTextEdit(summary)
        summary_edit.setPlaceholderText("章节梗概")
        summary_edit.setMaximumHeight(60)  # 限制高度
        summary_edit.setWordWrapMode(True)
        
        right_layout.addWidget(title_edit)
        right_layout.addWidget(summary_edit)
        
        layout.addWidget(checkbox)
        layout.addWidget(right_widget)
        
        widget.setLayout(layout)
        
        # 设置项的高度
        item.setSizeHint(widget.sizeHint())
        
        # 添加到列表
        self.outline_list.addItem(item)
        self.outline_list.setItemWidget(item, widget)
        
        # 保存章节信息
        chapter = {
            'chapter_num': chapter_num,
            'title': title,
            'summary': summary,
            'content': "",  # 新增 content 字段
            'item': item,
            'checkbox': checkbox,
            'title_edit': title_edit,
            'summary_edit': summary_edit
        }
        self.novel_outline.append(chapter)

    def update_select_all_state(self):
        """更新全选复选框的状态"""
        if not self.novel_outline:
            return
            
        checked_count = sum(1 for chapter in self.novel_outline if chapter['checkbox'].isChecked())
        
        # 阻止信号触发，避免递归
        self.select_all_checkbox.blockSignals(True)
        
        if checked_count == 0:
            self.select_all_checkbox.setCheckState(Qt.Unchecked)
        elif checked_count == len(self.novel_outline):
            self.select_all_checkbox.setCheckState(Qt.Checked)
        else:
            self.select_all_checkbox.setCheckState(Qt.PartiallyChecked)
            
        self.select_all_checkbox.blockSignals(False)

    def on_outline_item_clicked(self, item):
        """当大纲列表项被点击时，定位到小说最终结果列表中的对应章节"""
        # 查找点击的大纲项对应的数据
        for outline in self.novel_outline:
            if outline['item'] == item:
                chapter_num = outline['chapter_num']
                # 检查该章节是否在最终结果列表中存在
                if chapter_num in self.chapter_items_map:
                    chapter_item = self.chapter_items_map[chapter_num]
                    # 定位到该章节项并确保可见
                    self.final_result.setCurrentItem(chapter_item['item'])
                    self.final_result.scrollToItem(chapter_item['item'])
                    # 可选：高亮显示该项
                    chapter_item['item'].setSelected(True)
                break

    def on_final_result_item_clicked(self, item):
        """当小说最终结果列表项被点击时，定位到大纲列表中的对应章节"""
        # 查找点击的章节项对应的数据
        for chapter_num, chapter_item in self.chapter_items_map.items():
            if chapter_item['item'] == item:
                # 查找该章节在大纲列表中的项
                for outline in self.novel_outline:
                    if outline['chapter_num'] == chapter_num:
                        # 定位到该大纲项并确保可见
                        self.outline_list.setCurrentItem(outline['item'])
                        self.outline_list.scrollToItem(outline['item'])
                        # 可选：高亮显示该项
                        outline['item'].setSelected(True)
                        break
                break

    def update_outline_content(self, index, new_title, new_summary):
        """更新大纲内容"""
        if 0 <= index < len(self.novel_outline):
            # 更新数据结构
            self.novel_outline[index]['title'] = new_title
            self.novel_outline[index]['summary'] = new_summary
            
            # 更新UI显示
            item_widget = self.novel_outline[index]['item_widget']
            if item_widget and item_widget.layout():
                # 更新标题
                title_label = item_widget.findChild(QLabel, "title_label")
                if title_label:
                    title_label.setText(f"第{self.novel_outline[index]['chapter_num']}章 {new_title}")
                
                # 更新摘要，提取前3行作为摘要显示
                summary_lines = new_summary.split('\n')
                summary_preview = '\n'.join(summary_lines[:3])
                summary_label = item_widget.findChild(QLabel, "summary_label")
                if summary_label:
                    summary_label.setText(summary_preview)

    def update_outline_item_single(self, chapter_num, title, summary):
        """更新单个大纲项"""
        # 查找对应章节
        target_chapter = None
        for chapter in self.novel_outline:
            if chapter['chapter_num'] == chapter_num:
                target_chapter = chapter
                break
        
        # 如果找到了对应章节，则更新其内容
        if target_chapter:
            # 更新内存中的数据
            target_chapter['title'] = title
            target_chapter['summary'] = summary
            
            # 更新UI中的显示
            if 'title_edit' in target_chapter and target_chapter['title_edit']:
                target_chapter['title_edit'].setText(title)
            if 'summary_edit' in target_chapter and target_chapter['summary_edit']:
                target_chapter['summary_edit'].setPlainText(summary)
            
            # 保存到文件
            self.save_novel_outline()
            
            # 重新加载角色列表（可能有新角色添加）
            self.load_characters()
        else:
            # 如果没有找到对应章节，添加新的大纲项
            self.add_outline_item(chapter_num, title, summary)
            
            # 在AI角色输出窗口中显示系统提示
            self.role_output.append(f"[系统] 新增第{chapter_num}章大纲并更新完成")

    def finish_selected_chapters_regeneration(self):
        """完成选中章节的重新生成"""
        # 恢复按钮状态
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("生成大纲")
        self.stop_outline_btn.setEnabled(False)  # 禁用中断按钮
        
        # 重新加载角色列表
        self.load_characters()
        
        # 在AI角色输出窗口中显示系统提示，替代弹窗
        self.role_output.append("[系统] 选中的章节已生成完成！")

    def show_error(self, message):
        """显示错误信息"""
        QMessageBox.critical(self, "错误", message)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()