# 化学三轮复习刷题

面向 iPhone 与 Android 的在线刷题 PWA。题库由《三轮复习·基础知识回归（含答案）》提取，覆盖 27 个章节，支持填空、判断、选择和原题截图核对。

## 本地运行

```bash
npm install
npm run dev
```

## 构建

```bash
npm run build
```

产物位于 `dist/`。推送 `main` 分支后，GitHub Actions 会自动部署到 GitHub Pages。

## 用户与管理员

App 使用本机用户档案区分不同人的学习进度。进入“用户”页可以新增、切换用户；管理员输入口令后可编辑任意题目。

管理员编辑支持两种保存方式：

- 保存到本机：立即生效，适合先快速修正当前设备看到的内容。
- 保存并同步：填写 GitHub Fine-grained token 后，直接把题库更新提交到 `huxintingdexue/chem-quiz-app`，部署完成后所有用户都会看到新版本。Token 仅保存在当前浏览器，需要该仓库 Contents 读写权限。

管理员口令可通过构建环境变量 `VITE_ADMIN_CODE` 调整。

## 重新生成题库

```bash
uv run --with pymupdf --with pillow python scripts/extract_pdf.py
```

可通过 `CHEM_PDF_PATH` 指定源 PDF。脚本会重新生成 `public/question-bank/bank.json` 与 78 张题目/答案页面截图。
