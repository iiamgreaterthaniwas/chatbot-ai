# 饺子 🥟 安卓 App

这是一个"套壳" App：打开后全屏显示 **https://dumplings.photoidmaker.xyz** 。
页面和功能都来自服务器，所以**改网站不需要重新打包 App**，只有改了这个 `android/` 目录（图标、名字、壳的功能）才需要。

App 额外处理了这些事情：

- 登录状态保存，下次打开不用重新登录
- 发图片时可以从相册选，也可以直接拍照
- 返回键：先关闭大图 / 设置弹窗 / 侧边栏，再按才退出
- 外部链接（比如"去获取 API Key"）用手机浏览器打开
- 没网时显示"网络不可用 · 重试"
- 跟随手机的深色 / 浅色模式

打包在 GitHub 上云端完成，电脑上**什么都不用装**。

---

## 第一次：生成签名密钥（只做一次）

签名密钥是 App 的"身份证"，以后每次更新都必须用同一个，否则别人无法覆盖安装。

在 `D:\chatbot-ai` 目录运行：

```bash
python android/make_keystore.py
```

会在 `C:\Users\你的用户名\jiaozi-keystore\` 生成两个文件：

| 文件 | 用途 |
|---|---|
| `jiaozi-release.p12` | 签名密钥。**备份到网盘或 U 盘**，丢了就再也无法发布更新 |
| `github-secrets.txt` | 下一步要填到 GitHub 的 3 个值 |

> ⚠️ 这个文件夹**不要**复制到项目里，也不要提交到 Git 或发给别人。

## 第一次：把密钥填到 GitHub（只做一次）

1. 打开 GitHub 仓库页面 → **Settings** → 左侧 **Secrets and variables** → **Actions**
2. 点 **New repository secret**，按 `github-secrets.txt` 里的内容添加 3 项：

| Name | Secret |
|---|---|
| `KEYSTORE_BASE64` | 很长的一串字符（整段复制） |
| `KEYSTORE_PASSWORD` | 密码 |
| `KEY_ALIAS` | `jiaozi` |

填完后可以删掉 `github-secrets.txt`（`jiaozi-release.p12` 要留着并备份）。

---

## 打包

### 方式一：发布正式版（推荐，别人可以直接下载）

在本地 `D:\chatbot-ai` 目录打一个版本标签并推送：

```bash
git tag v1.0.0
git push origin v1.0.0
```

几分钟后，打开仓库页面右侧的 **Releases**，就能看到 `jiaozi-v1.0.0.apk`，把这个页面的链接发给别人即可下载。
下次发新版本把版本号加一，比如 `v1.0.1`。

### 方式二：只是自己测试

- 修改了 `android/` 目录并推送到 `main` 时会自动打包；
- 或者在仓库的 **Actions** 页面 → 左侧"打包 Android APK" → **Run workflow** 手动打包。

完成后点进这次运行，在页面最下面的 **Artifacts** 里下载 `jiaozi-apk`（下载的是 zip，解压出 `jiaozi.apk`）。
Artifacts 需要登录 GitHub 才能下载，保留 30 天，适合自己测试；发给别人用方式一。

> 如果还没配置签名密钥，Artifacts 里会是 `jiaozi-apk-debug-signed`：只能试装，以后不能被正式版覆盖安装（要先卸载）。

---

## 安装到手机

把 APK 发到手机上点击安装。第一次会提示"禁止安装未知来源应用"，按提示在设置里允许即可。
华为 / 小米 / OPPO 等可能会提示"未经检测"或被"纯净模式"拦截，选择继续安装就行。

## 常见问题

| 现象 | 原因 |
|---|---|
| Actions 里打包失败 | 点进失败的步骤看红色报错，复制发给 Claude |
| 打开 App 显示"网络不可用" | 手机没网，或服务器 / HTTPS 没配好（先用手机浏览器打开网站试试） |
| 安装新版本提示"签名不一致" | 旧版本是用别的密钥（或调试签名）打的，先卸载旧版再装 |
| 想换 App 打开的网址 | 改 `app/build.gradle.kts` 里的 `APP_URL` |
