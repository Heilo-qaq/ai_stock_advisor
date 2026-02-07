# 📱 手机端部署指南

本文档提供4种方案，让你在手机上访问 AI智能选股顾问系统。

---

## 方案一：Streamlit Cloud（推荐，最简单）

**免费 · 零配置 · 5分钟搞定**

### 步骤

1. **上传代码到GitHub**
```bash
# 本地初始化 Git
cd ai_stock_advisor
git init
git add .
git commit -m "initial commit"

# 创建 GitHub 仓库后推送
git remote add origin https://github.com/你的用户名/ai-stock-advisor.git
git branch -M main
git push -u origin main
```

2. **登录 Streamlit Cloud**
   - 打开 https://share.streamlit.io
   - 用 GitHub 账号登录
   - 点击 "New app"

3. **配置**
   - Repository: `你的用户名/ai-stock-advisor`
   - Branch: `main`
   - Main file path: `app.py`
   - 点击 "Advanced settings" → 添加环境变量:
     ```
     DEEPSEEK_API_KEY = 你的API密钥
     ```
   - 点击 "Deploy!"

4. **手机访问**
   - 部署成功后会得到一个URL，如: `https://ai-stock-advisor.streamlit.app`
   - 手机浏览器打开即可使用
   - 可以添加到手机桌面当"App"用

### 注意事项
- 免费版有资源限制（1GB内存），回测大量股票时可能超限
- 如果长时间无人访问，应用会休眠，首次打开需等10-20秒唤醒
- 不支持从中国大陆直接访问（需要梯子）

---

## 方案二：自己的云服务器 + Docker（推荐国内用户）

**国内可访问 · 无限制 · 需要服务器**

### 前提
- 一台云服务器（阿里云/腾讯云/华为云 轻量级即可，2核4G约50元/月）
- 服务器已安装 Docker

### 步骤

1. **上传代码到服务器**
```bash
# 方法1: Git
scp -r ai_stock_advisor/ root@你的服务器IP:/opt/

# 方法2: 压缩包
scp ai_stock_advisor.zip root@你的服务器IP:/opt/
ssh root@你的服务器IP
cd /opt && unzip ai_stock_advisor.zip
```

2. **配置环境变量**
```bash
cd /opt/ai_stock_advisor

# 创建环境变量文件
echo "DEEPSEEK_API_KEY=你的API密钥" > .env
```

3. **Docker一键启动**
```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

4. **开放端口**
   - 云服务器安全组放行 8501 端口
   - 或者用 Nginx 反向代理到 80/443 端口（推荐）

5. **手机访问**
   - 打开 `http://你的服务器IP:8501`
   - 如果配了域名: `http://你的域名`

### Nginx反向代理配置（可选）
```nginx
server {
    listen 80;
    server_name stock.你的域名.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    location /_stcore/stream {
        proxy_pass http://127.0.0.1:8501/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

---

## 方案三：Render / Railway（海外免费平台）

### Render（有免费额度）

1. 代码推到 GitHub
2. 打开 https://render.com → New Web Service
3. 连接 GitHub 仓库
4. 会自动检测到 `render.yaml`，一键部署
5. 在 Environment 里添加 `DEEPSEEK_API_KEY`
6. 手机打开分配的URL即可

### Railway

1. 打开 https://railway.app → New Project
2. Deploy from GitHub → 选择仓库
3. 自动检测到 `Procfile`
4. 添加环境变量 `DEEPSEEK_API_KEY`
5. Deploy → 获得URL

---

## 方案四：安卓手机本地运行（不推荐，仅供折腾）

通过 Termux 在安卓手机上直接运行 Python + Streamlit。

### 步骤

1. **安装 Termux**
   - 从 F-Droid 下载: https://f-droid.org/packages/com.termux/
   - （Google Play 版本已过时，不要用）

2. **安装Python环境**
```bash
pkg update && pkg upgrade
pkg install python rust binutils
pip install --upgrade pip wheel setuptools
```

3. **安装依赖**（会比较慢，约15-30分钟）
```bash
pip install streamlit pandas numpy scipy plotly
pip install akshare openai requests
```

4. **上传代码**
```bash
# 在手机Termux中
cd ~
# 用 termux-setup-storage 打开存储权限
termux-setup-storage
# 从Download目录复制
cp -r /sdcard/Download/ai_stock_advisor ~/
```

5. **运行**
```bash
cd ~/ai_stock_advisor
streamlit run app.py --server.port=8501
```

6. **访问**: 手机浏览器打开 `http://localhost:8501`

### 注意
- 手机内存可能不够，回测大量股票会崩溃
- 安装依赖很慢（numpy/scipy需要编译）
- 不推荐长期使用，仅供体验

---

## 🔧 手机浏览器使用技巧

无论哪种部署方式，以下技巧提升手机体验：

### 添加到桌面（类似App）
- **iPhone Safari**: 打开网页 → 分享按钮 → "添加到主屏幕"
- **安卓 Chrome**: 打开网页 → 右上角菜单 → "添加到主屏幕"

### 使用建议
- 侧边栏设置好参数后收起（点左上角X），给主区域更多空间
- 图表支持双指缩放
- 回测建议用 5-10 只股票（手机性能有限）
- 如果加载慢，减少回测时间范围

---

## ⚡ 各方案对比

| 方案 | 难度 | 费用 | 国内可访问 | 性能 |
|------|------|------|------------|------|
| Streamlit Cloud | ⭐ | 免费 | ❌ 需梯子 | 中 |
| 云服务器+Docker | ⭐⭐⭐ | ~50元/月 | ✅ | 高 |
| Render/Railway | ⭐⭐ | 免费额度 | ❌ 需梯子 | 中 |
| 手机Termux | ⭐⭐⭐⭐⭐ | 免费 | ✅ | 低 |

**推荐**：国内用户 → 方案二（云服务器）；海外/有梯子 → 方案一（Streamlit Cloud）
