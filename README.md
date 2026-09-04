# Gcore CaaS 容器探针

## 最简单使用步骤

1. 在 GitHub 创建公开仓库，名称建议为 `gcore-caas-probe`。
2. 解压本文件，把里面所有文件上传到 GitHub 仓库最外层。
3. 点击仓库上方 **Actions**，等待 `Build container image` 出现绿色勾号。
4. 到仓库的 **Packages** 找到镜像。如果镜像是私有的，请将 Package visibility 改为 Public。
5. Gcore CaaS 创建容器时填写镜像：

   `ghcr.io/你的GitHub用户名/gcore-caas-probe:latest`

6. 容器监听端口填写：`8080`。
7. 环境变量可不填；如有 PORT 环境变量，请设为 `8080`。
8. 容器状态 Ready 后，打开 Gcore 分配给你的 HTTPS 网址。
9. 按页面按钮顺序测试，最后点击“复制检测结果”，将内容粘贴回聊天。

## 注意

- 这是临时测试工具，不要在其中放账号、密码、UUID、代理配置或其他敏感信息。
- 该版本没有鉴权，因此不要将分配的网址公开分享；测试结束建议删除容器。
- 当前只检查 Gcore CaaS 本身，尚未包含 Cloudflare Worker。
