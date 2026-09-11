#!/usr/bin/env bash
# ============================================================
# 校园综合服务平台 —— 应用层部署 / 重新部署
#
# 用法（在服务器上，仓库根目录）：
#   sudo bash deploy/deploy.sh
#
# 幂等：重复执行等价于「装依赖 -> 数据库迁移 -> 重建前端 -> 重启后端」，
# 所以以后改完代码 pull 一下再跑这个脚本，就是更新上线。
#
# 前置条件（脚本会检查，缺失时立刻报错退出并说明原因）：
#   - python3.10+ / node / nginx / mysql 已安装   → 见 docs/部署手册.md 第二节
#   - 系统用户 campus 已存在，/opt/campus 归它所有
#   - /opt/campus/backend/.env 已填写             → 见 docs/部署手册.md 第三节
# ============================================================
set -euo pipefail

APP_DIR=/opt/campus
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
WEB_ROOT=/var/www/campus
SERVICE=campus-api
RUN_USER=campus
HEALTH_URL=http://127.0.0.1:8001/health

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    ok  %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    警告  %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m[失败] %s\033[0m\n' "$*" >&2; exit 1; }

# 注意 HOME：runuser 切换用户时 HOME 不一定跟着变。若不显式指定，npm / pip
# 会把缓存写向 root 的 /root/.npm、/root/.cache，而 campus 对 /root 没有写权限，
# 会抛出一串 EACCES 让人误以为是依赖坏了。
as_user() { runuser -u "$RUN_USER" -- env "HOME=/home/$RUN_USER" "$@"; }

# ---------------- 0. 前置检查 ----------------
step "0/6 前置检查"
[ "$(id -u)" -eq 0 ] || die "需要 root 权限，请用：sudo bash deploy/deploy.sh"
id "$RUN_USER" >/dev/null 2>&1 || die "系统用户 $RUN_USER 不存在，见 docs/部署手册.md 第二节"
[ -d "$BACKEND_DIR" ] || die "找不到 $BACKEND_DIR，确认仓库克隆在 $APP_DIR"
[ -d "$FRONTEND_DIR" ] || die "找不到 $FRONTEND_DIR"
[ -f "$BACKEND_DIR/.env" ] || die "$BACKEND_DIR/.env 不存在。生产环境请用 cp deploy/env.prod.template $BACKEND_DIR/.env 后填写，见 docs/部署手册.md 第三节"
command -v nginx >/dev/null || die "nginx 未安装"
command -v node  >/dev/null || die "node 未安装"
grep -q '^\(DB_PASSWORD\|LLM_API_KEY\|SECRET_KEY\)=' "$BACKEND_DIR/.env" || die ".env 缺少必要字段"
if grep -q 'CHANGE_ME' "$BACKEND_DIR/.env"; then
    warn ".env 里 SECRET_KEY 还是默认值，公网环境务必换掉"
fi

# 挑选可用的 Python 解释器：优先 3.11（与本机开发环境一致），否则退回 3.10。
# Ubuntu 22.04 自带的就是 3.10，而 3.11 要走 launchpad 上的 deadsnakes 第三方源，
# 国内网络未必拉得动。已扫过 app/ 全目录确认项目没用任何 3.11 专属特性
# （datetime.UTC / TaskGroup / tomllib / except* / typing.Self 全无），
# 所以 3.10 完全可跑 —— 能省掉这个不确定环节就省掉。
PY_BIN=""
for cand in python3.11 python3.12 python3.10 python3; do
    command -v "$cand" >/dev/null 2>&1 || continue
    ver=$("$cand" -c 'import sys;print("%d%02d"%sys.version_info[:2])' 2>/dev/null || echo 0)
    case "$ver" in ''|*[!0-9]*) continue ;; esac
    [ "$ver" -ge 310 ] || continue
    PY_BIN=$(command -v "$cand")
    break
done
[ -n "$PY_BIN" ] || die "找不到 Python 3.10 或更高版本，请先安装"
ok "使用 Python：$PY_BIN（$("$PY_BIN" -V 2>&1)）"
ok "环境检查通过"

# ---------------- 1. Python 虚拟环境 ----------------
step "1/6 同步后端依赖"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    as_user "$PY_BIN" -m venv "$VENV_DIR"
    ok "已创建虚拟环境 $VENV_DIR"
