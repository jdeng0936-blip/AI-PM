#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════
# preflight.sh — 部署前一键预检
#
# 用法:
#   cd backend && bash scripts/preflight.sh
#
# 检查项:
#   1. .env 存在且无 placeholder
#   2. 关键密钥强度(JWT_SECRET / POSTGRES_PASSWORD)
#   3. AIPM_ENV=prod
#   4. CORS 不是 *
#   5. PostgreSQL 可连
#   6. Alembic 处于最新版本
#   7. 关键凭证(企微/钉钉/OSS/LLM)非占位值
#   8. Python 依赖完整
#
# 退出码:
#   0 = 全部通过,可上线
#   1 = 有阻塞问题(必须修复)
#   2 = 有警告(可继续但建议处理)
# ════════════════════════════════════════════════════════════════
set -u

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

ok()    { echo -e "${GREEN}✓${NC} $1";  PASS=$((PASS+1)); }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; WARN=$((WARN+1)); }
fail()  { echo -e "${RED}✗${NC} $1";    FAIL=$((FAIL+1)); }
hdr()   { echo -e "\n${BLUE}── $1 ──${NC}"; }

echo -e "${BLUE}🛫 AI-PM V2.0 部署预检${NC}"
echo "项目: $(pwd)"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

# ─── 1. .env 文件 ────────────────────────────────────────────────
hdr "1/8 配置文件"

if [ ! -f .env ]; then
  fail ".env 不存在 — 先 cp .env.production.template .env"
  echo -e "\n${RED}阻塞:无法继续预检${NC}"
  exit 1
fi
ok ".env 存在"

# 检查 placeholder
PLACEHOLDER_COUNT=$(grep -c "⚠️_" .env 2>/dev/null | head -1)
PLACEHOLDER_COUNT=${PLACEHOLDER_COUNT:-0}
if [ "$PLACEHOLDER_COUNT" -gt 0 ] 2>/dev/null; then
  fail "发现 $PLACEHOLDER_COUNT 处未填的占位符(搜索 ⚠️_):"
  grep -n "⚠️_" .env | sed 's/^/    /'
else
  ok "无占位符未填"
fi

# ─── 2. 运行模式 ────────────────────────────────────────────────
hdr "2/8 运行模式"

