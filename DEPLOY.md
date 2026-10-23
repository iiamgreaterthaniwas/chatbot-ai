# 部署饺子 🥟 到 dumplings.photoidmaker.xyz

本文按你的服务器情况编写：**Ubuntu 22.04（ARM）**，已装好 Nginx、MySQL、git、certbot，
Nginx 上已经在跑 `photoidmaker.xyz`（配置在 `/etc/nginx/conf.d/idphoto.conf`），
代码 clone 在 **`/var/www/chatbot-ai`**。

最终结构：

```
浏览器 ──HTTPS──▶ Nginx (80/443) ──▶ gunicorn 127.0.0.1:5100 (app.py) ──▶ MySQL
```

饺子作为一个独立的子域名站点加进去，**不会影响**现有的 photoidmaker 网站、3000 端口的 Next.js 和 x-ui 代理。

---

## 第 0 步：把最新代码推送到 GitHub（在本地电脑上）

服务器上的代码是从 GitHub 拉的，所以本地改完要先推送上去。在本地 `D:\chatbot-ai` 目录执行：

```bash
git add -A
git commit -m "饺子：新界面、MySQL、注册登录、用户自己的 API Key、部署配置"
git push
```

> `.env` 已经在 `.gitignore` 里，不会被推送上去。

---

## 第 1 步：添加域名解析

到你买 `photoidmaker.xyz` 的域名服务商后台，添加一条记录：

| 记录类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `dumplings` | 服务器公网 IP（和 `photoidmaker.xyz` 用的是同一个） |

> 用 Cloudflare 的话，先把代理（橙色云朵）关掉，变成灰色"仅 DNS"，等第 6 步 HTTPS 证书申请成功后再打开。

几分钟后在本地电脑上检查（显示的 IP 是你服务器的就对了）：

```bash
ping dumplings.photoidmaker.xyz
```

---

## 第 2 步：安装缺少的软件

服务器上只缺 Python 虚拟环境和 pip，顺便确保 certbot 的 Nginx 插件在：

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-certbot-nginx
```

---

## 第 3 步：创建数据库

```bash
sudo mysql
```

> 如果提示 `Access denied`，说明你给 MySQL root 设置过密码，改用 `sudo mysql -u root -p`。

在 MySQL 里执行（把 `换成一个强密码` 改掉）：

```sql
CREATE DATABASE chatbot DEFAULT CHARSET utf8mb4;
CREATE USER 'dumplings'@'localhost' IDENTIFIED BY '换成一个强密码';
GRANT ALL PRIVILEGES ON chatbot.* TO 'dumplings'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> 专门建一个 `dumplings` 用户，只能访问 `chatbot` 这个库，比直接用 root 安全。表会在第一次访问网站时自动创建。

---

## 第 4 步：更新代码并安装依赖

代码已经 clone 在 `/var/www/chatbot-ai`，先拉取第 0 步推送的最新版本：

```bash
cd /var/www/chatbot-ai
sudo git config --global --add safe.directory /var/www/chatbot-ai
sudo git pull
ls templates deploy        # 能看到 index.html、login.html、dumplings.service 等就说明是新版本
```

创建 Python 虚拟环境并安装依赖：

```bash
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

创建配置文件：

```bash
sudo cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # 生成 SECRET_KEY，复制输出
sudo nano .env
```

`.env` 填成这样：

```
DEEPSEEK_MODEL=deepseek-flash

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=dumplings
MYSQL_PASSWORD=第 3 步设置的密码
MYSQL_DATABASE=chatbot

