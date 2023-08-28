import datetime
import time
import os
import shutil
import configparser
import logging
import os.path
from logging import handlers

class Logger(object):
    level_relations = {
        'debug':logging.DEBUG,
        'info':logging.INFO,
        'warning':logging.WARNING,
        'error':logging.ERROR,
        'crit':logging.CRITICAL
    }#日志级别关系映射

    def __init__(self,filename,level='info',when='D',backCount=3,fmt='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s'):
        self.logger = logging.getLogger(filename)
        format_str = logging.Formatter(fmt)#设置日志格式
        self.logger.setLevel(self.level_relations.get(level))#设置日志级别
        sh = logging.StreamHandler()#往屏幕上输出
        sh.setFormatter(format_str) #设置屏幕上显示的格式
        th = handlers.TimedRotatingFileHandler(filename=filename,when=when,backupCount=backCount,encoding='utf-8')#往文件里写入#指定间隔时间自动生成文件的处理器
        #实例化TimedRotatingFileHandler
        #interval是时间间隔，backupCount是备份文件的个数，如果超过这个个数，就会自动删除，when是间隔的时间单位，单位有以下几种：
        # S 秒
        # M 分
        # H 小时、
        # D 天、
        # W 每星期（interval==0时代表星期一）
        # midnight 每天凌晨
        th.setFormatter(format_str)
        self.logger.addHandler(sh) 
        self.logger.addHandler(th)

def read_config_file(config_file_path):
	config = configparser.ConfigParser()
	config.read_file(open(config_file_path))
	variables = {}
	for section in config.sections():
		for option in config[section]:
			variables[option] = config[section][option]
	return variables

def copy_file():
	now = time.time()
	current_date = time.strftime("%y%m%d", time.localtime(now))
	variables = read_config_file("copy.ini")
	log_dir_path = "log.txt"
	
	log = Logger(log_dir_path,level='debug')
	
	log.logger.info(time_printer())
	
	error_log = Logger('error.log', level='error')
	
	if variables["type"] == "1":
			src_dir = variables["src_dir"] + '/' + current_date
	elif variables["type"] == "2":
			src_dir = variables["src_dir"] + '/'
	elif variables["type"] != "1" or variables["type"] != "3":
			error_log.logger.error("类型填写错误，请检查配置")
			exit(1)
	dst_dir = variables["dst_dir"]
	if not os.path.isdir(src_dir):
		error_log.logger.error("源文件路径不存在，请检查配置")
		exit(1)
	elif not os.path.isdir(dst_dir):
		error_log.logger.error("目标路径不存在，请检查配置")
		exit(1)
	for file_name in os.listdir(src_dir):
			src_file = os.path.join(src_dir, file_name)
			dst_file = os.path.join(dst_dir, file_name)
			shutil.move(src_file, dst_file)
			log.logger.info("移动文件：" + src_file + " --> " + dst_file)
	
def time_printer():
	now = datetime.datetime.now()
	ts = now.strftime('%Y-%m-%d %H:%M:%S')
	return "执行时间:" + ts
	
def loop_monitor():
	while True:
			copy_file()
			time.sleep(5)

def tools_version():
	t_version = "1.0.0"
	print("欢迎使用Cloak的复制工具\n")
	print("当前版本:" + t_version + "\n")
			
if __name__ == "__main__":
	tools_version()
	loop_monitor()