AIPM_ENV_VAL=$(grep '^AIPM_ENV=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")
if [ "$AIPM_ENV_VAL" = "prod" ]; then
  ok "AIPM_ENV=prod(生产模式,/simulate 端点已禁用)"
else
  warn "AIPM_ENV=$AIPM_ENV_VAL(非 prod,生产建议改为 prod)"
fi

# ─── 3. JWT 密钥强度 ────────────────────────────────────────────
hdr "3/8 密钥强度"

JWT=$(grep '^JWT_SECRET_KEY=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
JWT_LEN=${#JWT}
if [ "$JWT_LEN" -lt 32 ]; then
  fail "JWT_SECRET_KEY 长度仅 $JWT_LEN(太短,至少 32 位)"
  echo "    生成方法:openssl rand -hex 32"
elif echo "$JWT" | grep -qE '^(change|your|default|test|secret|password)'; then
  fail "JWT_SECRET_KEY 似乎是默认占位值"
else
  ok "JWT_SECRET_KEY 长度 $JWT_LEN 位,看起来已自定义"
fi

PG_PWD=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$PG_PWD" ] || [ "$PG_PWD" = "aipm2026" ] || [ "${#PG_PWD}" -lt 12 ]; then
  warn "POSTGRES_PASSWORD 太弱($([ -z "$PG_PWD" ] && echo "空" || echo "${#PG_PWD}位"))"
else
  ok "POSTGRES_PASSWORD 长度 ${#PG_PWD} 位"
fi

# ─── 4. CORS ──────────────────────────────────────────────────
hdr "4/8 CORS 安全"

CORS=$(grep '^CORS_ALLOWED_ORIGINS=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
if echo "$CORS" | grep -q '\*'; then
  fail "CORS 含 *(危险!生产必须限定具体域名)"
elif [ -z "$CORS" ] || echo "$CORS" | grep -q "your-frontend-domain"; then
  fail "CORS 未配置或仍是模板默认值"
else
  ok "CORS 已限定到具体域名"
fi

# ─── 5. PostgreSQL 连通 ────────────────────────────────────────
hdr "5/8 数据库连通"

if command -v psql >/dev/null 2>&1; then
  DB_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
  # 转换 asyncpg URL 为 psql 可识别
  PSQL_URL=$(echo "$DB_URL" | sed 's|postgresql+asyncpg://|postgresql://|')
  if psql "$PSQL_URL" -c "SELECT 1" >/dev/null 2>&1; then
    ok "PostgreSQL 连通"
  else
    fail "PostgreSQL 连不上 — 检查 DATABASE_URL / 数据库是否启动"
  fi
else
  warn "本机无 psql,跳过连通测试(部署时 Docker 内会再检查)"
fi

# ─── 6. Alembic 版本 ────────────────────────────────────────────
hdr "6/8 数据库迁移"

if command -v alembic >/dev/null 2>&1 || [ -x .venv311/bin/alembic ]; then
  ALEMBIC_BIN=$(command -v alembic 2>/dev/null || echo .venv311/bin/alembic)
  HEAD=$(PYTHONPATH=. $ALEMBIC_BIN heads 2>/dev/null | head -1 | awk '{print $1}')
  CUR=$(PYTHONPATH=. $ALEMBIC_BIN current 2>/dev/null | head -1 | awk '{print $1}')

  if [ -z "$HEAD" ]; then
    warn "alembic heads 无输出 — 检查 alembic.ini 配置"
  elif [ "$HEAD" = "v2_0_baseline" ]; then
    ok "迁移文件 head = v2_0_baseline(Week 1-8 全部纳管)"
  else
    warn "迁移 head = $HEAD(预期 v2_0_baseline)"
  fi

  if [ -n "$CUR" ] && [ "$CUR" = "$HEAD" ]; then
    ok "数据库版本与 head 一致,无需 upgrade"
  elif [ -n "$CUR" ]; then
    warn "数据库当前版本 = $CUR,需要 alembic upgrade head"
  else
    warn "数据库尚未跑过迁移,需要 alembic upgrade head"
  fi
else
  warn "未找到 alembic 可执行文件"
fi

# ─── 7. 关键凭证检查 ────────────────────────────────────────────
hdr "7/8 凭证完整性"

check_credential() {
  local key=$1
  local desc=$2
  local optional=${3:-no}
  local val=$(grep "^${key}=" .env | cut -d= -f2- | tr -d '"' | tr -d "'")

  if [ -z "$val" ]; then
    if [ "$optional" = "optional" ]; then
      warn "$desc 未配置($key 为空)— 可选项"
    else
      fail "$desc 未配置($key 为空)"
    fi
  elif echo "$val" | grep -qE "^(your_|YOUR_|ww_your|⚠️|change-me)"; then
    fail "$desc 仍是占位值($key)"
  else
    ok "$desc 已配置"
  fi
}

check_credential LITELLM_API_KEY "LLM 网关 API Key"
check_credential WECHAT_CORP_ID "企微 CorpID" optional
check_credential WECHAT_BOT_WEBHOOK "企微群机器人 Webhook" optional
check_credential DINGTALK_BOT_WEBHOOK "钉钉群机器人 Webhook" optional
check_credential OSS_ACCESS_KEY_ID "OSS Access Key" optional

# ─── 8. Python 依赖 ────────────────────────────────────────────
hdr "8/8 Python 依赖"

if [ -x .venv311/bin/python ]; then
  PYBIN=.venv311/bin/python
elif [ -x .venv/bin/python ]; then
  PYBIN=.venv/bin/python
else
  PYBIN=python3
fi

MISSING=$($PYBIN -c "
import importlib
required = ['fastapi','sqlalchemy','asyncpg','redis','httpx','passlib','apscheduler','oss2','websockets']
missing = []
for m in required:
    try: importlib.import_module(m)
    except ImportError: missing.append(m)
print(','.join(missing))
" 2>/dev/null)

if [ -z "$MISSING" ]; then
  ok "9 个关键依赖全部就位"
else
  fail "缺失依赖:$MISSING(运行 pip install -r requirements.txt)"
fi

# ─── 总结 ──────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo -e "${GREEN}通过 $PASS${NC}  ${YELLOW}警告 $WARN${NC}  ${RED}阻塞 $FAIL${NC}"
echo "════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  echo -e "\n${RED}❌ 有阻塞项,修复后再上线${NC}"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo -e "\n${YELLOW}⚠️  有警告项,建议处理后上线(可继续)${NC}"
  exit 2
else
  echo -e "\n${GREEN}✅ 全部通过,可以上线!${NC}"
  exit 0
fi
