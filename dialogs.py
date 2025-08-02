from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QTextEdit, QLabel, QLineEdit, QComboBox, QMessageBox, QDialog, QFormLayout, QDialogButtonBox, QSpinBox, QDoubleSpinBox, QListWidget, QListWidgetItem, QCheckBox, QGroupBox, QGridLayout)
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtGui import QTextDocument, QFont
import json


class NovelSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("小说设置")
        
        # 章节数量
        self.chapter_count = QSpinBox()
        self.chapter_count.setRange(1, 500)
        self.chapter_count.setValue(30)
        self.chapter_count.valueChanged.connect(self.calculate_total_words)
        
        # 每章字数
        self.words_per_chapter = QSpinBox()
        self.words_per_chapter.setRange(500, 20000)
        self.words_per_chapter.setValue(1500)
        self.words_per_chapter.setSuffix(" 字")
        self.words_per_chapter.valueChanged.connect(self.calculate_total_words)
        
        # 总字数显示（只读）
        self.total_words = QLabel("45000 字")
        self.total_words.setStyleSheet("QLabel { color: blue; font-weight: bold; }")
        
        layout = QFormLayout(self)
        layout.addRow("章节数量:", self.chapter_count)
        layout.addRow("每章字数:", self.words_per_chapter)
        layout.addRow("总字数:", self.total_words)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        # 初始化计算总字数
        self.calculate_total_words()
    
    def calculate_total_words(self):
        """根据章节数和每章字数计算总字数"""
        total = self.chapter_count.value() * self.words_per_chapter.value()
        self.total_words.setText(f"{total} 字")
    
    def get_settings(self):
        """获取设置值"""
        return {
            "chapter_count": self.chapter_count.value(),
            "words_per_chapter": self.words_per_chapter.value(),
            "total_words": self.chapter_count.value() * self.words_per_chapter.value()
        }


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("参数设置")
        
        # 添加定时器确保模型输入框始终启用
        from PyQt5.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.ensure_model_inputs_enabled)
        self.timer.start(100)  # 每100毫秒检查一次
        
        # 温度参数输入框
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 1.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(0.5)
        
        # AI作家API Key输入框
        self.writer_key = QLineEdit()
        
        # AI读者API Key输入框
        self.reader_key = QLineEdit()
        
        # AI编辑API Key输入框
        self.editor_key = QLineEdit()
        
        # AI作家模型选择
        self.writer_model = QLineEdit()
        self.writer_model.setText("qwen-plus")
        
        # AI读者模型选择
        self.reader_model = QLineEdit()
        self.reader_model.setText("qwen-plus")
        
        # AI编辑模型选择
        self.editor_model = QLineEdit()
        self.editor_model.setText("qwen-plus")
        
        # AI资深作家API Key输入框（作家1）
        self.senior_writer1_key = QLineEdit()
        
        # AI资深作家模型选择（作家1）
        self.senior_writer1_model = QLineEdit()
        self.senior_writer1_model.setText("qwen-plus")
        
        # AI资深作家API Key输入框（作家2）
        self.senior_writer2_key = QLineEdit()
        
        # AI资深作家模型选择（作家2）
        self.senior_writer2_model = QLineEdit()
        self.senior_writer2_model.setText("qwen-plus")
        
        # 创建布局
        layout = QFormLayout(self)
        layout.addRow("温度参数:", self.temperature_spin)
        layout.addRow("AI作家API Key:", self.writer_key)
        layout.addRow("AI读者API Key:", self.reader_key)
        layout.addRow("AI编辑API Key:", self.editor_key)
        layout.addRow("AI作家模型:", self.writer_model)
        layout.addRow("AI读者模型:", self.reader_model)
        layout.addRow("AI编辑模型:", self.editor_model)
        layout.addRow("AI资深作家1 API Key:", self.senior_writer1_key)
        layout.addRow("AI资深作家1 模型:", self.senior_writer1_model)
        layout.addRow("AI资深作家2 API Key:", self.senior_writer2_key)
        layout.addRow("AI资深作家2 模型:", self.senior_writer2_model)
        
        # 创建按钮框
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        # 确保模型输入框初始状态为启用
        self.ensure_model_inputs_enabled()
    
    def ensure_model_inputs_enabled(self):
        """确保所有模型输入框都处于启用状态"""
        self.writer_model.setEnabled(True)
        self.reader_model.setEnabled(True)
        self.editor_model.setEnabled(True)
        self.senior_writer1_model.setEnabled(True)
        self.senior_writer2_model.setEnabled(True)
    
    def closeEvent(self, event):
        """关闭对话框时停止定时器"""
        self.timer.stop()
        super().closeEvent(event)
    
    def get_settings(self):
        """获取设置值"""
        return {
            "temperature": self.temperature_spin.value(),
            "writer_key": self.writer_key.text(),
            "reader_key": self.reader_key.text(),
            "editor_key": self.editor_key.text(),
            "writer_model": self.writer_model.text(),
            "reader_model": self.reader_model.text(),
            "editor_model": self.editor_model.text(),
            "senior_writer1_key": self.senior_writer1_key.text(),
            "senior_writer1_model": self.senior_writer1_model.text(),
            "senior_writer2_key": self.senior_writer2_key.text(),
            "senior_writer2_model": self.senior_writer2_model.text()
        }


class LocalSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("本地设置")
        
        # 使用本地模型总开关
        self.use_local_checkbox = QCheckBox("使用本地模型")
        
        # AI作家本地模型路径
        self.writer_local_model = QLineEdit()
        self.writer_local_model.setPlaceholderText("例如: ./models/qwen.gguf")
        
        # AI读者本地模型路径
        self.reader_local_model = QLineEdit()
        self.reader_local_model.setPlaceholderText("例如: ./models/qwen.gguf")
        
        # AI编辑本地模型路径
        self.editor_local_model = QLineEdit()
        self.editor_local_model.setPlaceholderText("例如: ./models/qwen.gguf")
        
        # AI资深作家1本地模型路径
        self.senior_writer1_local_model = QLineEdit()
        self.senior_writer1_local_model.setPlaceholderText("例如: ./models/qwen.gguf")
        
        # AI资深作家2本地模型路径
        self.senior_writer2_local_model = QLineEdit()
        self.senior_writer2_local_model.setPlaceholderText("例如: ./models/qwen.gguf")
        
        # 创建布局
        layout = QFormLayout(self)
        layout.addRow(self.use_local_checkbox)
        layout.addRow("AI作家本地模型:", self.writer_local_model)
        layout.addRow("AI读者本地模型:", self.reader_local_model)
        layout.addRow("AI编辑本地模型:", self.editor_local_model)
        layout.addRow("AI资深作家1本地模型:", self.senior_writer1_local_model)
        layout.addRow("AI资深作家2本地模型:", self.senior_writer2_local_model)
        # 创建按钮框
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def get_settings(self):
        """获取设置值"""
        return {
            "use_local": self.use_local_checkbox.isChecked(),
            "writer_local_model": self.writer_local_model.text(),
            "reader_local_model": self.reader_local_model.text(),
            "editor_local_model": self.editor_local_model.text(),
            "senior_writer1_local_model": self.senior_writer1_local_model.text(),
            "senior_writer2_local_model": self.senior_writer2_local_model.text()
        }
    
    def set_settings(self, settings):
        """设置值"""
        self.use_local_checkbox.setChecked(settings.get("use_local", False))
        self.writer_local_model.setText(settings.get("writer_local_model", ""))
        self.reader_local_model.setText(settings.get("reader_local_model", ""))
        self.editor_local_model.setText(settings.get("editor_local_model", ""))
        self.senior_writer1_local_model.setText(settings.get("senior_writer1_local_model", ""))
        self.senior_writer2_local_model.setText(settings.get("senior_writer2_local_model", ""))