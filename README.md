# 复制小工具

## 如果本工具有帮助到您的话，请帮忙给个start谢谢！

> 本工具作用于两种情况：
> 1、源文件夹下YYMMDD子文件夹内文件移动到目标文件夹 
> 2、源文件夹下所有文件定时到目标文件夹

## 文件说明
```
copy.ini #配置文件
copy_tools.ico #程序图标（可选）
copy_tools.py #程序源代码
```

## 配置说明

```
[file_config]
# 源路径（路径最后无需斜杠）
src_dir = 
# 目标路径（路径最后无需斜杠）
dst_dir = 
# 类型：1-按日期子目录监控 2-直接监控源目录
type = 2
# 源目录为空时的休息时间（秒）
rest_time = 120.5
# 执行/触发间隔（秒）
execution_time = 10
# 可选：文件过滤 - 仅移动指定后缀（多个用逗号分隔，空表示不过滤）
file_extensions = .html
# 可选：文件过滤 - 仅移动指定前缀（多个用逗号分隔，空表示不过滤）
file_prefixes = 
```

## 使用

### win

前往 [Releases](https://github.com/gongjuecloak/copy_tools/releases/) 下载win压缩包，按要求完成 copy.ini 文件的配置，双击压缩包下的exe文件即可

### linux

前往 [Releases](https://github.com/gongjuecloak/copy_tools/releases/) 下载linux压缩包，按要求完成 copy.ini 文件的配置，运行 copy_tools.py 即可

## 注意事项

如linux执行py文件时，提醒缺少包请自行百度安装