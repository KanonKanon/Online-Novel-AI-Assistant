import dashscope
from dashscope import Generation
import json
import re
import time
import threading  # 添加这一行

class GlobalModelManager:
    _instance = None
    _models = {}  # 存储已加载的模型实例
    _loading_events = {}  # 存储模型加载事件
    _lock = None
    _progress_callbacks = {}  # 存储进度回调函数
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalModelManager, cls).__new__(cls)
            cls._lock = threading.Lock()  # 使用 threading.Lock()
        return cls._instance
    
    def load_model_async(self, model_path, progress_callback=None):
        """
        异步加载模型，如果模型已在加载或已加载则直接返回
        """
        with self._lock:
            # 保存进度回调函数
            if progress_callback:
                self._progress_callbacks[model_path] = progress_callback
            
            if model_path in self._models:
                # 模型已加载
                return self._models[model_path]
            
            if model_path not in self._loading_events:
                # 创建加载事件
                self._loading_events[model_path] = threading.Event()  # 使用 threading.Event()
                self._loading_events[model_path].clear()
                
                # 启动加载线程
                def load_model():
                    try:
                        # 检查模型文件是否存在
                        if not os.path.exists(model_path):
                            print(f"Model file not found: {model_path}")
                            self._report_progress(model_path, f"错误: 找不到模型文件 {model_path}")
                            return
                        
                        # 获取模型文件大小
                        file_size = os.path.getsize(model_path)
                        print(f"Loading model: {model_path} (Size: {file_size / (1024**3):.2f} GB)")
                        
                        self._report_progress(model_path, f"模型文件大小: {file_size / (1024**3):.2f} GB")
                        
                        # 模拟加载进度
                        loaded_size = 0
                        
                        # 分块读取文件来模拟进度
                        chunk_size = max(1024*1024, file_size // 100)  # 每次读取1MB或总大小的1%
                        loaded = 0
                        
                        try:
                            with open(model_path, 'rb') as f:
                                while loaded < file_size:
                                    # 读取一块数据
                                    data = f.read(chunk_size)
                                    if not data:
                                        break
                                        
                                    loaded += len(data)
                                    loaded_size += len(data)
                                    
                                    # 计算进度百分比
                                    if file_size > 0:
                                        progress = min(100, int((loaded_size / file_size) * 100))
                                        self._report_progress(model_path, f"模型加载进度: {progress}%")
                                    
                                    # 稍微延迟以模拟真实的加载时间
                                    time.sleep(0.01)
                        except Exception as e:
                            self._report_progress(model_path, f"读取模型文件时出错: {str(e)}")
                            return
                        
                        # 现在真正加载模型
                        self._report_progress(model_path, "正在初始化模型...")
                        
                        from llama_cpp import Llama
                        # 初始化llama.cpp模型
                        llm = Llama(
                            model_path=model_path,
                            n_ctx=4096,  # 上下文长度
                            n_threads=8,  # 使用的线程数
                            n_gpu_layers=-1  # 使用GPU层数，-1表示尽可能使用GPU
                        )
                        print("Model loaded successfully")
                        self._report_progress(model_path, "模型加载完成")
                        
                        # 存储模型实例
                        with self._lock:
                            self._models[model_path] = llm
                    except Exception as e:
                        print(f"Error loading local model: {e}")
                        self._report_progress(model_path, f"模型加载出错: {str(e)}")
                    finally:
                        # 设置加载完成事件
                        with self._lock:
                            self._loading_events[model_path].set()
                
                # 在单独线程中加载模型
                thread = threading.Thread(target=load_model)  # 确认使用 threading.Thread
                thread.daemon = True
                thread.start()
            
            return None  # 返回None表示正在加载中
    
    def _report_progress(self, model_path, message):
        """
        报告加载进度
        """
        with self._lock:
            callback = self._progress_callbacks.get(model_path)
        
        if callback:
            callback(message)
    
    def wait_for_model(self, model_path, timeout=180):
        """
        等待模型加载完成
        """
        with self._lock:
            if model_path in self._models:
                return self._models[model_path]
            
            if model_path not in self._loading_events:
                return None  # 模型未开始加载
            
            event = self._loading_events[model_path]
        
        # 等待加载完成
        if event.wait(timeout=timeout):
            with self._lock:
                return self._models.get(model_path)
        
        return None  # 超时
    
    def get_model(self, model_path):
        """
        获取已加载的模型实例
        """
        with self._lock:
            return self._models.get(model_path)


# 模型加载进度回调类
class ModelLoadProgress:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self.loaded_size = 0
        self.total_size = 0
        
    def set_total_size(self, size):
        self.total_size = size
        
    def update(self, size):
        self.loaded_size += size
        if self.total_size > 0 and self.progress_callback:
            progress = min(100, int((self.loaded_size / self.total_size) * 100))
            self.progress_callback(progress)


class AIWriter:
    def __init__(self, api_key=None, model='qwen-plus', use_local=False, local_model_path=None):
        self.model = model
        self.use_local = use_local
        self.local_model_path = local_model_path
        self.llm = None
        self.model_manager = GlobalModelManager()
        if api_key and not use_local:
            dashscope.api_key = api_key
        elif use_local and local_model_path:
            # 异步初始化llama.cpp模型
            self.llm = self.model_manager.load_model_async(local_model_path)

    def wait_for_model(self, timeout=180, progress_callback=None):
        """
        等待模型加载完成
        """
        if not self.use_local or not self.local_model_path:
            return True
            
        if self.llm:
            return True
            
        # 如果有进度回调，启动加载过程
        if progress_callback:
            self.llm = self.model_manager.load_model_async(self.local_model_path, progress_callback)
        else:
            # 确保模型开始加载
            self.llm = self.model_manager.load_model_async(self.local_model_path)
            
        # 等待模型加载完成
        if self.llm is None:
            self.llm = self.model_manager.wait_for_model(self.local_model_path, timeout)
        return self.llm is not None

    def generate_content(self, prompt, feedback=None, selected_characters=None):
        """
        生成小说章节内容
        """
        # 添加专业背景设定
        professional_background = "你是一位有20年以上经验的大师级网文小说作家，擅长创作各种类型的长篇小说，具有丰富的写作经验和深厚的文学功底。"
        
        # 构造角色信息字符串
        character_info = ""
        if selected_characters:
            character_info = "\n\n要求在本章中包含以下角色的互动情节：\n"
            for character in selected_characters:
                character_info += f"角色名称：{character['name']}，角色背景关系：{character['background']}\n"
            character_info += "\n请在创作中安排这些角色与主角之间的互动，互动内容可以包括但不限于（战斗、聊天、谈情等）。"
        
        if feedback:
            # 构造包含反馈的提示
            full_prompt = f"{professional_background}\n{prompt}\n\n编辑反馈：{feedback}{character_info}\n\n请根据编辑反馈修改内容，确保内容满足用户要求和编辑建议。请严格按照以下格式输出：\n【第xx章  章节标题】\n【章节正文：\nXXXX】\n***其它说明内容***\nXXX...."
        else:
            # 构造不包含反馈的提示
            full_prompt = f"{professional_background}\n{prompt}{character_info}\n\n请创作满足用户要求的小说章节内容。请严格按照以下格式输出：\n【第xx章  章节标题】\n【章节正文：\nXXXX】\n***其它说明内容***\nXXX...."
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            # 获取最新加载的模型实例
            self.llm = self.model_manager.get_model(self.local_model_path)
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(full_prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=full_prompt,
                    max_tokens=2000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error: {str(e)}"
    
    def _generate_with_local_model(self, prompt, max_tokens=None, temperature=None, stop=None):
        """
        使用本地模型生成内容
        """
        try:
            # 设置默认参数
            gen_kwargs = {
                "max_tokens": max_tokens or 800,
                "temperature": temperature or 0.7,
                "echo": False
            }
            
            # 如果提供了stop参数，则使用它
            if stop is not None:
                gen_kwargs["stop"] = stop
            else:
                # 默认的停止条件
                gen_kwargs["stop"] = ["\n\n"]
            
            # 使用llama.cpp生成内容
            output = self.llm(
                prompt,
                max_tokens=2000,
                temperature=0.7,
                echo=False
            )
            
            # 提取生成的文本
            if 'choices' in output and len(output['choices']) > 0:
                generated_text = output['choices'][0]['text']
            else:
                generated_text = ""
            
            return generated_text
        except Exception as e:
            return f"Local model error occurred: {str(e)}"
    
    def _remove_brackets(self, content):
        """
        移除内容中的【】符号，避免影响后续处理逻辑
        """
        # 将【】符号替换为普通括号()或者直接移除
        content = re.sub(r'【', '(', content)
        content = re.sub(r'】', ')', content)
        return content


class AISeniorWriter:
    """
    专门用于大纲生成的资深作家类，支持对抗生成网络
    """
    def __init__(self, api_key=None, model="qwen-plus", use_local=False, local_model_path=None):
        self.api_key = api_key
        self.model = model
        self.use_local = use_local
        self.local_model_path = local_model_path
        self.llm = None
        self.model_manager = GlobalModelManager()
        self.main_window = None  # 添加对主窗口的引用
    
    def set_main_window(self, main_window):
        """设置主窗口引用"""
        self.main_window = main_window
    
    def log_debug(self, message):
        """调试信息输出方法"""
        if self.main_window:
            self.main_window.log_message(message, "debug")
        else:
            print(f"[调试] {message}")
    
    def wait_for_model(self, timeout=180, progress_callback=None):
        """
        等待模型加载完成
        """
        if not self.use_local or not self.local_model_path:
            return True
            
        if self.llm:
            return True
            
        # 如果有进度回调，启动加载过程
        if progress_callback:
            self.llm = self.model_manager.load_model_async(self.local_model_path, progress_callback)
        else:
            # 确保模型开始加载
            self.llm = self.model_manager.load_model_async(self.local_model_path)
            
        # 等待模型加载完成
        if self.llm is None:
            self.llm = self.model_manager.wait_for_model(self.local_model_path, timeout)
        return self.llm is not None

    def generate_outline(self, start_chapter, chapter_count, user_prompt, feedback=None, selected_characters=None):
        """
        生成完整的小说大纲
        """
        professional_background = "你是一位有20年以上经验的网文小说资深作家，擅长创作各种类型的长篇小说，具有丰富的写作经验和深厚的文学功底。"
        
        # 构造角色信息字符串
        character_info = ""
        if selected_characters:
            character_info = "\n\n要求在大纲中包含以下角色的互动情节：\n"
            for character in selected_characters:
                character_info += f"角色名称：{character['name']}，角色背景关系：{character['background']}\n"
            character_info += "\n请在创作中安排这些角色与主角之间的互动，互动内容可以包括但不限于（战斗、聊天、谈情等）。"
        
        if feedback:
            prompt = f"{professional_background}\n根据另一位资深作家的反馈修改小说大纲。\n\n小说整体要求：{user_prompt}\n\n反馈意见：{feedback}{character_info}\n\n请提供一个包含{chapter_count}章的小说大纲，从第{start_chapter}章开始。每章需要包含章节标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：\n【第x章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 各章节之间要有连贯性，情节发展要合理\n4. 角色名称要保持一致，不要串改角色名称"
        else:
            prompt = f"{professional_background}\n请为小说创作一个包含{chapter_count}章的大纲，从第{start_chapter}章开始。\n\n小说整体要求：{user_prompt}{character_info}\n\n每章需要包含章节标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：\n【第x章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 各章节之间要有连贯性，情节发展要合理\n4. 角色名称要保持一致，不要串改角色名称"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            # 获取最新加载的模型实例
            self.llm = self.model_manager.get_model(self.local_model_path)
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                import dashscope
                from dashscope import Generation
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=4000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error: {str(e)}"

    def generate_character_design(self, novel_theme):
        """
        生成角色设计
        """
        print(">>> PRINT: 进入AISeniorWriter.generate_character_design方法")  # 使用print确保输出
        self.log_debug(">>> 进入generate_character_design方法")
        # 添加专业背景设定
        professional_background = "你是一位专业的小说角色设计师，擅长创造各种类型小说中的角色，具有丰富的角色塑造经验和深厚的文学功底。"
        
        # 构造提示
        prompt = f"""
        {professional_background}
        根据以下小说主题，为我设计一些角色：
        
        小说主题：{novel_theme}
        
        请提供3个不同类型的角色设计，每个角色需要包含：
        1. 角色名称
        2. 角色背景说明（包括个人能力、社会关系、与主角的关系等）
        
        请严格按照以下格式输出：
        【角色设计1】
        角色名称：[角色名称]
        角色背景：[角色背景说明，包括个人能力、社会关系、与主角的关系等]
        
        【角色设计2】
        角色名称：[角色名称]
        角色背景：[角色背景说明，包括个人能力、社会关系、与主角的关系等]
        
        【角色设计3】
        角色名称：[角色名称]
        角色背景：[角色背景说明，包括个人能力、社会关系、与主角的关系等]
        """
        
        # 使用主窗口的日志方法输出调试信息
        self.log_debug(f"使用本地模型: {self.use_local}")
        self.log_debug(f"本地模型路径: {self.local_model_path}")
        self.log_debug(f"在线模型: {self.model}")
        
        if self.use_local and self.local_model_path:
            self.log_debug("使用本地模型生成内容")
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            # 获取最新加载的模型实例
            self.llm = self.model_manager.get_model(self.local_model_path)
            self.log_debug(f"模型实例: {self.llm}")
                
            if self.llm:
                # 使用本地模型
                self.log_debug("调用本地模型生成内容")
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            self.log_debug("使用在线API生成内容")
            # 使用在线API
            try:
                import dashscope
                from dashscope import Generation
                self.log_debug("准备调用Generation.call方法")
                self.log_debug(f"调用参数: model={self.model}, max_tokens=2000, temperature=0.7")
                self.log_debug(f"提示内容长度: {len(prompt)} 字符")
                self.log_debug("开始调用Generation.call方法")
                
                # 调用DashScope API
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=2000,  # 增加max_tokens以确保生成足够的内容
                    temperature=0.7
                )
                
                self.log_debug("Generation.call方法调用完成")
                self.log_debug(f"响应对象类型: {type(response)}")
                
                # 检查响应状态
                if hasattr(response, 'status_code'):
                    self.log_debug(f"响应状态码: {response.status_code}")
                
                # 处理响应
                if response.status_code == 200:
                    self.log_debug("响应状态码为200，处理响应内容")
                    ai_response = response.output.text
                    self.log_debug(f"AI响应内容长度: {len(ai_response)} 字符")
                    self.log_debug(f"AI响应前100字符: {ai_response[:100]}")
                    print(">>> PRINT: 准备返回正常结果")  # 使用print确保输出
                    self.log_debug("<<< 正常退出generate_character_design方法")
                    return ai_response
                else:
                    self.log_debug(f"API调用失败，状态码: {response.status_code}")
                    error_msg = f"API调用失败，状态码: {response.status_code}"
                    if hasattr(response, 'message'):
                        error_msg += f"，错误信息: {response.message}"
                    self.log_debug(error_msg)
                    print(">>> PRINT: 准备返回错误结果：API调用失败")  # 使用print确保输出
                    self.log_debug("<<< 异常退出generate_character_design方法")
                    return f"Error: {error_msg}"
                    
            except ImportError as e:
                self.log_debug(f"导入dashscope失败: {str(e)}")
                print(">>> PRINT: 准备返回错误结果：导入失败")  # 使用print确保输出
                self.log_debug("<<< 异常退出generate_character_design方法")
                return f"Error: Failed to import dashscope: {str(e)}"
            except TimeoutError as e:
                self.log_debug(f"API调用超时: {str(e)}")
                print(">>> PRINT: 准备返回错误结果：调用超时")  # 使用print确保输出
                self.log_debug("<<< 异常退出generate_character_design方法")
                return f"Error: API call timeout: {str(e)}"
            except Exception as e:
                self.log_debug(f"API调用异常发生: {str(e)}")
                import traceback
                self.log_debug(f"异常堆栈: {traceback.format_exc()}")
                print(">>> PRINT: 准备返回错误结果：其他异常")  # 使用print确保输出
                self.log_debug("<<< 异常退出generate_character_design方法")
                return f"Error: {str(e)}"

    def generate_chapter_outline(self, chapter_num, user_prompt, previous_chapters="", feedback=None, selected_characters=None):
        """
        生成单个章节的大纲（标题和梗概）
        """
        professional_background = "你是一位有20年以上经验的网文小说资深作家，擅长创作各种类型的长篇小说，具有丰富的写作经验和深厚的文学功底。"
        
        # 构造角色信息字符串
        character_info = ""
        if selected_characters:
            character_info = "\n\n要求在本章中包含以下角色的互动情节：\n"
            for character in selected_characters:
                character_info += f"角色名称：{character['name']}，角色背景关系：{character['background']}\n"
            character_info += "\n请在创作中安排这些角色与主角之间的互动，互动内容可以包括但不限于（战斗、聊天、谈情等）。"
        
        if feedback:
            prompt = f"{professional_background}\n根据另一位资深作家的反馈修改第{chapter_num}章的内容。\n\n小说整体要求：{user_prompt}\n\n前面章节内容：{previous_chapters}\n\n反馈意见：{feedback}{character_info}\n\n请提供第{chapter_num}章的标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：【第{chapter_num}章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 重点参考前面章节的情节发展，不要参考尚未发生的后续章节内容\n4. 角色名称要与前几章保持一致，不要串改角色名称"
        else:
            if previous_chapters:
                prompt = f"{professional_background}\n请为小说创作第{chapter_num}章的标题和梗概。\n\n小说整体要求：{user_prompt}\n\n前面章节内容：{previous_chapters}{character_info}\n\n请提供第{chapter_num}章的标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：【第{chapter_num}章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 重点参考前面章节的情节发展，不要参考尚未发生的后续章节内容\n4. 角色名称要与前几章保持一致，不要串改角色名称"
            else:
                prompt = f"{professional_background}\n请为小说创作第{chapter_num}章的标题和梗概。\n\n小说整体要求：{user_prompt}\n\n这是小说的开始章节{character_info}，请提供第{chapter_num}章的标题和约500字的梗概，并列出本章出现的角色及其背景关系。请严格按照以下格式输出：【第{chapter_num}章： 章节标题】\n【梗概内容： XXX】\n【本章出现角色：\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n<角色名称：xxx,角色说明(包括角色能力，社会关系，与主角之间关系等等描述内容)>\n...\n】\n***其它说明或描述内容***\nXXX...\n\n注意事项：\n1. 必须严格遵循小说整体要求进行创作\n2. 确保章节内容与小说整体风格和设定保持一致\n3. 角色名称要与前几章保持一致，不要串改角色名称"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            # 获取最新加载的模型实例
            self.llm = self.model_manager.get_model(self.local_model_path)
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=2000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error: {str(e)}"
    
    def evaluate_chapter_outline(self, outline, user_prompt, previous_chapters=""):
        """
        评估章节大纲
        """
        # 添加专业背景设定
        professional_background = "你是一位专业的网文小说编辑，有20年以上的编辑经验，擅长评估各种类型的小说章节大纲，具有敏锐的文学洞察力和丰富的市场经验。"
        
        # 构造评估提示
        prompt = f"{professional_background}\n请评估以下章节大纲：\n\n{outline}\n\n小说整体要求：{user_prompt}\n\n前面章节内容：{previous_chapters}\n\n请从以下三个核心维度进行重点评估：\n1. 角色名称一致性：检查主角、配角的名字是否与前几章保持一致，没有被串改\n2. 情节连贯性：评估与前面章节的情节衔接是否自然流畅，逻辑是否连贯\n3. 创新性：评估情节或物品设定是否有足够的创新性，是否能够使读者感到'脑洞'大开\n\n评分标准（满分10分）：\n- 9.0分以上：大纲质量优秀，可以直接使用\n- 8.0-8.9分：大纲质量良好，稍作修改即可使用\n- 7.0-7.9分：大纲质量一般，需要修改\n- 7.0分以下：大纲质量较差，需要大幅修改\n\n特别注意：\n1. 在角色名称一致性对比时，要对比至少前两个章节（第一章、第二章除外）\n2. 第一章着重参考小说整体要求\n3. 第二章则要参考第一章梗概与小说整体要求\n4. 必须确保所有角色名称在整个小说中保持一致\n5. 重点参考前面章节的情节发展，不要参考尚未发生的后续章节内容\n\n请严格按照以下格式输出：\n【最终评分：XX分】\n【评价内容：“XXX”】\n【改进意见：“XXX”】\n***其它说明或描述内容***\n评分必须严格按照10分制标准，评分范围为0-10分，保留一位小数。"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            # 获取最新加载的模型实例
            self.llm = self.model_manager.get_model(self.local_model_path)
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=800,
                    temperature=0.5
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error: {str(e)}"

    def _generate_with_local_model(self, prompt):
        """
        使用本地模型生成内容
        """
        try:
            # 使用llama.cpp生成内容
            output = self.llm(
                prompt,
                max_tokens=2000,
                temperature=0.7,
                echo=False
            )
            
            # 提取生成的文本
            if 'choices' in output and len(output['choices']) > 0:
                generated_text = output['choices'][0]['text']
            else:
                generated_text = ""
            
            return generated_text
        except Exception as e:
            return f"Local model error occurred: {str(e)}"


class AIReader:
    def __init__(self, api_key=None, model='qwen-plus', use_local=False, local_model_path=None):
        self.model = model
        self.use_local = use_local
        self.local_model_path = local_model_path
        self.llm = None
        self.model_manager = GlobalModelManager()
        if api_key and not use_local:
            dashscope.api_key = api_key
        elif use_local and local_model_path:
            # 异步初始化llama.cpp模型
            self.llm = self.model_manager.load_model_async(local_model_path)

    def wait_for_model(self, timeout=30, progress_callback=None):
        """
        等待模型加载完成
        """
        if not self.use_local or not self.local_model_path:
            return True
            
        if self.llm:
            return True
            
        # 如果有进度回调，启动加载过程
        if progress_callback:
            self.llm = self.model_manager.load_model_async(self.local_model_path, progress_callback)
        else:
            # 确保模型开始加载
            self.llm = self.model_manager.load_model_async(self.local_model_path)
            
        # 等待模型加载完成
        if self.llm is None:
            self.llm = self.model_manager.wait_for_model(self.local_model_path, timeout)
        return self.llm is not None

    def review_content(self, content):
        professional_background = "你是一位专业的网文小说编辑，有丰富的文学鉴赏能力，能够准确指出作品的优缺点。"
        prompt = f"{professional_background}\n请评价以下小说内容：{content}\n\n请从情节吸引力、文字表达、逻辑性等方面进行评价，并给出1-10分的评分。请严格按照以下格式输出：【最终评分：X.X分】\n【评价内容:\nXXX】"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=1000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error occurred: {str(e)}"
    
    def evaluate_content(self, content):
        """
        评估章节内容，返回评分和建议
        """
        professional_background = "你是一位专业的网文小说读者，有丰富的网络文学阅读经验，能够准确评价作品的优劣。"
        prompt = f"{professional_background}\n请评价以下小说内容：{content}\n\n请从情节吸引力、文字表达、节奏控制等方面进行评价，并给出1-10分的评分。如果评分低于9.5分，请给出具体的修改建议。\n\n请严格按照以下格式输出：\n【最终评分：x.x分（10分为满分）】\n【评价内容：\nXXXX】"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=1000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error occurred: {str(e)}"
    
    def _generate_with_local_model(self, prompt):
        """
        使用本地模型生成内容
        """
        try:
            # 使用llama.cpp生成内容
            output = self.llm(
                prompt,
                max_tokens=500,
                temperature=0.3,
                echo=False
            )
            
            # 提取生成的文本
            if 'choices' in output and len(output['choices']) > 0:
                generated_text = output['choices'][0]['text']
            else:
                generated_text = ""
            
            return generated_text
        except Exception as e:
            return f"Local model error occurred: {str(e)}"


class AIEditor:
    def __init__(self, api_key=None, model='qwen-plus', use_local=False, local_model_path=None):
        self.model = model
        self.use_local = use_local
        self.local_model_path = local_model_path
        self.llm = None
        self.model_manager = GlobalModelManager()
        if api_key and not use_local:
            dashscope.api_key = api_key
        elif use_local and local_model_path:
            # 异步初始化llama.cpp模型
            self.llm = self.model_manager.load_model_async(local_model_path)

    def wait_for_model(self, timeout=30, progress_callback=None):
        """
        等待模型加载完成
        """
        if not self.use_local or not self.local_model_path:
            return True
            
        if self.llm:
            return True
            
        # 如果有进度回调，启动加载过程
        if progress_callback:
            self.llm = self.model_manager.load_model_async(self.local_model_path, progress_callback)
        else:
            # 确保模型开始加载
            self.llm = self.model_manager.load_model_async(self.local_model_path)
            
        # 等待模型加载完成
        if self.llm is None:
            self.llm = self.model_manager.wait_for_model(self.local_model_path, timeout)
        return self.llm is not None

    def edit_content(self, original_content, review_comments):
        professional_background = "你是一位专业的网文小说编辑，有丰富的文学编辑经验，能够根据评价意见对作品进行修改完善。"
        prompt = f"{professional_background}\n原文内容：{original_content}\n\n评价意见：{review_comments}\n\n请根据评价意见修改原文内容，使作品更加优秀。请严格按照原文格式输出修改后的内容。"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=2000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error occurred: {str(e)}"
    
    def review_content(self, content):
        """
        审核内容并给出最终意见
        """
        professional_background = "你是一位专业的网文小说编辑，有丰富的文学编辑经验，能够判断作品是否符合出版要求。"
        prompt = f"{professional_background}\n请审核以下小说内容是否符合出版要求：{content}\n\n请从情节合理性、文字表达、逻辑性、是否符合网文规范等方面进行审核。如果内容符合要求，请回复【最终审核结果：审核通过】，否则请回复【最终审核结果：审核不通过】，并给出具体原因和修改建议。"
        
        if self.use_local and self.local_model_path:
            # 等待模型加载完成
            if not self.wait_for_model():
                return "Error: Model loading timeout"
                
            if self.llm:
                # 使用本地模型
                return self._generate_with_local_model(prompt)
            else:
                return "Error: Failed to load local model"
        else:
            # 使用在线API
            try:
                response = Generation.call(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=1000,
                    temperature=0.7
                )
                if response.status_code == 200:
                    return response.output.text
                else:
                    return f"Error: {response.message}"
            except Exception as e:
                return f"Error occurred: {str(e)}"
    
    def _generate_with_local_model(self, prompt):
        """
        使用本地模型生成内容
        """
        try:
            # 使用llama.cpp生成内容
            output = self.llm(
                prompt,
                max_tokens=800,
                temperature=0.7,
                stop=["***"],
                echo=False
            )
            
            # 提取生成的文本
            generated_text = output["choices"][0]["text"]
            
            # 移除内容中的【】符号（如果有的话）
            if 'choices' in output and len(output['choices']) > 0:
                generated_text = output['choices'][0]['text']
                # 移除内容中的【】符号
                generated_text = re.sub(r'【', '(', generated_text)
                generated_text = re.sub(r'】', ')', generated_text)
            else:
                generated_text = ""
            
            return generated_text
        except Exception as e:
            return f"Local model error occurred: {str(e)}"
