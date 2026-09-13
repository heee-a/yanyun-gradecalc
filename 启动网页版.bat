@echo off
chcp 65001 >nul
title 燕云十六声装备毕业度计算器 - 网页版
cd /d %~dp0
echo 正在启动网页版（关闭本窗口即停止服务）...
python -m yanyun_gradecalc.web
pause
