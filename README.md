# 饺子 🥟
一个 AI 聊天助手，基于 DeepSeek API + Flask + MySQL。

- 每次只把当前消息发给模型（不带上下文，节省 token）
- 用户注册 / 登录，每个用户只能看到自己的对话
- 每个用户使用自己的 DeepSeek API Key（加密保存在数据库里）
- 支持发送图片（选择、粘贴或拖入），由 deepseek-flash 识图
- 安卓 App（WebView 套壳），由 GitHub Actions 云端打包，见 [android/README.md](android/README.md)
- 对话记录保存在 MySQL：`users`（用户）、`conversations`（对话）、`messages`（对话记录）

## 本地运行

1. 安装依赖：`pip install -r requirements.txt`
2. 在 MySQL 中建库（表会在第一次访问时自动创建）：

   ```sql
   CREATE DATABASE chatbot DEFAULT CHARSET utf8mb4;
   ```

3. 复制 `.env.example` 为 `.env`，填写 MySQL 账号密码和 `SECRET_KEY`（DeepSeek API Key 由每个用户登录后自己填写）
4. 运行 `python app.py`，打开 http://localhost:5000

> 重新运行前先停掉上一次的 `app.py`。Windows 上多个进程可以同时占用 5000 端口，浏览器可能会连到旧版本。

## 部署到服务器

见 [DEPLOY.md](DEPLOY.md)，包含域名解析、Nginx、HTTPS 证书和 systemd 开机自启的完整步骤。
