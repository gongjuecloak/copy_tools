import datetime
import time
import os
import sys
import shutil
import threading
import configparser
import logging
import argparse
from logging import handlers
from typing import Dict, Optional, List, Any
from dataclasses import dataclass

# ===================== GUI 相关导入 =====================
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
        QGroupBox, QGridLayout, QFileDialog, QMessageBox, QPlainTextEdit, QSplitter,
        QCheckBox, QStatusBar
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QDateTime, QMutex, QMutexLocker, QMetaObject, Q_ARG
    from PyQt5.QtGui import QFont, QIcon, QTextCursor
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    print("警告：未安装PyQt5，将使用命令行模式运行")

# ===================== 基础配置 =====================
# 获取代码文件所在的绝对目录
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认配置文件路径
DEFAULT_CONFIG_PATH = os.path.join(CODE_DIR, "copy.ini")
# 默认日志文件路径
LOG_FILE_PATH = os.path.join(CODE_DIR, "file_move_tool.log")
# 工具版本
TOOL_VERSION = "2.2.0 (最终修复版)"

# ===================== 数据类定义 =====================
@dataclass
class AppConfig:
    """应用配置数据类，提供类型提示和默认值"""
    src_dir: str
    dst_dir: str
    type: str
    rest_time: float
    execution_time: float
    file_extensions: str = ""
    file_prefixes: str = ""
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, str]) -> 'AppConfig':
        """从字典创建配置对象"""
        return cls(
            src_dir=config_dict.get('src_dir', ''),
            dst_dir=config_dict.get('dst_dir', ''),
            type=config_dict.get('type', '1'),
            rest_time=float(config_dict.get('rest_time', 60)),
            execution_time=float(config_dict.get('execution_time', 300)),
            file_extensions=config_dict.get('file_extensions', ''),
            file_prefixes=config_dict.get('file_prefixes', '')
        )
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典，用于保存配置"""
        return {
            'src_dir': self.src_dir,
            'dst_dir': self.dst_dir,
            'type': self.type,
            'rest_time': str(self.rest_time),
            'execution_time': str(self.execution_time),
            'file_extensions': self.file_extensions,
            'file_prefixes': self.file_prefixes
        }

# ===================== 日志工具类（修复GUI日志显示） =====================
class Logger:
    """优化后的日志工具类，支持单例模式和GUI日志输出"""
    _instance: Optional['Logger'] = None
    _lock = threading.Lock()
    # GUI日志信号（用于实时更新界面）
    log_signal = None
    
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }

    def __new__(cls, filename: str = LOG_FILE_PATH, level: str = 'info', 
                when: str = 'D', backup_count: int = 10, 
                max_bytes: int = 10*1024*1024, fmt: str = None):
        """单例模式创建日志实例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize(filename, level, when, backup_count, max_bytes, fmt)
            return cls._instance
    
    def _initialize(self, filename: str, level: str, when: str, 
                   backup_count: int, max_bytes: int, fmt: str):
        """初始化日志配置"""
        self.logger = logging.getLogger(filename)
        self.logger.handlers.clear()
        self.logger.setLevel(self.level_relations.get(level, logging.INFO))
        self.logger.propagate = False

        # 默认日志格式（包含线程名）
        if fmt is None:
            fmt = '%(asctime)s - %(threadName)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s'
        
        format_str = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

        # 控制台处理器
        sh = logging.StreamHandler()
        sh.setFormatter(format_str)
        self.logger.addHandler(sh)

        # 文件轮转处理器（10MB/文件，最多保留10个）
        th = handlers.RotatingFileHandler(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        th.setFormatter(format_str)
        self.logger.addHandler(th)
        
        # 自定义处理器（用于GUI日志输出 - 核心修复）
        class GuiLogHandler(logging.Handler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    # 直接发送信号，移除多余判断，确保信号能触发
                    if Logger.log_signal:
                        Logger.log_signal.emit(msg)
                except Exception as e:
                    # 记录处理器自身错误，避免吞异常
                    print(f"日志处理器错误: {str(e)}")
        
        gui_handler = GuiLogHandler()
        gui_handler.setFormatter(format_str)
        self.logger.addHandler(gui_handler)
    
    def set_log_signal(self, signal):
        """设置GUI日志信号"""
        Logger.log_signal = signal
    
    def __getattr__(self, name):
        """动态转发日志方法"""
        if name in ['debug', 'info', 'warning', 'error', 'critical', 'exception']:
            return getattr(self.logger, name)
        raise AttributeError(f"'Logger' object has no attribute '{name}'")

# ===================== 配置管理类 =====================
class ConfigManager:
    """配置管理类，统一处理配置的读取、验证和热加载"""
    
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, logger: Logger = None):
        self.config_path = config_path
        self.logger = logger or Logger()
        self.last_modified_time = 0.0
        self.current_config: Optional[AppConfig] = None
        self._mutex = QMutex()  # 使用QMutex保证线程安全
        self._config_loaded = False  # 标记配置是否已加载
    
    def load_config(self) -> AppConfig:
        """加载并验证配置（线程安全，避免重复加载）"""
        locker = QMutexLocker(self._mutex)
        
        # 避免重复加载
        if self._config_loaded and self.current_config is not None:
            return self.current_config
        
        # 检查配置文件是否存在
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件 {self.config_path} 不存在，请确认路径")
        
        # 读取配置文件
        config = configparser.ConfigParser()
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config.read_file(f)
        except configparser.Error as e:
            raise configparser.Error(f"配置文件解析错误: {str(e)}")
        
        # 转换为字典格式
        config_dict = {}
        for section in config.sections():
            for option in config[section]:
                config_dict[option] = config[section][option]
        
        # 验证配置合法性
        if not self._validate_config(config_dict):
            raise ValueError("配置参数验证失败，请检查配置文件")
        
        # 更新最后修改时间
        self.last_modified_time = os.path.getmtime(self.config_path)
        
        # 创建配置对象并返回
        self.current_config = AppConfig.from_dict(config_dict)
        self._config_loaded = True
        self.logger.info(f"配置文件加载成功: {self.config_path}")
        return self.current_config
    
    def save_config(self, config: AppConfig):
        """保存配置到文件"""
        locker = QMutexLocker(self._mutex)
        
        config_parser = configparser.ConfigParser()
        config_parser['config'] = config.to_dict()
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                config_parser.write(f)
            self.logger.info(f"配置已保存到: {self.config_path}")
            self.last_modified_time = os.path.getmtime(self.config_path)
            self._config_loaded = False  # 标记需要重新加载
        except Exception as e:
            self.logger.error(f"保存配置失败: {str(e)}")
            raise
    
    def _validate_config(self, config_dict: Dict[str, str]) -> bool:
        """验证配置合法性"""
        # 1. 检查必填字段
        required_fields = ['src_dir', 'dst_dir', 'type', 'rest_time', 'execution_time']
        missing_fields = [f for f in required_fields if f not in config_dict or not config_dict[f].strip()]
        if missing_fields:
            self.logger.error(f"缺失必填配置项: {', '.join(missing_fields)}")
            return False
        
        # 2. 验证类型配置（仅支持1或2）
        type_config = config_dict['type'].strip()
        if type_config not in ['1', '2']:
            self.logger.error(f"类型配置错误，仅支持1或2，当前值: {type_config}")
            return False
        
        # 3. 验证数值类型和范围
        try:
            rest_time = float(config_dict['rest_time'])
            exec_time = float(config_dict['execution_time'])
            if rest_time <= 0 or exec_time <= 0:
                self.logger.error("休息时间和执行时间必须大于0")
                return False
        except ValueError:
            self.logger.error("休息时间和执行时间必须为有效数字（支持小数）")
            return False
        
        # 4. 标准化路径格式
        if 'src_dir' in config_dict:
            config_dict['src_dir'] = config_dict['src_dir'].strip().rstrip('/\\')
        if 'dst_dir' in config_dict:
            config_dict['dst_dir'] = config_dict['dst_dir'].strip().rstrip('/\\')
        
        return True
    
    def check_for_updates(self) -> Optional[AppConfig]:
        """检查配置是否有更新（优化：降低检查频率，避免频繁IO）"""
        try:
            if not os.path.exists(self.config_path):
                return None
            
            current_mtime = os.path.getmtime(self.config_path)
            # 只有修改时间差异大于1秒才重新加载（避免频繁读取）
            if abs(current_mtime - self.last_modified_time) > 1:
                self.logger.info("检测到配置文件更新，开始重新加载")
                self._config_loaded = False  # 标记需要重新加载
                return self.load_config()
        except Exception as e:
            self.logger.error(f"检查配置更新失败: {str(e)}", exc_info=True)
        return None

# ===================== 文件操作类 =====================
class FileMover:
    """文件移动操作类，封装所有文件处理逻辑"""
    
    def __init__(self, config: AppConfig, logger: Logger = None):
        self.config = config
        self.logger = logger or Logger()
        self._mutex = QMutex()
        # 移动统计信息
        self.stats = {
            'total_files': 0,
            'success_files': 0,
            'failed_files': 0,
            'start_time': time.time()
        }
    
    def update_config(self, new_config: AppConfig):
        """更新配置（线程安全）"""
        locker = QMutexLocker(self._mutex)
        self.config = new_config
        self.logger.info("配置已更新，将使用新配置执行后续操作")
    
    def get_source_directory(self) -> str:
        """获取实际的源目录路径"""
        locker = QMutexLocker(self._mutex)
        if self.config.type == "1":
            current_date = datetime.datetime.now().strftime("%Y%m%d")
            return os.path.join(self.config.src_dir, current_date)
        return self.config.src_dir
    
    def is_directory_empty(self, dir_path: str) -> bool:
        """判断目录是否为空"""
        if not os.path.isdir(dir_path):
            return True
        try:
            return not any(os.scandir(dir_path))
        except PermissionError:
            self.logger.error(f"无权限访问目录: {dir_path}")
            return True
    
    def filter_files(self, file_list: List[str]) -> List[str]:
        """根据配置过滤文件"""
        locker = QMutexLocker(self._mutex)
        # 预处理过滤规则（支持带/不带点的扩展名）
        ext_rules = []
        if self.config.file_extensions:
            ext_rules = [e.strip().lower() for e in self.config.file_extensions.split(",") if e.strip()]
            ext_rules = [f".{ext}" if not ext.startswith('.') else ext for ext in ext_rules]
        
        prefix_rules = []
        if self.config.file_prefixes:
            prefix_rules = [p.strip() for p in self.config.file_prefixes.split(",") if p.strip()]
        
        locker.unlock()  # 提前解锁，避免阻塞
        
        # 无过滤规则时返回原列表
        if not ext_rules and not prefix_rules:
            return file_list
        
        # 执行过滤
        filtered_files = []
        for filename in file_list:
            if filename.endswith(('.tmp', '~', '.swp', '.bak')):
                continue
            
            # 扩展名过滤
            if ext_rules:
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in ext_rules:
                    continue
            
            # 前缀过滤
            if prefix_rules and not any(filename.startswith(p) for p in prefix_rules):
                continue
            
            filtered_files.append(filename)
        
        return filtered_files
    
    def move_single_file(self, src_file: str, dst_file: str, retry: int = 3) -> bool:
        """移动单个文件，带指数退避重试机制"""
        for attempt in range(retry):
            try:
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.move(src_file, dst_file)
                return True
            except PermissionError:
                wait_time = 0.5 * (attempt + 1)
                self.logger.warning(f"第{attempt+1}次移动失败（权限不足）: {src_file}，等待{wait_time}秒重试")
                # 使用QThread的msleep，避免阻塞
                QThread.msleep(int(wait_time * 1000))
            except Exception as e:
                wait_time = 0.5 * (attempt + 1)
                self.logger.warning(f"第{attempt+1}次移动失败: {src_file}，错误：{str(e)}，等待{wait_time}秒重试")
                QThread.msleep(int(wait_time * 1000))
        
        self.logger.error(f"移动文件失败（已重试{retry}次）: {src_file}")
        return False
    
    def move_files(self) -> None:
        """批量移动文件核心逻辑（优化：移除time.sleep，改用QThread延迟）"""
        src_dir = self.get_source_directory()
        dst_dir = self.config.dst_dir  # 修复：正确使用目标目录
        locker = QMutexLocker(self._mutex)
        rest_time = self.config.rest_time
        exec_time = self.config.execution_time
        locker.unlock()
        
        # 检查源目录是否存在
        if not os.path.isdir(src_dir):
            self.logger.warning(f"源目录不存在: {src_dir}")
            QThread.msleep(int(exec_time * 1000))
            return
        
        # 检查源目录是否为空
        if self.is_directory_empty(src_dir):
            self.logger.info(f"源目录为空: {src_dir}，休息 {rest_time} 秒")
            QThread.msleep(int(rest_time * 1000))
            return
        
        # 获取文件列表（仅文件，排除目录）
        try:
            file_list = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
        except PermissionError:
            self.logger.error(f"无权限访问源目录: {src_dir}")
            QThread.msleep(int(rest_time * 1000))
            return
        
        # 过滤文件
        filtered_files = self.filter_files(file_list)
        if not filtered_files:
            self.logger.info(f"源目录 {src_dir} 无符合过滤规则的文件，休息 {rest_time} 秒")
            QThread.msleep(int(rest_time * 1000))
            return
        
        # 执行批量移动
        total_files = len(filtered_files)
        success_count = 0
        fail_count = 0
        
        self.logger.info(f"开始移动文件，共 {total_files} 个符合条件的文件")
        
        for idx, filename in enumerate(filtered_files, 1):
            src_file = os.path.join(src_dir, filename)
            dst_file = os.path.join(dst_dir, filename)
            
            # 处理目标文件已存在的情况
            if os.path.exists(dst_file):
                name, ext = os.path.splitext(filename)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S_%f")[:-3]
                dst_file = os.path.join(dst_dir, f"{name}_{timestamp}{ext}")
                self.logger.debug(f"目标文件已存在，重命名为: {dst_file}")
            
            # 移动文件
            if self.move_single_file(src_file, dst_file):
                success_count += 1
                self.logger.debug(f"[{idx}/{total_files}] 成功移动: {src_file} -> {dst_file}")
            else:
                fail_count += 1
        
        # 更新统计信息
        locker = QMutexLocker(self._mutex)
        self.stats['total_files'] += total_files
        self.stats['success_files'] += success_count
        self.stats['failed_files'] += fail_count
        
        # 输出移动结果
        self.logger.info(f"文件移动完成 - 成功: {success_count}, 失败: {fail_count}, 总计: {total_files}")
        success_rate = self.stats['success_files']/max(self.stats['total_files'], 1)*100
        self.logger.info(f"累计统计 - 成功: {self.stats['success_files']}, 失败: {self.stats['failed_files']}, 成功率: {success_rate:.1f}%")

# ===================== 监控器线程类（修复卡死问题） =====================
class MonitorThread(QThread):
    """监控器线程，避免阻塞GUI主线程"""
    status_signal = pyqtSignal(str)  # 状态更新信号
    stats_signal = pyqtSignal(dict)  # 统计信息更新信号
    progress_signal = pyqtSignal(int)  # 进度更新信号
    
    def __init__(self, config_manager: ConfigManager, logger: Logger):
        super().__init__()
        self.config_manager = config_manager
        self.logger = logger
        self.file_mover = None
        self.is_running = False
        self.config = None
        self._mutex = QMutex()
    
    def run(self):
        """线程运行入口（优化：移除死循环阻塞，改用定时器式检查）"""
        try:
            # 加载初始配置（只加载一次）
            self.config = self.config_manager.load_config()
            self.file_mover = FileMover(self.config, self.logger)
            self.is_running = True
            
            self.status_signal.emit("监控已启动（轮询模式）")
            self.logger.info("文件移动工具启动成功（GUI修复版）")
            
            # 优化的轮询逻辑：每次循环只执行一次检查，避免死循环阻塞
            while self.is_running:
                if not self.is_running:
                    break
                    
                try:
                    # 执行文件移动（单次）
                    self.file_mover.move_files()
                    
                    # 检查配置更新（降低频率）
                    new_config = self.config_manager.check_for_updates()
                    if new_config:
                        self.config = new_config
                        self.file_mover.update_config(new_config)
                        self.status_signal.emit("配置已更新")
                    
                    # 发送统计信息
                    locker = QMutexLocker(self._mutex)
                    self.stats_signal.emit(self.file_mover.stats)
                    locker.unlock()
                    
                    # 关键修复：使用QThread的sleep，不阻塞Python GIL
                    # 每次等待前检查是否需要停止
                    wait_ms = int(self.config.execution_time * 1000)
                    wait_step = 100  # 每100ms检查一次是否停止
                    total_wait = 0
                    
                    while total_wait < wait_ms and self.is_running:
                        QThread.msleep(wait_step)
                        total_wait += wait_step
                    
                except Exception as e:
                    self.logger.error(f"轮询过程中发生错误: {str(e)}", exc_info=True)
                    self.status_signal.emit(f"运行错误: {str(e)}")
                    # 出错时等待10秒，但仍检查是否需要停止
                    QThread.msleep(10000)
                    
        except Exception as e:
            self.logger.error(f"监控线程启动失败: {str(e)}", exc_info=True)
            self.status_signal.emit(f"启动失败: {str(e)}")
            self.is_running = False
    
    def stop(self):
        """停止监控线程（优雅退出，避免卡死）"""
        locker = QMutexLocker(self._mutex)
        self.is_running = False
        locker.unlock()
        
        # 等待线程结束（最多5秒）
        self.wait(5000)
        
        self.status_signal.emit("监控已停止")
        self.logger.info("监控线程已停止（优雅退出）")

# ===================== GUI主窗口类（最终修复版） =====================
class FileMoveToolGUI(QMainWindow):
    """文件移动工具主窗口（修复所有已知问题）"""
    log_signal = pyqtSignal(str)  # 日志更新信号
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"文件自动移动工具 v{TOOL_VERSION}")
        self.setGeometry(100, 100, 1000, 700)
        
        # 初始化组件
        self.logger = Logger(level='info')
        self.logger.set_log_signal(self.log_signal)
        self.config_manager = ConfigManager(DEFAULT_CONFIG_PATH, self.logger)
        self.monitor_thread = None
        
        # 创建界面
        self._create_ui()
        
        # 直接连接日志信号（核心修复：确保信号连接不丢失）
        self.log_signal.connect(self._update_log)
        
        # 定时器更新状态（降低频率，避免资源占用）
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(2000)  # 每2秒更新一次
        
        # 尝试加载配置（只加载一次）
        self._load_config_to_ui()
    
    def _create_ui(self):
        """创建用户界面"""
        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 1. 配置标签页
        self._create_config_tab()
        
        # 2. 监控标签页
        self._create_monitor_tab()
        
        # 3. 日志标签页
        self._create_log_tab()
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 - 未启动监控")
    
    def _create_config_tab(self):
        """创建配置标签页"""
        config_widget = QWidget()
        self.tab_widget.addTab(config_widget, "配置管理")
        
        # 布局
        layout = QVBoxLayout(config_widget)
        
        # 配置组框
        config_group = QGroupBox("核心配置")
        layout.addWidget(config_group)
        
        # 网格布局
        grid_layout = QGridLayout(config_group)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(20, 20, 20, 20)
        
        # 源目录
        grid_layout.addWidget(QLabel("源目录:"), 0, 0)
        self.src_dir_edit = QLineEdit()
        self.src_dir_edit.setPlaceholderText("如：D:\\download")
        grid_layout.addWidget(self.src_dir_edit, 0, 1)
        src_dir_btn = QPushButton("浏览")
        src_dir_btn.clicked.connect(lambda: self._select_directory(self.src_dir_edit))
        grid_layout.addWidget(src_dir_btn, 0, 2)
        
        # 目标目录
        grid_layout.addWidget(QLabel("目标目录:"), 1, 0)
        self.dst_dir_edit = QLineEdit()
        self.dst_dir_edit.setPlaceholderText("如：E:\\archive")
        grid_layout.addWidget(self.dst_dir_edit, 1, 1)
        dst_dir_btn = QPushButton("浏览")
        dst_dir_btn.clicked.connect(lambda: self._select_directory(self.dst_dir_edit))
        grid_layout.addWidget(dst_dir_btn, 1, 2)
        
        # 监控类型
        grid_layout.addWidget(QLabel("监控类型:"), 2, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["按日期子目录监控（YYMMDD）", "直接监控源目录"])
        self.type_combo.setCurrentIndex(0)
        grid_layout.addWidget(self.type_combo, 2, 1, 1, 2)
        
        # 休息时间
        grid_layout.addWidget(QLabel("空目录休息时间（秒）:"), 3, 0)
        self.rest_time_spin = QDoubleSpinBox()
        self.rest_time_spin.setRange(1, 3600)
        self.rest_time_spin.setValue(60)
        self.rest_time_spin.setSingleStep(1)
        grid_layout.addWidget(self.rest_time_spin, 3, 1, 1, 2)
        
        # 执行间隔
        grid_layout.addWidget(QLabel("执行间隔（秒）:"), 4, 0)
        self.exec_time_spin = QDoubleSpinBox()
        self.exec_time_spin.setRange(1, 3600)
        self.exec_time_spin.setValue(300)
        self.exec_time_spin.setSingleStep(1)
        grid_layout.addWidget(self.exec_time_spin, 4, 1, 1, 2)
        
        # 文件扩展名过滤
        grid_layout.addWidget(QLabel("文件扩展名过滤:"), 5, 0)
        self.ext_edit = QLineEdit()
        self.ext_edit.setPlaceholderText("逗号分隔，如：mp4,txt（留空不过滤）")
        grid_layout.addWidget(self.ext_edit, 5, 1, 1, 2)
        
        # 文件前缀过滤
        grid_layout.addWidget(QLabel("文件前缀过滤:"), 6, 0)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("逗号分隔，如：order_,log_（留空不过滤）")
        grid_layout.addWidget(self.prefix_edit, 6, 1, 1, 2)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)
        
        self.save_config_btn = QPushButton("保存配置")
        self.save_config_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_config_btn)
        
        self.load_config_btn = QPushButton("加载配置")
        self.load_config_btn.clicked.connect(self._load_config_to_ui)
        btn_layout.addWidget(self.load_config_btn)
        
        btn_layout.addStretch()
    
    def _create_monitor_tab(self):
        """创建监控标签页"""
        monitor_widget = QWidget()
        self.tab_widget.addTab(monitor_widget, "运行监控")
        
        # 布局
        layout = QVBoxLayout(monitor_widget)
        
        # 控制按钮组
        control_group = QGroupBox("监控控制")
        layout.addWidget(control_group)
        
        control_layout = QHBoxLayout(control_group)
        
        self.start_btn = QPushButton("启动监控")
        self.start_btn.clicked.connect(self._start_monitor)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止监控")
        self.stop_btn.clicked.connect(self._stop_monitor)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        
        # 状态信息组
        status_group = QGroupBox("运行状态")
        layout.addWidget(status_group)
        
        status_layout = QGridLayout(status_group)
        
        # 基本状态
        status_layout.addWidget(QLabel("监控状态:"), 0, 0)
        self.status_label = QLabel("未启动")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.status_label, 0, 1)
        
        status_layout.addWidget(QLabel("当前监控目录:"), 1, 0)
        self.current_dir_label = QLabel("无")
        status_layout.addWidget(self.current_dir_label, 1, 1)
        
        # 统计信息
        status_layout.addWidget(QLabel("总计文件数:"), 2, 0)
        self.total_files_label = QLabel("0")
        status_layout.addWidget(self.total_files_label, 2, 1)
        
        status_layout.addWidget(QLabel("成功移动数:"), 3, 0)
        self.success_files_label = QLabel("0")
        self.success_files_label.setStyleSheet("color: green;")
        status_layout.addWidget(self.success_files_label, 3, 1)
        
        status_layout.addWidget(QLabel("失败移动数:"), 4, 0)
        self.failed_files_label = QLabel("0")
        self.failed_files_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.failed_files_label, 4, 1)
        
        status_layout.addWidget(QLabel("成功率:"), 5, 0)
        self.success_rate_label = QLabel("0%")
        status_layout.addWidget(self.success_rate_label, 5, 1)
        
        layout.addStretch()
    
    def _create_log_tab(self):
        """创建日志标签页"""
        log_widget = QWidget()
        self.tab_widget.addTab(log_widget, "日志查看")
        
        # 布局
        layout = QVBoxLayout(log_widget)
        
        # 日志显示区域
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # 日志控制按钮
        log_btn_layout = QHBoxLayout()
        layout.addLayout(log_btn_layout)
        
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_btn_layout.addWidget(clear_log_btn)
        
        save_log_btn = QPushButton("保存日志")
        save_log_btn.clicked.connect(self._save_log)
        log_btn_layout.addWidget(save_log_btn)
        
        log_btn_layout.addStretch()
    
    def _select_directory(self, line_edit):
        """选择目录并填充到输入框"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择目录")
        if dir_path:
            line_edit.setText(dir_path)
    
    def _load_config_to_ui(self):
        """加载配置到界面（只加载一次，避免重复）"""
        try:
            config = self.config_manager.load_config()
            self.src_dir_edit.setText(config.src_dir)
            self.dst_dir_edit.setText(config.dst_dir)
            self.type_combo.setCurrentIndex(0 if config.type == "1" else 1)
            self.rest_time_spin.setValue(config.rest_time)
            self.exec_time_spin.setValue(config.execution_time)
            self.ext_edit.setText(config.file_extensions)
            self.prefix_edit.setText(config.file_prefixes)
            
        except Exception as e:
            QMessageBox.warning(self, "警告", f"加载配置失败: {str(e)}\n将使用默认值")
    
    def _save_config(self):
        """保存界面配置到文件"""
        try:
            # 构建配置对象
            config = AppConfig(
                src_dir=self.src_dir_edit.text().strip(),
                dst_dir=self.dst_dir_edit.text().strip(),
                type="1" if self.type_combo.currentIndex() == 0 else "2",
                rest_time=self.rest_time_spin.value(),
                execution_time=self.exec_time_spin.value(),
                file_extensions=self.ext_edit.text().strip(),
                file_prefixes=self.prefix_edit.text().strip()
            )
            
            # 保存配置
            self.config_manager.save_config(config)
            
            # 更新当前监控目录显示
            self._update_current_dir()
            
            QMessageBox.information(self, "成功", "配置保存成功！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {str(e)}")
    
    def _start_monitor(self):
        """启动监控（修复：避免重复创建线程）"""
        if self.monitor_thread and self.monitor_thread.isRunning():
            QMessageBox.warning(self, "警告", "监控已在运行中！")
            return
        
        try:
            # 先保存配置
            self._save_config()
            
            # 创建监控线程（每次启动新建）
            self.monitor_thread = MonitorThread(self.config_manager, self.logger)
            self.monitor_thread.status_signal.connect(self._update_monitor_status)
            self.monitor_thread.stats_signal.connect(self._update_stats)
            
            # 启动线程
            self.monitor_thread.start()
            
            # 更新界面状态
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("运行中")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.status_bar.showMessage("监控运行中...")
            
            # 更新当前监控目录
            self._update_current_dir()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动监控失败: {str(e)}")
    
    def _stop_monitor(self):
        """停止监控（修复：确保线程完全停止）"""
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            # 等待线程结束
            self.monitor_thread.wait(2000)
        
        # 更新界面状态
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("已停止")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.status_bar.showMessage("监控已停止")
    
    def _update_monitor_status(self, status):
        """更新监控状态"""
        self.status_label.setText(status)
        self.status_bar.showMessage(status)
    
    def _update_stats(self, stats):
        """更新统计信息"""
        total = stats.get('total_files', 0)
        success = stats.get('success_files', 0)
        failed = stats.get('failed_files', 0)
        
        self.total_files_label.setText(str(total))
        self.success_files_label.setText(str(success))
        self.failed_files_label.setText(str(failed))
        
        if total > 0:
            rate = (success / total) * 100
            self.success_rate_label.setText(f"{rate:.1f}%")
        else:
            self.success_rate_label.setText("0%")
    
    def _update_current_dir(self):
        """更新当前监控目录显示"""
        try:
            config = self.config_manager.load_config()
            if config.type == "1":
                current_date = datetime.datetime.now().strftime("%Y%m%d")
                current_dir = os.path.join(config.src_dir, current_date)
            else:
                current_dir = config.src_dir
            self.current_dir_label.setText(current_dir)
        except:
            self.current_dir_label.setText("未知")
    
    def _update_log(self, log_msg):
        """更新日志显示（核心修复：简化逻辑，确保日志显示）"""
        # 直接在主线程更新日志，移除复杂的invokeMethod调用
        self.log_text.appendPlainText(log_msg)
        # 自动滚动到最后一行
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
    
    def _update_status(self):
        """定时更新状态（降低频率）"""
        if self.monitor_thread and self.monitor_thread.isRunning():
            self._update_current_dir()
    
    def _save_log(self):
        """保存日志到文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存日志", 
            f"file_move_tool_log_{QDateTime.currentDateTime().toString('yyyyMMddHHmmss')}.log",
            "Log Files (*.log);;All Files (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "成功", "日志保存成功！")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存日志失败: {str(e)}")
    
    def closeEvent(self, event):
        """窗口关闭事件（修复：确保线程完全停止）"""
        if self.monitor_thread and self.monitor_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认", "监控正在运行，是否停止并退出？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self._stop_monitor()
                # 等待线程结束
                self.monitor_thread.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# ===================== 工具函数 =====================