fi
as_user "$VENV_DIR/bin/python" -m pip install --upgrade pip -q
# 每次全新解析 requirements.txt，服务器上这份环境不会像本地那样被别的项目污染
as_user "$VENV_DIR/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt" -q
ok "依赖安装完成"

# 光装依赖不够：asyncmy 连 MySQL 8 的 caching_sha2_password 需要 cryptography，
# 而 asyncmy 自己没声明这个依赖。少了它后端会在建连时抛 RuntimeError 起不来。
as_user "$VENV_DIR/bin/python" -c "import cryptography" \
    || die "cryptography 未装上，MySQL 8 将无法建连。请检查 requirements.txt 是否包含它"
ok "cryptography 就位（MySQL 8 认证必需）"

# ---------------- 2. 数据库迁移 ----------------
step "2/6 数据库迁移"
# ★ 必须在 backend/ 目录下执行 ★
# alembic.ini 里 `script_location = alembic` 是相对路径、`prepend_sys_path = .`
# 也指当前目录，两者都由「进程的工作目录」解析。从别处执行会找不到 alembic/
# 脚本目录，或让 env.py 里的 `from app.config import settings` 报
# ModuleNotFoundError —— 所以这里先 cd 再跑，不要用 -c 指绝对路径糊过去。
(cd "$BACKEND_DIR" && as_user "$VENV_DIR/bin/alembic" upgrade head)
ok "已升级到最新版本（head）"

# ---------------- 3. 构建前端 ----------------
step "3/6 构建前端"
cd "$FRONTEND_DIR"
# package-lock.json 已入库，优先 npm ci（更快、结果可复现）；
# 但 npm ci 要求 lock 与 package.json 严格一致，不一致时会直接失败，
# 所以失败就退回 npm install 兜底，别让整个部署卡在装依赖这一步。
if [ -f package-lock.json ] && as_user npm ci --silent; then
    ok "npm ci 完成（依据 package-lock.json）"
else
    warn "npm ci 未成功，改用 npm install 兜底"
    as_user npm install --silent
fi
as_user npm run build

[ -f "$FRONTEND_DIR/dist/index.html" ] || die "前端构建产物 dist/index.html 不存在，构建失败了"
ok "前端构建完成"

# ---------------- 4. 发布静态文件 ----------------
step "4/6 发布前端静态文件到 $WEB_ROOT"
mkdir -p "$WEB_ROOT"
# 先清空再拷贝：避免上一版残留的旧 hash 文件越堆越多
rm -rf "${WEB_ROOT:?}/dist"
cp -r "$FRONTEND_DIR/dist" "$WEB_ROOT/dist"
chown -R "$RUN_USER:$RUN_USER" "$WEB_ROOT"
ok "已发布到 $WEB_ROOT/dist"

# ---------------- 5. 上传目录权限 ----------------
step "5/6 检查上传目录"
UPLOAD_DIR="$BACKEND_DIR/uploads"
mkdir -p "$UPLOAD_DIR"
chown -R "$RUN_USER:$RUN_USER" "$UPLOAD_DIR"
ok "$UPLOAD_DIR 可写（商品图 / 简历落盘位置）"

# ---------------- 6. 重启服务 ----------------
step "6/6 重启后端并重载 Nginx"
systemctl daemon-reload
systemctl restart "$SERVICE"

# 等待健康检查通过（最多 60 秒）
# 经济型 e 是共享型实例，导入 FastAPI + LangChain 在冷启动时可能就要十几秒，
# 给到 60 秒余量，避免「其实起来了但被判为失败」。
for i in $(seq 1 60); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
        ok "后端已就绪：$(curl -fsS "$HEALTH_URL")"
        break
    fi
    if [ "$i" -eq 60 ]; then
        printf '\n--- 最近 40 行服务日志 ---\n'
        journalctl -u "$SERVICE" -n 40 --no-pager
        die "后端 60 秒内未通过健康检查，请查看上面的日志"
    fi
    sleep 1
done

nginx -t || die "Nginx 配置有语法错误，已中止（服务未重载）"
systemctl reload nginx
ok "Nginx 已重载"

printf '\n\033[1;32m部署完成。\033[0m\n'
PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '<你的公网IP>')
printf '访问：  http://%s\n' "$PUBLIC_IP"
printf '接口文档： http://%s/docs\n' "$PUBLIC_IP"
printf '\n排错常用命令：\n'
printf '  查看后端日志   journalctl -u %s -f\n' "$SERVICE"
printf '  查看 Nginx 日志 tail -f /var/log/nginx/campus.error.log\n'