SECRET_KEY=刚才生成的那串字符
SESSION_COOKIE_SECURE=1
```

> `nano` 里按 `Ctrl+O` 回车保存，`Ctrl+X` 退出。
>
> ⚠️ `SECRET_KEY` 设置好后**不要再改**，否则所有用户保存的 API Key 都会失效、需要重新登录。

让服务（以 `www-data` 用户运行）能读取 `.env`，其他用户读不到；再建一个存放用户图片的目录，让服务能写入：

```bash
sudo chown www-data:www-data /var/www/chatbot-ai/.env
sudo chmod 600 /var/www/chatbot-ai/.env
sudo mkdir -p /var/www/chatbot-ai/uploads
sudo chown www-data:www-data /var/www/chatbot-ai/uploads
sudo chmod 700 /var/www/chatbot-ai/uploads
```

> `uploads` 里是用户发送的图片，已加入 `.gitignore`，`git pull` 不会影响它。备份服务器时记得连同数据库一起备份这个目录。

---

## 第 5 步：启动服务

```bash
sudo cp /var/www/chatbot-ai/deploy/dumplings.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dumplings
sudo systemctl status dumplings      # 看到 active (running) 就成功了，按 q 退出
```

本机测试一下（第一行应该是 `HTTP/1.1 302 FOUND`，即跳转到登录页）：

```bash
curl -I http://127.0.0.1:5100/
```

---

## 第 6 步：配置 Nginx 和 HTTPS

你服务器上的站点配置都放在 `conf.d` 目录，饺子也放这里（文件名必须以 `.conf` 结尾）：

```bash
sudo cp /var/www/chatbot-ai/deploy/nginx-dumplings.conf /etc/nginx/conf.d/dumplings.conf
sudo nginx -t                        # 显示 syntax is ok 和 test is successful 才继续
sudo systemctl reload nginx
```

确认 Nginx 把新域名转给了饺子，而不是现有的 photoidmaker 网站（同样应该看到 `302` 和 `Location: /login`）：

```bash
curl -I -H "Host: dumplings.photoidmaker.xyz" http://127.0.0.1/
```

申请免费 HTTPS 证书（按提示操作，会自动续期；只会修改 `dumplings.conf`，不会动 `idphoto.conf`）：

```bash
sudo certbot --nginx -d dumplings.photoidmaker.xyz
```

---

## 第 7 步：确认端口（⚠️ 不要直接启用 ufw）

你的服务器上还跑着 x-ui 代理（23456、2096、60204 端口）和 3000 端口的服务。
**如果随手执行 `ufw enable`，只放行 SSH 和网站的话，这些服务会立刻断掉。**

先看一下防火墙状态：

```bash
sudo ufw status
```

- 显示 `inactive`：**保持不启用，这一步什么都不用做。** 端口由云服务器控制台的安全组控制，photoidmaker 网站能访问说明 80/443 早就放行了。
- 显示 `active`：确认列表里有 `80`、`443`（或 `Nginx Full`）即可，不需要新增规则。

> 不要放行 5100 和 3306，它们只在服务器内部使用。

完成！打开 **https://dumplings.photoidmaker.xyz** ，注册账号、填写 DeepSeek API Key 就能用了。

---

## 以后更新代码

本地改完代码并 `git push` 后，在服务器上执行：

```bash
cd /var/www/chatbot-ai
sudo git pull
sudo venv/bin/pip install -r requirements.txt
sudo systemctl restart dumplings
```

如果这次更新改了 `deploy/nginx-dumplings.conf`（比如加图片功能时调大了上传上限），还要重新复制一次 Nginx 配置。
**注意**：certbot 之前往 `/etc/nginx/conf.d/dumplings.conf` 里加了 HTTPS 配置，直接覆盖会把它冲掉，所以只改对应的那一行：

```bash
sudo sed -i 's/client_max_body_size .*/client_max_body_size 50m;/' /etc/nginx/conf.d/dumplings.conf
sudo nginx -t && sudo systemctl reload nginx
```

> 加图片功能那次更新，还要按第 4 步最后的命令建好 `uploads` 目录。

---

## 出问题时怎么查

| 现象 | 排查命令 / 原因 |
|---|---|
| 打不开网站 | `ping dumplings.photoidmaker.xyz` 看域名解析是否生效 |
| 打开的是 photoidmaker 的页面 | 第 6 步的 `dumplings.conf` 没生效：`ls /etc/nginx/conf.d/`，再 `sudo nginx -t && sudo systemctl reload nginx` |
| 502 Bad Gateway | 饺子服务没起来：`sudo journalctl -u dumplings -n 50` 看报错 |
| 报错 `未配置 SECRET_KEY` | `.env` 没填好，或权限不对（第 4 步最后两条命令） |
| 报错 `Access denied for user` | `.env` 里的 MySQL 用户名或密码不对 |
| `pip install` 时 cryptography 编译失败 | ARM 服务器偶尔会遇到：`sudo apt install -y build-essential libssl-dev libffi-dev python3-dev` 后重试 |
| 能打开但登录后又跳回登录页 | 还没配 HTTPS 却设置了 `SESSION_COOKIE_SECURE=1`，先完成第 6 步 |
| AI 回复不是逐字显示，而是一次性出来 | Nginx 配置里缺少 `proxy_buffering off;` |
| 发图片提示"上传的内容太大"或 `413` | Nginx 的 `client_max_body_size` 还是旧的 2m，见"以后更新代码" |
| 发图片报 `Permission denied: .../uploads` | `uploads` 目录不存在或 `www-data` 没有写权限，见第 4 步最后几条命令 |
| 查看实时日志 | `sudo journalctl -u dumplings -f` |
