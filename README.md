# 复制小工具

> 本工具作用于两种情况：
> 1、源文件夹下YYMMDD子文件夹内文件移动到目标文件夹 
> 2、源文件夹下所有文件定时到目标文件夹

## 文件说明
```
copy.ini #配置文件
copy_tools.ico #程序图标（可选）
copy_tools.py #程序源代码
error.log #运行错误日志
log.txt #运行日志
```

## 配置说明

```
# 源路径
src_dir = 
# 目标路径
dst_dir = 
# 类型，1 为源路径下有格式为YYMMDD格式文件夹；2 为无需指向源路径下的子文件夹内
type = 
```

## 使用

### win

前往 Releases 下载压缩包，按要求完成 copy.ini 文件的配置，双击压缩包下的exe文件即可

### linux

下载 Releases 源码压缩包，按要求完成 copy.ini 文件的配置，运行 copy_tools.py 即可

## 注意事项

如linux执行py文件时，提醒缺少包请自行百度安装