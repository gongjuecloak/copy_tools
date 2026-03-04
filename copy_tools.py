import datetime
import time
import os
import sys
import shutil
import threading
import configparser
import logging
from logging import handlers
from typing import Dict, Optional, List
from dataclasses import dataclass

# ===================== PyQt5 核心导入 =====================
QT_AVAILABLE = False
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QPlainTextEdit, QComboBox, QDoubleSpinBox,
        QGroupBox, QGridLayout, QFileDialog, QMessageBox, QStatusBar, QTextBrowser
    )
    from PyQt5.QtCore import (
        Qt, QThread, pyqtSignal, QTimer, QMutex, QMutexLocker, QObject
    )
    from PyQt5.QtGui import QFont, QTextCursor
    QT_AVAILABLE = True
except ImportError:
    class QObject: pass
    class QMutex:
        def __init__(self): self._lock=threading.Lock()
        def lock(self): self._lock.acquire()
        def unlock(self): self._lock.release()
    class QMutexLocker:
        def __init__(self,m): self.m=m; self.m.lock()
        def __del__(self): self.m.unlock()
    class QThread:
        @staticmethod
        def msleep(ms): time.sleep(ms/1000)
    class pyqtSignal:
        def __init__(self,*a): pass
        def connect(self,f): pass
        def emit(self,*a): pass
    print("警告：未安装PyQt5，使用命令行模式")

# ===================== 基础路径 =====================
def get_program_dir():
    if getattr(sys,'frozen',False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__)) if __file__ else os.getcwd()

CONFIG_FILE_PATH = os.path.join(get_program_dir(), "config.ini")
DEFAULT_LOG_FILE_PATH = os.path.join(get_program_dir(), "file_move_tool.log")

# ===================== 配置检查 =====================
def check_config_file_exists() -> bool:
    return os.path.exists(CONFIG_FILE_PATH)

def validate_config_file() -> bool:
    if not check_config_file_exists():
        return False
    try:
        c = configparser.ConfigParser()
        c.read(CONFIG_FILE_PATH,encoding='utf-8')
        req = ['src_dir','dst_dir','type','rest_time','execution_time']
        if 'config' not in c: return False
        for f in req:
            if f not in c['config'] or not c['config'][f].strip():
                return False
        float(c['config']['rest_time'])
        float(c['config']['execution_time'])
        return True
    except:
        return False

# ===================== 配置结构体 =====================
@dataclass
class AppConfig:
    src_dir:str
    dst_dir:str
    type:str
    rest_time:float
    execution_time:float
    file_extensions:str=""
    file_prefixes:str=""
    log_file_path:str=""

    @classmethod
    def from_dict(cls,d:dict):
        return cls(
            src_dir=d.get('src_dir',''),
            dst_dir=d.get('dst_dir',''),
            type=d.get('type','1'),
            rest_time=float(d.get('rest_time',60)),
            execution_time=float(d.get('execution_time',300)),
            file_extensions=d.get('file_extensions',''),
            file_prefixes=d.get('file_prefixes',''),
            log_file_path=d.get('log_file_path','')
        )
    def to_dict(self):
        return {
            'src_dir':self.src_dir,
            'dst_dir':self.dst_dir,
            'type':self.type,
            'rest_time':str(self.rest_time),
            'execution_time':str(self.execution_time),
            'file_extensions':self.file_extensions,
            'file_prefixes':self.file_prefixes,
            'log_file_path':self.log_file_path
        }

# ===================== 日志类（修复信号 + 界面显示） =====================
class LogEmitter(QObject):
    log_signal = pyqtSignal(str)

