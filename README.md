# 文件自动移动工具
定时自动将文件从源目录移动到目标目录，支持 GUI 界面与命令行双模式。

## 如果本工具有帮助到您的话，请帮忙给个start谢谢！

> 本工具作用于两种情况：
> 1、源文件夹下YYMMDD子文件夹内文件移动到目标文件夹 
> 2、源文件夹下所有文件定时到目标文件夹

## 功能特性
1. 支持两种监控模式：
- 按日期子目录（YYYYMMDD）监控并移动文件
- 直接监控源目录并移动文件
2. 支持按文件扩展名、文件前缀过滤
3. 运行中配置文件热加载
4. 文件移动失败自动重试
5. 同名文件自动时间戳重命名
6. 完整日志输出 + 移动统计
7. 带 PyQt5 图形界面，无 GUI 时自动运行命令行模式

## 文件说明
```
copy_tools.py      # 主程序
copy.ini           # 配置文件
file_move_tool.log # 运行日志（自动生成）
README.md          # 说明文档
```

## 配置说明

```
[config]
# 源目录
src_dir = 
# 目标目录
dst_dir = 
# 监控类型：1=按日期子目录 2=直接监控源目录
type = 2
# 目录为空时休息时间（秒）
rest_time = 10.0
# 执行间隔（秒）
execution_time = 10.0
# 后缀过滤，逗号分隔，空=不过滤
file_extensions = .html
# 前缀过滤，逗号分隔，空=不过滤
file_prefixes =
```

## 使用

### win

前往 [Releases](https://github.com/gongjuecloak/copy_tools/releases/) 下载win压缩包，按要求完成 copy.ini 文件的配置，双击压缩包下的exe文件即可

### linux

前往 [Releases](https://github.com/gongjuecloak/copy_tools/releases/) 下载linux压缩包，按要求完成 copy.ini 文件的配置，运行 copy_tools.py 即可

## 注意事项

路径末尾不要加斜杠
确保源目录、目标目录有读写权限
Linux 下如缺少库请自行安装依赖
关闭窗口时会自动停止监控线程