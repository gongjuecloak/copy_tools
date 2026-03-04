import datetime
import time
import os
import sys
import shutil
import configparser
import logging
from logging import handlers
from typing import Dict, Optional

# 获取代码文件所在的绝对目录（关键：不再依赖运行时的工作目录）
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认配置文件路径（和代码文件同目录）
DEFAULT_CONFIG_PATH = os.path.join(CODE_DIR, "copy.ini")
LOG_FILE_PATH = os.path.join(CODE_DIR, "log.txt")

class Logger:
    """日志工具类，提供文件和控制台日志输出"""
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }

    def __init__(self, filename: str, level: str = 'info', when: str = 'D', 
                 backup_count: int = 3, 
                 fmt: str = '%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s'):
        # 避免重复添加处理器
        self.logger = logging.getLogger(filename)
        self.logger.handlers.clear()
        self.logger.setLevel(self.level_relations.get(level, logging.INFO))
        self.logger.propagate = False

        # 设置日志格式
        format_str = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

        # 控制台处理器
        sh = logging.StreamHandler()
        sh.setFormatter(format_str)
        self.logger.addHandler(sh)

        # 文件轮转处理器
        th = handlers.TimedRotatingFileHandler(
            filename=filename,
            when=when,
            backupCount=backup_count,
            encoding='utf-8'
        )
        th.setFormatter(format_str)
        self.logger.addHandler(th)

def read_config_file(config_file_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, str]:
    """
    读取配置文件，返回配置参数字典
    
    Args:
        config_file_path: 配置文件路径
    
    Returns:
        配置参数字典
    
    Raises:
        FileNotFoundError: 配置文件不存在
        configparser.Error: 配置文件解析错误
    """
    # 检查配置文件是否存在
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"配置文件 {config_file_path} 不存在，请确认文件路径")
    
    config = configparser.ConfigParser()
    # 使用with语句自动管理文件句柄
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config.read_file(f)
    except configparser.Error as e:
        raise configparser.Error(f"配置文件解析错误: {str(e)}")

    variables = {}
    # 修正拼写错误：sections()而非Basiss()
    for section in config.sections():
        for option in config[section]:
            variables[option] = config[section][option]
    return variables

def validate_config(config: Dict[str, str], logger: Logger) -> bool:
    """
    校验配置参数的合法性
    
    Args:
        config: 配置参数字典
        logger: 日志实例
    
    Returns:
        True: 配置合法，False: 配置不合法
    """
    # 1. 检查必填参数是否缺失
    required_fields = ['src_dir', 'dst_dir', 'type', 'rest_time', 'execution_time']
    missing_fields = [field for field in required_fields if field not in config or not config[field].strip()]
    if missing_fields:
        logger.logger.error(f"配置文件缺失必填参数: {', '.join(missing_fields)}")
        return False
    
    # 2. 检查type是否为1或2
    type_config = config['type'].strip()
    if type_config not in ['1', '2']:
        logger.logger.error(f"类型配置错误，仅支持1或2，当前值: {type_config}")
        return False
    
    # 3. 检查时间参数是否为合法数字
    try:
        rest_time = float(config['rest_time'].strip())
        execution_time = float(config['execution_time'].strip())
    except ValueError:
        logger.logger.error("休息时间或执行时间必须为数字（支持小数点）")
        return False
    
    # 4. 检查时间参数是否为正数
    if rest_time <= 0 or execution_time <= 0:
        logger.logger.error("休息时间和执行时间必须大于0")
        return False
    
    # 5. 提示rest_time小于execution_time的情况
    if rest_time < execution_time:
        logger.logger.warning(f"休息时间({rest_time}秒)小于执行时间({execution_time}秒)，将按执行时间执行")
    
    # 6. 检查源路径和目标路径格式（去除末尾斜杠/反斜杠，统一格式）
    config['src_dir'] = config['src_dir'].strip().rstrip('/\\')
    config['dst_dir'] = config['dst_dir'].strip().rstrip('/\\')
    
    logger.logger.info("配置参数校验通过")
    return True

def is_directory_empty(dir_path: str) -> bool:
    """
    判断目录是否为空
    
    Args:
        dir_path: 目录路径
    
    Returns:
        True: 空目录，False: 非空目录
    """
    if not os.path.isdir(dir_path):
        return True
    return not any(os.scandir(dir_path))

