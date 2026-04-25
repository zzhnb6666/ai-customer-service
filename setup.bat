@echo off
chcp 65001 >nul
echo ========================================
echo   AI 智能客服系统 - 一键启动
echo ========================================
echo.

:: Check .env file
if not exist ".env" (
    echo [提示] 未找到 .env 文件，从模板复制...
    copy .env.example .env
    echo [重要] 请编辑 .env 文件填入你的配置！
    echo.
    pause
    exit /b 1
)

:: Check Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Docker，请先安装 Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

echo [1/2] 构建并启动服务...
docker-compose up -d --build

echo.
echo [2/2] 检查服务状态...
timeout /t 5 /nobreak >nul
docker-compose ps

echo.
echo ========================================
echo  启动完成！
echo.
echo   健康检查: http://localhost:8000/health
echo   API 文档: http://localhost:8000/docs
echo.
echo   停止服务: docker-compose down
echo ========================================
pause
