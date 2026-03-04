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

# ===================== 基础配置 =====================
# 获取代码文件所在的绝对目录
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认配置文件路径
DEFAULT_CONFIG_PATH = os.path.join(CODE_DIR, "copy.ini")
# 默认日志文件路径
LOG_FILE_PATH = os.path.join(CODE_DIR, "file_move_tool.log")
# 工具版本
TOOL_VERSION = "2.2.0 (优化版)"

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

# ===================== 日志工具类 =====================
class Logger:
    """优化后的日志工具类，支持单例模式"""
    _instance: Optional['Logger'] = None
    _lock = threading.Lock()
    
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
        self._lock = threading.Lock()
    
    def load_config(self) -> AppConfig:
        """加载并验证配置"""
        with self._lock:
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
            self.logger.info(f"配置文件加载成功: {self.config_path}")
            return self.current_config
    
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
            # 提示休息时间小于执行时间的情况
            if rest_time < exec_time:
                self.logger.warning(f"休息时间({rest_time}秒)小于执行时间({exec_time}秒)，可能影响执行效率")
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
        """检查配置是否有更新"""
        try:
            if not os.path.exists(self.config_path):
                return None
            
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self.last_modified_time:
                self.logger.info("检测到配置文件更新，开始重新加载")
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
        self._lock = threading.Lock()
        # 移动统计信息
        self.stats = {
            'total_files': 0,
            'success_files': 0,
            'failed_files': 0,
            'start_time': time.time()
        }
    
    def update_config(self, new_config: AppConfig):
        """更新配置（线程安全）"""
        with self._lock:
            self.config = new_config
            self.logger.info("配置已更新，将使用新配置执行后续操作")
    
    def get_source_directory(self) -> str:
        """获取实际的源目录路径"""
        with self._lock:
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
        with self._lock:
            # 预处理过滤规则（支持带/不带点的扩展名）
            ext_rules = []
            if self.config.file_extensions:
                ext_rules = [e.strip().lower() for e in self.config.file_extensions.split(",") if e.strip()]
                # 统一添加点前缀
                ext_rules = [f".{ext}" if not ext.startswith('.') else ext for ext in ext_rules]
            
            prefix_rules = []
            if self.config.file_prefixes:
                prefix_rules = [p.strip() for p in self.config.file_prefixes.split(",") if p.strip()]
        
        # 无过滤规则时返回原列表
        if not ext_rules and not prefix_rules:
            return file_list
        
        # 执行过滤
        filtered_files = []
        for filename in file_list:
            # 跳过临时文件
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
                # 确保目标目录存在
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                
                # 原子操作移动文件
                shutil.move(src_file, dst_file)
                return True
            except PermissionError:
                wait_time = 0.5 * (attempt + 1)  # 指数退避：0.5s → 1s → 1.5s
                self.logger.warning(f"第{attempt+1}次移动失败（权限不足）: {src_file}，等待{wait_time}秒重试")
                time.sleep(wait_time)
            except Exception as e:
                wait_time = 0.5 * (attempt + 1)
                self.logger.warning(f"第{attempt+1}次移动失败: {src_file}，错误：{str(e)}，等待{wait_time}秒重试")
                time.sleep(wait_time)
        
        self.logger.error(f"移动文件失败（已重试{retry}次）: {src_file}")
        return False
    
    def move_files(self) -> None:
        """批量移动文件核心逻辑"""
        src_dir = self.get_source_directory()
        dst_dir = self.config.dst_dir
        
        # 检查源目录是否存在
        if not os.path.isdir(src_dir):
            self.logger.warning(f"源目录不存在: {src_dir}")
            time.sleep(self.config.execution_time)
            return
        
        # 检查源目录是否为空
        if self.is_directory_empty(src_dir):
            self.logger.info(f"源目录为空: {src_dir}，休息 {self.config.rest_time} 秒")
            time.sleep(self.config.rest_time)
            return
        
        # 获取文件列表（仅文件，排除目录）
        try:
            file_list = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
        except PermissionError:
            self.logger.error(f"无权限访问源目录: {src_dir}")
            time.sleep(self.config.rest_time)
            return
        
        # 过滤文件
        filtered_files = self.filter_files(file_list)
        if not filtered_files:
            self.logger.info(f"源目录 {src_dir} 无符合过滤规则的文件，休息 {self.config.rest_time} 秒")
            time.sleep(self.config.rest_time)
            return
        
        # 执行批量移动
        total_files = len(filtered_files)
        success_count = 0
        fail_count = 0
        
        self.logger.info(f"开始移动文件，共 {total_files} 个符合条件的文件")
        
        for idx, filename in enumerate(filtered_files, 1):
            src_file = os.path.join(src_dir, filename)
            dst_file = os.path.join(dst_dir, filename)
            
            # 处理目标文件已存在的情况（毫秒级时间戳避免冲突）
            if os.path.exists(dst_file):
                name, ext = os.path.splitext(filename)
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S_%f")[:-3]  # 毫秒级
                dst_file = os.path.join(dst_dir, f"{name}_{timestamp}{ext}")
                self.logger.debug(f"目标文件已存在，重命名为: {dst_file}")
            
            # 移动文件
            if self.move_single_file(src_file, dst_file):
                success_count += 1
                self.logger.debug(f"[{idx}/{total_files}] 成功移动: {src_file} -> {dst_file}")
            else:
                fail_count += 1
        
        # 更新统计信息
        with self._lock:
            self.stats['total_files'] += total_files
            self.stats['success_files'] += success_count
            self.stats['failed_files'] += fail_count
        
        # 输出移动结果
        self.logger.info(f"文件移动完成 - 成功: {success_count}, 失败: {fail_count}, 总计: {total_files}")
        self.logger.info(f"累计统计 - 成功: {self.stats['success_files']}, 失败: {self.stats['failed_files']}, "
                        f"成功率: {self.stats['success_files']/max(self.stats['total_files'], 1)*100:.1f}%")

