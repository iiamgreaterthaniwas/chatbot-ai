# 部署饺子 🥟 到 dumplings.photoidmaker.xyz

以下步骤以 **Ubuntu 22.04 / 24.04** 为例，命令都在服务器上执行（`ssh` 登录后）。

最终结构：

```
浏览器 ──HTTPS──▶ Nginx (80/443) ──▶ gunicorn 127.0.0.1:5100 (app.py) ──▶ MySQL
```

---

## 第 1 步：添加域名解析

到你买 `photoidmaker.xyz` 的域名服务商后台（阿里云 / 腾讯云 / Cloudflare / Namesilo 等），添加一条记录：

| 记录类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `dumplings` | 你服务器的公网 IP |

> 用 Cloudflare 的话，先把代理（橙色云朵）关掉，变成灰色"仅 DNS"，等第 6 步 HTTPS 证书申请成功后再打开。

几分钟后在本地电脑上检查是否生效（显示的 IP 是你服务器的就对了）：

```bash
ping dumplings.photoidmaker.xyz
```

> ⚠️ 如果服务器在**中国大陆**，域名必须先完成 ICP 备案，否则 80/443 端口会被拦截。香港和海外服务器不需要备案。

---

## 第 2 步：安装软件

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip nginx mysql-server certbot python3-certbot-nginx
```

---

## 第 3 步：创建数据库

```bash
sudo mysql
```

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

## 第 4 步：下载代码并安装依赖

```bash
sudo git clone https://github.com/iiamgreaterthaniwas/chatbot-ai.git /var/www/dumplings
cd /var/www/dumplings
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

设置文件权限（让服务能读取，其他人读不到 `.env`）：

```bash
sudo chown -R www-data:www-data /var/www/dumplings
sudo chmod 600 /var/www/dumplings/.env
```

---

## 第 5 步：启动服务

```bash
sudo cp /var/www/dumplings/deploy/dumplings.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dumplings
sudo systemctl status dumplings      # 看到 active (running) 就成功了，按 q 退出
```

本机测试一下（应该返回 `302`，即跳转到登录页）：

```bash
curl -I http://127.0.0.1:5100/
```

---

## 第 6 步：配置 Nginx 和 HTTPS

```bash
sudo cp /var/www/dumplings/deploy/nginx-dumplings.conf /etc/nginx/sites-available/dumplings
sudo ln -s /etc/nginx/sites-available/dumplings /etc/nginx/sites-enabled/
sudo nginx -t                        # 显示 syntax is ok 才继续
sudo systemctl reload nginx
```

申请免费 HTTPS 证书（按提示输入邮箱、同意协议；会自动续期）：

```bash
sudo certbot --nginx -d dumplings.photoidmaker.xyz
```

---

## 第 7 步：开放端口

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

> 如果用的是阿里云 / 腾讯云 / AWS 等云服务器，还要在控制台的**安全组**里放行 **80** 和 **443** 端口。
> 不要放行 5100 和 3306，它们只在服务器内部使用。

完成！打开 **https://dumplings.photoidmaker.xyz** ，注册账号、填写 DeepSeek API Key 就能用了。

---

## 以后更新代码

本地改完代码并 `git push` 后，在服务器上执行：

```bash
cd /var/www/dumplings
sudo -u www-data git pull
sudo venv/bin/pip install -r requirements.txt
sudo systemctl restart dumplings
```

> 如果 `git pull` 提示权限问题，先执行 `sudo git config --global --add safe.directory /var/www/dumplings`。

---

## 出问题时怎么查

| 现象 | 排查命令 / 原因 |
|---|---|
| 打不开网站 | `ping dumplings.photoidmaker.xyz` 看解析；检查安全组是否放行 80/443 |
| 502 Bad Gateway | 服务没起来：`sudo journalctl -u dumplings -n 50` 看报错 |
| 报错 `未配置 SECRET_KEY` | `.env` 没填好，或不在 `/var/www/dumplings` 下 |
| 报错 `Access denied for user` | `.env` 里的 MySQL 用户名或密码不对 |
| 能打开但登录后又跳回登录页 | 还没配 HTTPS 却设置了 `SESSION_COOKIE_SECURE=1`，先完成第 6 步 |
| AI 回复不是逐字显示，而是一次性出来 | Nginx 配置里缺少 `proxy_buffering off;` |
| 查看实时日志 | `sudo journalctl -u dumplings -f` |
