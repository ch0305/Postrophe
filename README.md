# Postrophe

> **Postrophe 是 [Apostrophe](https://gitlab.gnome.org/somas/apostrophe) 的 fork 和延续。**
> 它基于 Apostrophe 2.4，由本仓库独立维护。原项目由
> [Wolf Vollprecht](https://github.com/wolfvollprecht) 创建，后由
> [Manuel Genovés](https://gitlab.gnome.org/somas) 维护；原编辑器、界面设计和翻译的版权
> 归 Apostrophe 的作者与贡献者所有。

本仓库与 GNOME 项目、上游 Apostrophe 维护者没有隶属关系。Postrophe 特有的问题请提交到
[本仓库](https://github.com/ch0305/Postrophe/issues)，不要提交到上游 Apostrophe 的 tracker。

![](screenshots/main.png)

## 相比 Apostrophe 的改进

Postrophe 保留了 Apostrophe 干净、专注的编辑体验，并增加了以下功能：

- **任务列表 / 复选框**
  - `Ctrl+Shift+T` 插入任务项，`Ctrl+Shift+X` 切换光标所在行或选区内的复选框状态
    （菜单中也有对应操作）。
  - 在任务项或有序列表中按 `Enter` 会自动续接列表，行为与 GitHub / Typora 一致；
    在空列表项中按 `Enter` 会删除标记并退出列表。
  - 预览中的复选框可以直接点击，修改会写回编辑器中的 Markdown。
  - `Ctrl+Shift+O` 插入有序列表项。

- **预览性能**
  - 打字时不再重新加载整个预览页面，只替换页面 `<body>` 的内容，因此不会白闪，
    滚动位置也能保持。
  - 预览转换增加了防抖，避免每按一个键都启动一次 pandoc。
  - 去掉了窗口焦点 / 主题变化时不必要的预览重载。

- **稳定性修复**
  - 搜索和替换遇到非法正则表达式时不再崩溃，也不会使用过期的选区偏移。
  - 改进编辑器与预览之间的滚动同步。
  - 优先使用 WebKitGTK 4.1，旧环境回退到 4.0。

- **设置迁移**
  - 首次启动时会把旧 Apostrophe 的 GSettings 配置复制到 Postrophe 的新 schema，
    原有主题、输入格式、拼写检查等设置会保留。

## 安装

从 [Releases](https://github.com/ch0305/Postrophe/releases) 页面下载最新的 `.deb`，
然后安装：

```bash
sudo apt install ./postrophe_*.deb
```

安装包包含完整应用，会替换系统中已安装的 `apostrophe` / `apostrophe-devel` 包。
目前主要针对 Ubuntu 24.04 及更新版本构建；其他发行版请参考下面的源码构建方式。

如果需要退回 Apostrophe：

```bash
sudo apt remove postrophe
sudo apt install apostrophe
```

## 从源码构建

Ubuntu 24.04 上所需的依赖：

```bash
sudo apt install meson ninja-build sassc gettext \
    libhandy-1-dev libgirepository1.0-dev libgtk-3-dev \
    gir1.2-webkit2-4.1 pandoc python3-gi python3-regex \
    python3-setuptools python3-pypandoc python3-cairo \
    desktop-file-utils libglib2.0-bin
```

直接从源码树构建并运行（开发配置）：

```bash
./run-dev.sh
```

也可以手动构建：

```bash
meson setup builddir --prefix=/usr -Dprofile=development
ninja -C builddir
./builddir/local-postrophe       # 直接从源码树运行
sudo ninja -C builddir install   # 或安装到系统
postrophe
```

发布构建请使用默认 Meson profile（应用 id 为 `io.github.ch0305.Postrophe`，
不带 `.Devel` 后缀）：

```bash
meson setup builddir --prefix=/usr
ninja -C builddir
```

### 构建 Debian 安装包

```bash
./make-deb.sh
sudo apt install ./postrophe_*_amd64.deb
```

脚本必须使用系统 Python（`/usr/bin/python3`），会将构建结果安装到 `/usr`，
并打包成 Debian 安装包。包中声明了 `Conflicts` / `Replaces`，因此会替换旧的
`apostrophe` / `apostrophe-devel` 包。

### 预览更新机制

预览使用 `pandoc` 渲染。打开文档时第一次预览会完整加载页面；之后的编辑只替换
页面 `<body>`，这是打字和按回车时不再白闪的关键。切换预览主题、输入格式或窗口
布局时仍会进行一次完整重载，因为这些变化会影响整个页面。

## 持续集成

`.github/workflows/build.yml` 会在每次推送时构建 `.deb`：

- 推送到 `main`：构建安装包，并附加到滚动的 **Latest build** 预发布版本；
- 推送 `v*` 标签（例如 `v2.5.0`）：构建安装包并发布为正式的 GitHub Release。

## 翻译

Postrophe 继承了 Apostrophe 的翻译。上游翻译工作可以在
[Poeditor](https://poeditor.com/join/project/gxVzFyXb2x) 参与；本 fork 新增字符串的
翻译可以通过 Pull Request 提交到本仓库。

## 致谢

- 原版 Apostrophe：Wolf Vollprecht、Manuel Genovés 及所有贡献者。
- Postrophe fork、任务列表和预览性能改动：Postrophe 贡献者。

上游项目：<https://gitlab.gnome.org/somas/apostrophe>

## 许可证

Postrophe 使用 GNU General Public License version 3 发布，详见 [LICENSE](LICENSE)。
源码中保留了原始版权声明。
