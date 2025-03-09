from apscheduler.schedulers.blocking import BlockingScheduler
import requests
import hashlib
import os
import yaml 
from yaml import CLoader as Loader, CDumper as Dumper
from loguru import logger
import sys
from DownloadKit import DownloadKit
import subprocess
import shutil
from asar import AsarArchive
import re
from datetime import datetime



def download(url, path):
    downloadKit = DownloadKit(path)
    logger.info(f"开始下载{url}")
    downloadKit.download(url)

def readJs(path):
    res = []
    files = os.walk(path)
    for path, dir_lst, file_lst in files:
        for file_name in file_lst:
            if(file_name.endswith(".js")):
                res.append(os.path.join(path, file_name))
                logger.info(f"找到js文件：{res[len(res)-1]}")
    return res

def extractPackage(content):
    logger.debug(content)
    config = yaml.load(content, Loader)
    logger.info(f"下载{config['packages']['x64']['path']}")
    download(f"https://launcherupdates.lunarclientcdn.com/{config['packages']['x64']['path']}", r"./files")
    logger.debug("开始解包7z到./files/tmp")
    cmd = ["7z", "x", f"files/{config['packages']['x64']['file']}", "-ofiles/tmp", "-y"]
    subprocess.run(cmd)
    logger.info("解包完成")
    logger.info("解包asar")
    with AsarArchive.open(r'./files/tmp/resources/app.asar') as archive:
        archive.extract(r'./files/asar')
    for js in readJs("./files/asar/dist-electron/electron"):
        with open(js, 'r', encoding='utf-8') as f:
            content = f.read()
            #https://api.lunarclientdev.com/f5278921b2d4429d95531e025f5318fd/openapi
            res = re.search(r"https://api.lunarclient(dev|prod).com/[a-f0-9]+/openapi", content)
            logger.info(f"在{js}里，找到了openapi")
            if res:
                logger.info(res.group())
                download(res.group(), r"./openapi")
                logger.info("重命名文件")
                os.rename(r"./openapi/openapi", f"./openapi/openapi-{datetime.now().strftime("%Y-%m-%d-%H-%M-%S")}.json")
    shutil.rmtree("files")

def updateHash(hash):
    os.remove("latest.yml.sha256")
    with open("latest.yml.sha256", "w") as f:
        f.write(hash)


def getHash(content):
    return hashlib.sha256(content).digest().hex()

def checkUpdate():
    res = requests.get("https://launcherupdates.lunarclientcdn.com/latest.yml")
    if(res.ok):
        hash = getHash(res.content)
        with open("latest.yml.sha256", "w+") as f:
            prevHash = f.readline()
            logger.info("prevHash="+ prevHash)
            logger.info("nowHash="+ hash)
            if hash==prevHash:
                logger.info("此次未更新，跳过")
            else:
                logger.info("检测到更新")
                f.close()
                updateHash(hash)
                extractPackage(res.content) 

checkUpdate()
logger.add(sys.stdout, colorize=True, format="<green>{time}</green> <level>{message}</level>")
scheduler = BlockingScheduler()
scheduler.add_job(checkUpdate, 'interval', hours=6)
scheduler.start()