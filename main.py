from apscheduler.schedulers.blocking import BlockingScheduler
import requests
import hashlib
import os
import yaml
from yaml import CLoader as Loader
from loguru import logger
import sys
from DownloadKit import DownloadKit
import subprocess
import shutil
from asar import AsarArchive
import re
import difflib
from datetime import datetime

# 目录定义
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
TMP_DIR = os.path.join(FILES_DIR, "tmp")
EXTRACTED_DIR = os.path.join(TMP_DIR, "extracted")
ASAR_DIR = os.path.join(TMP_DIR, "asar")
OPENAPI_DIR = os.path.join(BASE_DIR, "openapi")
HASH_FILE = os.path.join(FILES_DIR, "latest.yml.sha256")
HISTORY_FILE = os.path.join(FILES_DIR, "openapi_history.txt")

# 确保目录存在
for directory in [FILES_DIR, TMP_DIR, EXTRACTED_DIR, OPENAPI_DIR]:
    os.makedirs(directory, exist_ok=True)

def download(url, path):
    """ 下载文件 """
    os.makedirs(path, exist_ok=True)  # 确保目录存在
    logger.info(f"开始下载: {url}")
    DownloadKit(path).download(url)

def read_js_files(path):
    """ 递归获取所有 .js 文件路径 """
    js_files = []
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".js"):
                js_path = os.path.join(root, file)
                js_files.append(js_path)
                logger.info(f"找到 JS 文件: {js_path}")
    return js_files

def generate_patch(old_file, new_file, patch_file):
    """ 生成文本 diff 补丁文件 """
    logger.info(f"生成补丁: {patch_file}")
    with open(old_file, 'r', encoding='utf-8') as f1, open(new_file, 'r', encoding='utf-8') as f2:
        diff_lines = list(difflib.unified_diff(
            f1.readlines(), f2.readlines(),
            fromfile=old_file, tofile=new_file
        ))
    
    if diff_lines:
        with open(patch_file, 'w', encoding='utf-8') as f_patch:
            f_patch.writelines(diff_lines)
        logger.info(f"补丁文件生成完成: {patch_file}")
    else:
        logger.info("没有变化，不生成补丁")

def extract_package(content):
    """ 解析 `latest.yml` 并下载解压 7z 和 asar """
    logger.debug("解析配置文件")
    config = yaml.load(content, Loader)

    # 下载 package
    package_url = f"https://launcherupdates.lunarclientcdn.com/{config['packages']['x64']['path']}"
    download(package_url, TMP_DIR)

    # 解压 7z
    package_file = os.path.join(TMP_DIR, config['packages']['x64']['file'])
    cmd = ["7z", "x", package_file, f"-o{EXTRACTED_DIR}", "-y"]
    subprocess.run(cmd)
    logger.info("7z 解压完成")

    # 解包 asar
    asar_file = os.path.join(EXTRACTED_DIR, "resources/app.asar")
    with AsarArchive.open(asar_file) as archive:
        archive.extract(ASAR_DIR)

    # 处理 openapi
    for js in read_js_files(os.path.join(ASAR_DIR, "dist-electron/electron")):
        with open(js, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r"https://api.lunarclient(dev|prod).com/[a-f0-9]+/openapi", content)
            if match:
                openapi_url = match.group()
                logger.info(f"发现 openapi: {openapi_url}")

                # 生成新 openapi 文件名
                timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                new_openapi_file = os.path.join(OPENAPI_DIR, f"openapi-{timestamp}.json")

                # 下载 openapi
                download(openapi_url, OPENAPI_DIR)
                os.rename(os.path.join(OPENAPI_DIR, "openapi"), new_openapi_file)

                # **更新 openapi-latest.json**
                latest_openapi_file = os.path.join(OPENAPI_DIR, "openapi-latest.json")
                shutil.copy(new_openapi_file, latest_openapi_file)

                # 读取上一次下载的 openapi
                last_openapi_file = None
                if os.path.exists(HISTORY_FILE):
                    with open(HISTORY_FILE, "r") as history:
                        last_openapi_file = history.readline().strip()

                # 生成补丁文件（如果存在上一次的 openapi）
                if last_openapi_file and os.path.exists(last_openapi_file):
                    patch_file = os.path.join(OPENAPI_DIR, f"patch-{timestamp}.diff")
                    generate_patch(last_openapi_file, new_openapi_file, patch_file)

                    # **更新 patch-latest.diff**
                    latest_patch_file = os.path.join(OPENAPI_DIR, "patch-latest.diff")
                    if os.path.exists(patch_file):
                        shutil.copy(patch_file, latest_patch_file)
                    else:
                        try:
                            os.remove(latest_patch_file)
                        except FileNotFoundError:
                            pass  # 文件不存在时忽略错误
                        except Exception as e:
                            logger.error(f"删除文件时出错: {e}")

                # 记录最新的 openapi 文件
                with open(HISTORY_FILE, "w") as history:
                    history.write(new_openapi_file)

    # 清理临时文件
    shutil.rmtree(TMP_DIR)

def update_hash(hash):
    """ 记录最新 hash """
    with open(HASH_FILE, "w") as f:
        f.write(hash)

def get_hash(content):
    """ 计算 SHA256 哈希 """
    return hashlib.sha256(content).hexdigest()

def check_update():
    """ 检查更新 """
    res = requests.get("https://launcherupdates.lunarclientcdn.com/latest.yml")
    if res.ok:
        new_hash = get_hash(res.content)
        prev_hash = None

        if os.path.exists(HASH_FILE):
            with open(HASH_FILE, "r") as f:
                prev_hash = f.readline().strip()

        logger.info(f"prevHash = {prev_hash}")
        logger.info(f"nowHash = {new_hash}")

        if new_hash == prev_hash:
            logger.info("此次未更新，跳过")
        else:
            logger.info("检测到更新")
            update_hash(new_hash)
            extract_package(res.content)

# 启动任务调度
logger.add(sys.stdout, colorize=True, format="<green>{time}</green> <level>{message}</level>")
check_update()

scheduler = BlockingScheduler()
scheduler.add_job(check_update, 'interval', hours=6)
scheduler.start()
