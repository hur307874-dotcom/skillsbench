# skill-bench 沙箱镜像：agent 在容器内跑，只挂 /repo，答案材料物理不可达
# 构建：wsl -d Ubuntu -u root -- docker build -f /mnt/d/ai_project/skill-bench/docker/Dockerfile -t skillbench-sandbox:0.73.1 /mnt/d/ai_project/skill-bench
FROM node:22-bookworm-slim

# Debian 换 USTC 源（CN 网络）
RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip git ca-certificates bash \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir --break-system-packages pytest -i https://mirrors.aliyun.com/pypi/simple/

# 与宿主机同版本的 pi CLI（0.73.1），走 npmmirror
RUN npm install -g @mariozechner/pi-coding-agent@0.73.1 --registry=https://registry.npmmirror.com \
 && npm cache clean --force

# DIS 中转站 provider 扩展
COPY pi-dis-provider.ts /opt/pi-dis-provider.ts

WORKDIR /repo
ENTRYPOINT []
CMD ["bash"]