def move_files(src_dir: str, dst_dir: str, logger: Logger) -> None:
    """
    移动目录下的所有文件到目标目录，处理文件重名问题
    
    Args:
        src_dir: 源目录路径
        dst_dir: 目标目录路径
        logger: 日志实例
    """
    if not os.listdir(src_dir):
        logger.logger.info(f"源目录 {src_dir} 为空，无文件可移动")
        return

    for file_name in os.listdir(src_dir):
        src_file = os.path.join(src_dir, file_name)
        dst_file = os.path.join(dst_dir, file_name)

        # 跳过子目录，只处理文件
        if os.path.isdir(src_file):
            logger.logger.warning(f"跳过子目录: {src_file}")
            continue

        # 处理目标文件已存在的情况
        if os.path.exists(dst_file):
            # 添加时间戳避免覆盖
            file_name, ext = os.path.splitext(file_name)
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            dst_file = os.path.join(dst_dir, f"{file_name}_{timestamp}{ext}")
            logger.logger.warning(f"目标文件已存在，重命名为: {dst_file}")

        try:
            # 使用move移动文件，添加异常捕获
            shutil.move(src_file, dst_file)
            logger.logger.info(f"成功移动文件: {src_file} --> {dst_file}")
        except PermissionError:
            logger.logger.error(f"权限不足，无法移动文件: {src_file}")
        except Exception as e:
            logger.logger.error(f"移动文件失败 {src_file}: {str(e)}")

def copy_file(config: Dict[str, str], logger: Logger) -> None:
    """
    核心文件移动逻辑
    
    Args:
        config: 配置参数字典
        logger: 日志实例
    """
    try:
        # 获取当前日期
        current_date = time.strftime("%Y%m%d", time.localtime())
        
        # 确定源目录路径
        type_config = config.get("type", "")
        src_dir_base = config.get("src_dir", "")
        
        if type_config == "1":
            src_dir = os.path.join(src_dir_base, current_date)
        elif type_config == "2":
            src_dir = src_dir_base
        else:
            logger.logger.error(f"无效的类型配置: {type_config}，仅支持1或2")
            return

        dst_dir = config.get("dst_dir", "")
        rest_time = float(config.get("rest_time", 60))  # 默认休息60秒
        execution_time = float(config.get("execution_time", 300))
        
        # 验证目录是否存在
        if not os.path.isdir(src_dir):
            logger.logger.error(f"源目录不存在: {src_dir}")
            # 类型1时，可能是当日目录还未创建，仅警告不退出
            if type_config == "1":
                logger.logger.warning(f"类型1配置下，当日目录({src_dir})尚未创建，等待下次执行")
                time.sleep(execution_time)
            return
        
        if not os.path.isdir(dst_dir):
            logger.logger.error(f"目标目录不存在: {dst_dir}")
            return
        
        # 检查源目录是否为空
        if is_directory_empty(src_dir):
            logger.logger.info(f"源目录为空，休息 {rest_time} 秒后继续")
            time.sleep(rest_time)
            return
        
        # 执行文件移动
        move_files(src_dir, dst_dir, logger)
        
    except Exception as e:
        logger.logger.error(f"执行文件移动时发生错误: {str(e)}")

def loop_monitor(config: Dict[str, str], logger: Logger) -> None:
    """
    循环监控并执行文件移动
    
    Args:
        config: 配置参数字典
        logger: 日志实例
    """
    execution_interval = float(config.get("execution_time", 300))  # 默认5分钟
    logger.logger.info(f"开始循环监控，执行间隔: {execution_interval} 秒")
    
    while True:
        copy_file(config, logger)
        logger.logger.info(f"等待 {execution_interval} 秒后执行下一次检查")
        time.sleep(execution_interval)

def tools_version() -> None:
    """打印工具版本信息"""
    t_version = "1.1.0"
    print("=" * 50)
    print("欢迎使用Cloak的复制工具")
    print(f"当前版本: {t_version}")
    print("=" * 50)

def main(config_path: str = DEFAULT_CONFIG_PATH):
    """
    程序主入口
    
    Args:
        config_path: 配置文件路径（可选，默认和代码同目录）
    """
    # 初始化日志
    logger = Logger(LOG_FILE_PATH, level='debug')
    
    try:
        # 打印版本信息
        tools_version()
        
        # 读取配置（只读取一次，提升效率）
        logger.logger.info(f"尝试读取配置文件: {config_path}")
        config = read_config_file(config_path)
        
        # 校验配置合法性
        if not validate_config(config, logger):
            logger.logger.critical("配置参数不合法，程序退出")
            sys.exit(1)
        
        # 启动循环监控
        loop_monitor(config, logger)
        
    except FileNotFoundError as e:
        logger.logger.critical(f"启动失败: {str(e)}")
        sys.exit(1)
    except configparser.Error as e:
        logger.logger.critical(f"启动失败: {str(e)}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.logger.info("用户手动终止程序")
        sys.exit(0)
    except Exception as e:
        logger.logger.critical(f"程序异常终止: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # 支持命令行指定配置文件路径（可选）
    # 示例：python copy_tools.py "D:/my_config/copy.ini"
    if len(sys.argv) > 1:
        main(config_path=sys.argv[1])
    else:
        main()