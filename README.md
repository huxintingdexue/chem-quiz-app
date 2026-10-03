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

## 重新生成题库

```bash
uv run --with pymupdf --with pillow python scripts/extract_pdf.py
```

可通过 `CHEM_PDF_PATH` 指定源 PDF。脚本会重新生成 `public/question-bank/bank.json` 与 78 张题目/答案页面截图。
