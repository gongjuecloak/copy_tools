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
log.txt #运行日志
```

## 配置说明

```
[Basis]
# 源路径（路径最后无需斜杠）
src_dir = 
# 目标路径（路径最后无需斜杠）
dst_dir = 
# 类型，1 为源路径下有格式为YYMMDD格式文件夹；2 为无需指向源路径下的子文件夹内
type = 1
# 当文件夹为空时，程序的休息时间，需要大于执行时间，当小于时只会按执行时间进行，目前单位为秒，支持小数点
rest_time = 
# 程序执行时间，多久执行一次，目前单位为秒，支持小数点
execution_time = 
```

## 使用

### win

前往 [Releases](https://github.com/gongjuecloak/copy_tools/releases/) 下载win压缩包，按要求完成 copy.ini 文件的配置，双击压缩包下的exe文件即可

### linux

前往 [Releases](https://github.com/gongjuecloak/copy_tools/releases/) 下载linux压缩包，按要求完成 copy.ini 文件的配置，运行 copy_tools.py 即可

## 注意事项

如linux执行py文件时，提醒缺少包请自行百度安装