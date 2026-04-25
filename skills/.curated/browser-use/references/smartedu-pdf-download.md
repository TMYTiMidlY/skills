---
description: 国家中小学智慧教育平台受保护 PDF 的下载方法
---

# 国家中小学智慧教育平台 PDF 下载

## 案例背景

国家中小学智慧教育平台 (basic.smartedu.cn) 的教材详情页嵌入了 pdf.js 阅读器来展示 PDF。对于需要认证的受保护 PDF，直接下载 URL 会返回 401 错误。

## 目标教材

道德与法治八年级上册: https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId=5a29b928-d6da-4131-a69e-4c54941f7651&catalogType=tchMaterial&subCatalog=tchMaterial

## 解决方案

通过浏览器内置的 pdf.js 阅读器提取已加载的 PDF 数据：

```javascript
(async () => {
  const iframe = document.querySelector('iframe');
  const win = iframe.contentWindow;
  const app = win.PDFViewerApplication;
  const doc = app.pdfDocument;
  const data = await doc.getData();
  const blob = new Blob([data], {type: 'application/pdf'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '道德与法治八年级上册.pdf';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
})();
```

## 步骤说明

1. 首先用 `tabs_context_mcp` 获取当前 tab 列表
2. 切换到 PDF 预览页面的 tab
3. 用 `read_page` 确认 iframe 已加载
4. 执行上述 JavaScript 代码提取并下载 PDF

## 注意事项

- PDF 必须在 pdf.js 中完全加载后才能提取
- 该方法利用的是用户在浏览器中已合法访问的资源
