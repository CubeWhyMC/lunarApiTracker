# 使用较轻的 Alpine 镜像
FROM python:3.13-alpine

# 安装 7z 和依赖库
RUN apk add --no-cache \
    p7zip \
    libmagic \
    && pip install --no-cache-dir pdm

# 复制 pyproject.toml 和 pdm.lock 到 /project/ 目录
COPY pyproject.toml pdm.lock /app/

# 复制整个项目到 /project/ 目录
COPY . /app/

# 设置工作目录
WORKDIR /app

# 安装项目依赖
RUN pdm install --check --prod --no-editable

# 设置容器启动时执行的命令
ENTRYPOINT ["pdm", "run", "python", "./main.py"]