class Logger:
    _instance = None
    _lock = threading.Lock()
    level_map = {
        'debug':logging.DEBUG,
        'info':logging.INFO,
        'warning':logging.WARNING,
        'error':logging.ERROR,
        'crit':logging.CRITICAL
    }

    def __init__(self,level='info',log_path=None):
        self.log_path = log_path or DEFAULT_LOG_FILE_PATH
        self.level = level
        self.emitter = LogEmitter()
        self.log_signal = self.emitter.log_signal
        self._init_logger()

    def _init_logger(self):
        self.logger = logging.getLogger(self.log_path)
        self.logger.handlers.clear()
        self.logger.setLevel(self.level_map.get(self.level,logging.INFO))
        self.logger.propagate = False

        fmt = '%(asctime)s - %(levelname)s: %(message)s'
        formatter = logging.Formatter(fmt,datefmt='%Y-%m-%d %H:%M:%S')

        # 控制台
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        self.logger.addHandler(sh)

        # 文件
        os.makedirs(os.path.dirname(self.log_path),exist_ok=True)
        fh = handlers.RotatingFileHandler(
            self.log_path,maxBytes=10*1024*1024,backupCount=5,encoding='utf-8'
        )
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        # GUI 输出
        class GuiHandler(logging.Handler):
            def __init__(self,emitter):
                super().__init__()
                self.emitter = emitter
            def emit(self,record):
                msg = self.format(record)
                self.emitter.log_signal.emit(msg)

        gh = GuiHandler(self.emitter)
        gh.setFormatter(formatter)
        self.logger.addHandler(gh)

    @classmethod
    def get_instance(cls,level='info',log_path=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = Logger(level,log_path)
            return cls._instance

    def __getattr__(self,name):
        return getattr(self.logger,name)

# ===================== 配置管理器 =====================
class ConfigManager:
    def __init__(self,logger=None):
        self.path = CONFIG_FILE_PATH
        self.logger = logger or Logger.get_instance()
        self.mtx = QMutex()
        self.cfg = None
        self.mtime = 0

    def load(self):
        with QMutexLocker(self.mtx):
            if not check_config_file_exists():
                raise FileNotFoundError("config.ini 不存在")
            if not validate_config_file():
                raise ValueError("配置无效")
            c = configparser.ConfigParser()
            c.read(self.path,encoding='utf-8')
            self.cfg = AppConfig.from_dict(c['config'])
            self.mtime = os.path.getmtime(self.path)
            return self.cfg

    def save(self,cfg:AppConfig):
        with QMutexLocker(self.mtx):
            c = configparser.ConfigParser()
            c['config'] = cfg.to_dict()
            with open(self.path,'w',encoding='utf-8') as f:
                c.write(f)
            self.mtime = os.path.getmtime(self.path)
            self.logger.info("配置已保存")

    def check_update(self):
        try:
            if not check_config_file_exists(): return None
            if os.path.getmtime(self.path)!=self.mtime:
                return self.load()
        except: pass
        return None

# ===================== 文件移动 =====================
class FileMover:
    def __init__(self,cfg,logger=None):
        self.cfg = cfg
        self.logger = logger or Logger.get_instance()
        self.mtx = QMutex()
        self.stats = {'total':0,'success':0,'fail':0}

    def update_cfg(self,cfg):
        with QMutexLocker(self.mtx): self.cfg=cfg

    def src_dir(self):
        with QMutexLocker(self.mtx):
            if self.cfg.type=="1":
                date = datetime.datetime.now().strftime("%Y%m%d")
                return os.path.join(self.cfg.src_dir,date)
            return self.cfg.src_dir

    def move(self):
        src = self.src_dir()
        with QMutexLocker(self.mtx):
            dst = self.cfg.dst_dir
            rest = self.cfg.rest_time
            inte = self.cfg.execution_time
            exts = [e.strip().lower() for e in self.cfg.file_extensions.split(',') if e.strip()]
            pres = [p.strip() for p in self.cfg.file_prefixes.split(',') if p.strip()]

        if not os.path.isdir(src):
            self.logger.warning(f"源目录不存在: {src}")
            QThread.msleep(int(inte*1000))
            return

        files = []
        try:
            files = [f for f in os.listdir(src) if os.path.isfile(os.path.join(src,f))]
        except:
            self.logger.error(f"无法读取目录: {src}")
            QThread.msleep(int(rest*1000))
            return

        if not files:
            self.logger.info(f"目录为空，休息 {rest}s")
            QThread.msleep(int(rest*1000))
            return

        ok=0
        ng=0
        for f in files:
            skip=False
            if exts:
                e = os.path.splitext(f)[1].lower()
                if not any(e==x or e=='.'+x.lstrip('.') for x in exts):
                    skip=True
            if pres and not any(f.startswith(p) for p in pres):
                skip=True
            if skip: continue

            s = os.path.join(src,f)
            t = os.path.join(dst,f)
            if os.path.exists(t):
                n,e = os.path.splitext(f)
                t = os.path.join(dst,f"{n}_{int(time.time())}{e}")
            try:
                os.makedirs(dst,exist_ok=True)
                shutil.move(s,t)
                ok+=1
                self.logger.debug(f"移动: {f}")
            except:
                ng+=1
                self.logger.error(f"失败: {f}")

        self.logger.info(f"本轮完成 成功:{ok} 失败:{ng}")
        with QMutexLocker(self.mtx):
            self.stats['total']+=ok+ng
            self.stats['success']+=ok
            self.stats['fail']+=ng
        QThread.msleep(int(inte*1000))

# ===================== 监控线程 =====================
class MonitorThread(QThread):
    status = pyqtSignal(str)
    stats = pyqtSignal(dict)
    def __init__(self,cm,logger):
        super().__init__()
        self.cm = cm
        self.logger = logger
        self.running = False
        self.mover = None

    def run(self):
        try:
            cfg = self.cm.load()
            self.mover = FileMover(cfg,self.logger)
            self.running=True
            self.status.emit("运行中")
            self.logger.info("监控启动")
            while self.running:
                self.mover.move()
                new = self.cm.check_update()
                if new:
                    self.mover.update_cfg(new)
                    self.status.emit("配置已更新")
                self.stats.emit(self.mover.stats)
        except Exception as e:
            self.logger.error(f"异常: {e}")
            self.status.emit(f"异常: {e}")
        finally:
            self.running=False

    def stop(self):
        self.running=False
        if self.isRunning():
            self.wait(3000)

# ===================== GUI =====================
class GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文件自动移动工具")
        self.setGeometry(100,100,950,700)
        self.logger = Logger.get_instance()
        self.cm = ConfigManager(self.logger)
        self.thread = None

        self.ui = QWidget()
        self.setCentralWidget(self.ui)
        self.ly = QVBoxLayout(self.ui)

        self.tab = QTabWidget()
        self.ly.addWidget(self.tab)

        self.tab_cfg = QWidget()
        self.tab_mon = QWidget()
        self.tab_log = QWidget()
        self.tab_help = QWidget()  # 帮助中心

        self.tab.addTab(self.tab_cfg,"配置")
        self.tab.addTab(self.tab_mon,"监控")
        self.tab.addTab(self.tab_log,"日志")
        self.tab.addTab(self.tab_help,"帮助中心")

        self._build_cfg()
        self._build_mon()
        self._build_log()
        self._build_help()

        # 日志绑定界面
        self.logger.log_signal.connect(self.append_log)

        self.sta = QStatusBar()
        self.setStatusBar(self.sta)

        if check_config_file_exists() and validate_config_file():
            self._load_cfg()
            self.btn_start.setEnabled(True)
        else:
            self.sta.showMessage("请先配置并保存")

    def _build_cfg(self):
        ly = QVBoxLayout(self.tab_cfg)
        g = QGroupBox("核心配置")
        ly.addWidget(g)
        grid = QGridLayout(g)

        grid.addWidget(QLabel("源目录:"),0,0)
        self.ed_src = QLineEdit()
        grid.addWidget(self.ed_src,0,1)
        btn_src = QPushButton("浏览")
        btn_src.clicked.connect(lambda: self._dir(self.ed_src))
        grid.addWidget(btn_src,0,2)

        grid.addWidget(QLabel("目标目录:"),1,0)
        self.ed_dst = QLineEdit()
        grid.addWidget(self.ed_dst,1,1)
        btn_dst = QPushButton("浏览")
        btn_dst.clicked.connect(lambda: self._dir(self.ed_dst))
        grid.addWidget(btn_dst,1,2)

        grid.addWidget(QLabel("监控模式:"),2,0)
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["按日期子目录","直接监控源目录"])
        grid.addWidget(self.cb_mode,2,1,1,2)

        grid.addWidget(QLabel("空目录休息(s):"),3,0)
        self.sb_rest = QDoubleSpinBox()
        self.sb_rest.setRange(1,3600)
        self.sb_rest.setValue(30)
        grid.addWidget(self.sb_rest,3,1,1,2)

        grid.addWidget(QLabel("执行间隔(s):"),4,0)
        self.sb_int = QDoubleSpinBox()
        self.sb_int.setRange(1,3600)
        self.sb_int.setValue(10)
        grid.addWidget(self.sb_int,4,1,1,2)

        grid.addWidget(QLabel("后缀过滤(逗号分隔):"),5,0)
        self.ed_ext = QLineEdit()
        grid.addWidget(self.ed_ext,5,1,1,2)

        grid.addWidget(QLabel("前缀过滤:"),6,0)
        self.ed_pre = QLineEdit()
        grid.addWidget(self.ed_pre,6,1,1,2)

        h = QHBoxLayout()
        ly.addLayout(h)
        btn_save = QPushButton("保存配置")
        btn_save.clicked.connect(self._save)
        h.addWidget(btn_save)
        btn_load = QPushButton("加载配置")
        btn_load.clicked.connect(self._load_cfg)
        h.addWidget(btn_load)

    def _build_mon(self):
        ly = QVBoxLayout(self.tab_mon)
        g = QGroupBox("控制")
        ly.addWidget(g)
        h = QHBoxLayout(g)
        self.btn_start = QPushButton("启动监控")
        self.btn_start.clicked.connect(self._start)
        h.addWidget(self.btn_start)
        self.btn_stop = QPushButton("停止监控")
        self.btn_stop.clicked.connect(self._stop)
        h.addWidget(self.btn_stop)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)

        g2 = QGroupBox("状态")
        ly.addWidget(g2)
        gr = QGridLayout(g2)
        gr.addWidget(QLabel("状态:"),0,0)
        self.lb_sta = QLabel("未启动")
        self.lb_sta.setStyleSheet("color:red")
        gr.addWidget(self.lb_sta,0,1)
        gr.addWidget(QLabel("总计文件:"),1,0)
        self.lb_t = QLabel("0")
        gr.addWidget(self.lb_t,1,1)
        gr.addWidget(QLabel("成功移动:"),2,0)
        self.lb_s = QLabel("0")
        gr.addWidget(self.lb_s,2,1)
        gr.addWidget(QLabel("移动失败:"),3,0)
        self.lb_f = QLabel("0")
        gr.addWidget(self.lb_f,3,1)
        ly.addStretch()

    def _build_log(self):
        ly = QVBoxLayout(self.tab_log)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas",10))
        ly.addWidget(self.txt_log)
        h = QHBoxLayout()
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self.txt_log.clear)
        h.addWidget(btn_clear)
        ly.addLayout(h)

    # ===================== 帮助中心界面 =====================
    def _build_help(self):
        ly = QVBoxLayout(self.tab_help)
        help_text = QTextBrowser()
        help_text.setStyleSheet("font-size:14px; padding:10px;")
        help_text.setOpenExternalLinks(False)
        
        help_html = """
        <h2>📘 文件自动移动工具 - 使用帮助</h2>
        <p>本工具用于自动监控目录，并按规则将文件移动到目标位置，支持按日期目录、过滤文件等功能。</p>
        <hr>
        
        <h3>一、源目录</h3>
        <p>需要被监控的文件夹，工具会自动扫描这里的文件。</p>
        
        <h3>二、目标目录</h3>
        <p>文件最终要移动到的文件夹，工具会自动创建不存在的目录。</p>
        
        <h3>三、监控模式</h3>
        <p><b>按日期子目录</b>：自动在源目录下找当天日期文件夹（如 20250101）<br>
        <b>直接监控源目录</b>：不按日期，直接监控填写的源目录</p>
        
        <h3>四、空目录休息时间</h3>
        <p>当目录里没有文件时，工具休眠多久再继续扫描，单位：秒。</p>
        
        <h3>五、执行间隔</h3>
        <p>每轮移动完成后，等待多久再进行下一轮扫描，单位：秒。</p>
        
        <h3>六、后缀过滤</h3>
        <p>只移动指定后缀的文件，多个用英文逗号分隔。<br>
        例：<code>txt,mp4,docx</code></p>
        
        <h3>七、前缀过滤</h3>
        <p>只移动文件名以指定字符开头的文件，多个用英文逗号分隔。<br>
        例：<code>data_,log_</code></p>
        
        <h3>八、使用流程</h3>
        <ol>
            <li>填写配置</li>
            <li>点击【保存配置】</li>
            <li>点击【启动监控】</li>
            <li>在【日志】页面查看运行情况</li>
        </ol>
        
        <h3>九、常见问题</h3>
        <p><b>Q：文件不动？</b><br>
        A：检查目录是否正确、权限是否足够、过滤规则是否太严格。</p>
        
        <p><b>Q：重复文件怎么办？</b><br>
        A：工具会自动重命名，不会覆盖。</p>
        """
        
        help_text.setHtml(help_html)
        ly.addWidget(help_text)

    def _dir(self,ed):
        d = QFileDialog.getExistingDirectory()
        if d: ed.setText(d)

    def _save(self):
        try:
            cfg = AppConfig(
                src_dir=self.ed_src.text().strip(),
                dst_dir=self.ed_dst.text().strip(),
                type="1" if self.cb_mode.currentIndex()==0 else "2",
                rest_time=self.sb_rest.value(),
                execution_time=self.sb_int.value(),
                file_extensions=self.ed_ext.text().strip(),
                file_prefixes=self.ed_pre.text().strip()
            )
            if not cfg.src_dir or not cfg.dst_dir:
                QMessageBox.warning(self,"","目录不能为空")
                return
            self.cm.save(cfg)
            self.btn_start.setEnabled(True)
            QMessageBox.information(self,"","保存成功")
        except Exception as e:
            QMessageBox.critical(self,"",str(e))

    def _load_cfg(self):
        try:
            c = self.cm.load()
            self.ed_src.setText(c.src_dir)
            self.ed_dst.setText(c.dst_dir)
            self.cb_mode.setCurrentIndex(0 if c.type=="1" else 1)
            self.sb_rest.setValue(c.rest_time)
            self.sb_int.setValue(c.execution_time)
            self.ed_ext.setText(c.file_extensions)
            self.ed_pre.setText(c.file_prefixes)
        except Exception as e:
            QMessageBox.warning(self,"",str(e))

    def _start(self):
        if self.thread and self.thread.isRunning(): return
        self.thread = MonitorThread(self.cm,self.logger)
        self.thread.status.connect(self._on_sta)
        self.thread.stats.connect(self._on_stat)
        self.thread.finished.connect(self._on_finish)
        self.thread.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lb_sta.setText("运行中")
        self.lb_sta.setStyleSheet("color:green")

    def _stop(self):
        if self.thread:
            self.thread.stop()

    def _on_sta(self,s):
        self.lb_sta.setText(s)
        self.sta.showMessage(s)

    def _on_stat(self,d):
        self.lb_t.setText(str(d['total']))
        self.lb_s.setText(str(d['success']))
        self.lb_f.setText(str(d['fail']))

    def _on_finish(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lb_sta.setText("已停止")
        self.lb_sta.setStyleSheet("color:red")

    def append_log(self,msg):
        self.txt_log.appendPlainText(msg)
        c = self.txt_log.textCursor()
        c.movePosition(QTextCursor.End)
        self.txt_log.setTextCursor(c)

    def closeEvent(self,e):
        if self.thread and self.thread.isRunning():
            r = QMessageBox.question(self,"","监控运行中，确定退出？")
            if r!=QMessageBox.Yes:
                e.ignore()
                return
            self.thread.stop()
        e.accept()

# ===================== 入口 =====================
def main():
    logging.basicConfig(level=logging.WARNING)
    if QT_AVAILABLE:
        app = QApplication(sys.argv)
        w = GUI()
        w.show()
        sys.exit(app.exec_())
    else:
        print("请先安装PyQt5：pip install pyqt5")

if __name__ == '__main__':
    main()