# ===================== 监控器类 =====================
class FileMonitor:
    """文件监控器，统一管理监控逻辑"""
    
    def __init__(self, config_manager: ConfigManager, logger: Logger = None):
        self.config_manager = config_manager
        self.logger = logger or Logger()
        self.file_mover: Optional[FileMover] = None
        self.observer = None
        self.is_running = False
        self.start_time = time.time()
        self._lock = threading.Lock()  # 修复：添加锁对象定义
        
        # 加载初始配置
        self.config = config_manager.load_config()
        self.file_mover = FileMover(self.config, self.logger)
    
    def start(self):
        """启动监控"""
        self.is_running = True
        self.start_time = time.time()
        self.logger.info("文件移动工具启动成功")
        
        # 尝试使用watchdog监控（高性能），失败则降级为轮询模式
        try:
            self._start_watchdog_monitor()
        except ImportError:
            self.logger.warning("未安装watchdog库，将使用轮询模式（性能稍低）")
            self._start_polling_monitor()
    
    def _start_watchdog_monitor(self):
        """启动watchdog监控（事件驱动）"""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        
        class MonitorHandler(FileSystemEventHandler):
            """文件系统事件处理器（避免频繁触发）"""
            def __init__(self, monitor: 'FileMonitor'):
                self.monitor = monitor
                self.last_trigger = 0.0
                self.timer = None
                self._lock = threading.Lock()
            
            def on_created(self, event):
                self._handle_event(event)
            
            def on_modified(self, event):
                self._handle_event(event)
            
            def _handle_event(self, event):
                """处理文件事件，实现防抖机制"""
                # 过滤目录和临时文件
                if event.is_directory or event.src_path.endswith(('.tmp', '~', '.swp', '.bak')):
                    return
                
                with self._lock:
                    now = time.time()
                    interval = self.monitor.config.execution_time
                    
                    # 取消之前的定时器（防抖）
                    if self.timer and self.timer.is_alive():
                        self.timer.cancel()
                    
                    # 设置新的定时器
                    if now - self.last_trigger < interval:
                        # 延迟执行，确保批量文件都能被处理
                        delay = interval - (now - self.last_trigger)
                        self.timer = threading.Timer(delay, self.monitor.file_mover.move_files)
                        self.timer.start()
                        # 修复：使用monitor的logger而不是self.logger
                        self.monitor.logger.debug(f"检测到文件变化，将在{delay:.1f}秒后处理")
                    else:
                        # 立即执行
                        self.last_trigger = now
                        threading.Thread(target=self.monitor.file_mover.move_files, 
                                       name="FileMoveThread").start()
        
        # 确定监控目录
        with self._lock:
            if self.config.type == "1":
                monitor_dir = os.path.dirname(self.config.src_dir) if self.config.src_dir else ""
            else:
                monitor_dir = self.config.src_dir
        
        # 检查监控目录
        if not monitor_dir or not os.path.isdir(monitor_dir):
            self.logger.error(f"监控目录不存在或无效: {monitor_dir}")
            self.is_running = False
            return
        
        # 启动监控器
        self.observer = Observer()
        handler = MonitorHandler(self)
        self.observer.schedule(handler, monitor_dir, recursive=True)
        self.observer.daemon = True  # 守护线程，主程序退出时自动关闭
        self.observer.start()
        
        self.logger.info(f"Watchdog监控已启动，监控目录: {monitor_dir}")
        self.logger.info(f"触发间隔: {self.config.execution_time} 秒（批量文件将统一处理）")
        
        # 主线程循环（处理配置更新和状态输出）
        self._main_loop()
    
    def _start_polling_monitor(self):
        """启动轮询监控（兼容模式）"""
        self.logger.info(f"轮询监控已启动，执行间隔: {self.config.execution_time} 秒")
        
        # 轮询主循环
        while self.is_running:
            try:
                # 执行文件移动
                self.file_mover.move_files()
                
                # 检查配置更新（每分钟一次）
                new_config = self.config_manager.check_for_updates()
                if new_config:
                    self.config = new_config
                    self.file_mover.update_config(new_config)
                
                # 定时输出运行状态（每小时）
                if time.time() - self.start_time >= 3600:
                    self._print_status()
                    self.start_time = time.time()
                
                # 等待下一次执行
                self.logger.debug(f"等待 {self.config.execution_time} 秒后执行下一次检查")
                time.sleep(self.config.execution_time)
                
            except KeyboardInterrupt:
                self.logger.info("接收到用户终止信号，准备退出")
                self.is_running = False
            except Exception as e:
                self.logger.error(f"轮询过程中发生错误: {str(e)}", exc_info=True)
                time.sleep(10)  # 出错时短暂等待，避免无限循环报错
    
    def _main_loop(self):
        """主循环，处理配置更新和状态输出"""
        last_status_time = self.start_time
        config_check_interval = 60  # 每分钟检查一次配置更新
        
        while self.is_running:
            try:
                time.sleep(1)
                
                # 检查配置更新
                if time.time() - last_status_time >= config_check_interval:
                    new_config = self.config_manager.check_for_updates()
                    if new_config:
                        self.config = new_config
                        self.file_mover.update_config(new_config)
                
                # 定时输出运行状态（每小时）
                if time.time() - last_status_time >= 3600:
                    self._print_status()
                    last_status_time = time.time()
                    
            except KeyboardInterrupt:
                self.logger.info("接收到用户终止信号，准备退出")
                self.stop()
    
    def _print_status(self):
        """输出运行状态信息"""
        uptime = time.time() - self.start_time
        uptime_str = f"{int(uptime//3600)}h {int((uptime%3600)//60)}m {int(uptime%60)}s"
        
        # 确定监控目录
        with self._lock:
            if self.config.type == "1":
                monitor_dir = os.path.dirname(self.config.src_dir) if self.config.src_dir else ""
            else:
                monitor_dir = self.config.src_dir
        
        # 组装状态信息
        stats = self.file_mover.stats
        success_rate = stats['success_files'] / max(stats['total_files'], 1) * 100
        
        status_info = f"""
===== 运行状态 [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] =====
启动时间: {datetime.datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S')}
运行时长: {uptime_str}
监控目录: {monitor_dir}
目标目录: {self.config.dst_dir}
执行间隔: {self.config.execution_time} 秒
文件过滤: 后缀[{self.config.file_extensions}] 前缀[{self.config.file_prefixes}]
移动统计: 总计 {stats['total_files']} 个，成功 {stats['success_files']} 个，失败 {stats['failed_files']} 个
成功率: {success_rate:.1f}%
===========================================
        """
        self.logger.info(status_info)
    
    def stop(self):
        """停止监控（优雅退出）"""
        self.is_running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        self.logger.info("文件移动工具已停止运行")
        self._print_status()  # 退出前输出最终状态

# ===================== 工具函数 =====================
def print_version():
    """打印版本信息"""
    print("=" * 60)
    print(f"文件自动移动工具 v{TOOL_VERSION}")
    print("功能特性：")
    print("  1. 支持按日期子目录或直接监控")
    print("  2. 支持文件扩展名/前缀过滤")
    print("  3. 配置文件热加载")
    print("  4. 批量文件处理防抖机制")
    print("  5. 完整的移动统计和状态输出")
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
        
        # 初始化配置管理器
        config_manager = ConfigManager(args.config, logger)
        
        # 启动监控器
        monitor = FileMonitor(config_manager, logger)
        monitor.start()
        
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