def print_version():
    """打印版本信息（移除功能特性展示）"""
    print("=" * 60)
    print(f"文件自动移动工具 v{TOOL_VERSION}")
    print("=" * 60)

def parse_command_line_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='文件自动移动工具 - 高性能、高可靠的文件迁移解决方案')
    parser.add_argument('-c', '--config', default=DEFAULT_CONFIG_PATH,
                       help=f'配置文件路径（默认：{DEFAULT_CONFIG_PATH}）')
    parser.add_argument('-l', '--log-level', default='info',
                       choices=['debug', 'info', 'warning', 'error', 'crit'],
                       help='日志级别（默认：info）')
    parser.add_argument('-v', '--version', action='store_true',
                       help='显示版本信息并退出')
    parser.add_argument('--no-gui', action='store_true',
                       help='强制使用命令行模式运行')
    return parser.parse_args()

# ===================== 主程序 =====================
def main():
    """程序主入口"""
    # 解析命令行参数
    args = parse_command_line_args()
    
    # 显示版本信息
    if args.version:
        print_version()
        sys.exit(0)
    
    # 初始化日志（指定日志级别）
    logger = Logger(level=args.log_level)
    
    try:
        # 打印版本信息
        print_version()
        
        # 判断是否使用GUI模式
        if QT_AVAILABLE and not args.no_gui:
            # GUI模式
            app = QApplication(sys.argv)
            app.setStyle('Fusion')  # 统一风格
            
            # 创建主窗口
            window = FileMoveToolGUI()
            window.show()
            
            # 运行应用
            sys.exit(app.exec_())
        else:
            # 命令行模式（保留原有逻辑）
            print("使用命令行模式运行...")
            # 初始化配置管理器
            config_manager = ConfigManager(args.config, logger)
            
            # 简单的命令行监控逻辑（避免卡死）
            config = config_manager.load_config()
            file_mover = FileMover(config, logger)
            
            print("监控已启动，按Ctrl+C停止...")
            try:
                while True:
                    file_mover.move_files()
                    time.sleep(config.execution_time)
            except KeyboardInterrupt:
                print("\n监控已停止")
        
    except FileNotFoundError as e:
        logger.critical(f"启动失败: {str(e)}")
        sys.exit(1)
    except configparser.Error as e:
        logger.critical(f"配置文件错误: {str(e)}")
        sys.exit(1)
    except ValueError as e:
        logger.critical(f"配置验证失败: {str(e)}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("用户手动终止程序")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"程序异常终止: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()