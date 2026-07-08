# 车型监测 CLI - 数据源复杂度评估报告

> 调研时间：2026-06-16
> 评估目标：汽车之家、易车、懂车帝

---

## 1. 汽车之家 (autohome.com.cn)

| 维度 | 评分 | 说明 |
|------|------|------|
| 页面渲染方式 | 🔴 高 | 全站 JS 渲染，requests 直接返回空 HTML shell |
| 爬取难度 | 高 | 需要 Selenium / Playwright / scrapling |
| 价格数据 | 🔴 JS渲染 | AJAX 动态加载，requests 无法获取 |
| 配置参数 | 🔴 JS渲染 | 动态渲染 |
| 竞品对比 | 🔴 JS渲染 | 页面 SPA |

**技术方案**：
```bash
# scrapling 可行（需 --network-idle 等待 JS 加载）
scrapling extract fetch https://www.autohome.com.cn/grade/carhtml/B.html
```

**结论**：需要 scrapling（Homebrew 安装），CLI 已集成 scrapling 可用 ✅

---

## 2. 易车 (yiche.com)

| 维度 | 评分 | 说明 |
|------|------|------|
| 页面渲染方式 | 🟡 中 | 部分 JS 渲染，列表页可能可直接 requests |
| 爬取难度 | 中 | 先尝试 requests，降级到 scrapling |
| 价格数据 | 🟡 视页面 | 车型页通常 AJAX |
| 配置参数 | 🟡 视页面 | 动态加载 |

**技术方案**：先尝试 requests，失败则 scrapling

**结论**：混合方案，可用 scrapling 统一处理 ✅

---

## 3. 懂车帝 (dongchedi.com)

| 维度 | 评分 | 说明 |
|------|------|------|
| 页面渲染方式 | 🔴 高 | ByteDance 系，全 JS 渲染，反爬严格 |
| 爬取难度 | 高 | 强反爬 + JS 渲染 |
| 价格数据 | 🔴 API | 可能直接调后端 API，需要抓包分析 |
| 配置参数 | 🔴 JS渲染 | 动态 |

**技术方案**：
- 简单抓取：scrapling（但可能被反爬拦截）
- 精准抓取：需抓包找 API 接口

**结论**：高难度，优先考虑其他数据源 ⚠️

---

## 4. 备选数据源

### 国家数据平台（无反爬）
| 数据源 | 优点 | 缺点 |
|--------|------|------|
| 工信部公告 | 权威、无反爬 | 只有公告，无价格/配置 |
| 机动车出厂合格证 | 权威数据 | 普通用户无法访问 |
| 国家统计局 | 汽车产销数据 | 宏观数据，非车型粒度 |

### 第三方汽车媒体
| 数据源 | 难度 | 说明 |
|--------|------|------|
| 太平洋汽车 | 🟡 中 | 部分 JS，部分可直接 requests |
| 网上车市 | 🟡 中 | PGC 内容为主，可直接 requests |
| 58同城汽车 | 🟡 中 | 有反爬但可绕过 |

---

## 5. 推荐技术方案

### 方案 A：scrapling 全家桶（推荐）
```python
# 所有 JS 渲染页面统一使用 scrapling
fetch_with_scrapling(url, timeout=30)
```
- 优点：统一方案，无需分别处理
- 缺点：慢（每个页面等待 JS 渲染）
- 依赖：Homebrew 安装 scrapling

### 方案 B：requests 优先 + scrapling 降级
```python
# 先尝试 requests（轻量快速）
html = requests.get(url).text
if "动态内容特征" in html:
    html = fetch_with_scrapling(url)
```
- 优点：快就快，慢就降级
- 缺点：需要维护降级逻辑

### 方案 C：API 直连（懂车帝等）
- F12 抓包找到数据 API
- 直接请求 API（绕过页面渲染）
- 风险：API 可能随时变化

---

## 6. 实现决策

| 组件 | 实现方案 | 状态 |
|------|----------|------|
| 汽车之家车型页 | scrapling | ✅ 可实现 |
| 易车车型页 | scrapling | ✅ 可实现 |
| 懂车帝 | scrapling + API | ⚠️ 复杂，先文档记录 |
| 价格监测 | scrapling | ✅ 可实现 |
| 竞品对比 | scrapling | ✅ 可实现 |
| 变更提醒 | diff 算法 | ✅ 可实现 |

**最终推荐**：使用 **scrapling 全家桶** 方案，CLI 已集成，无需额外依赖。

---

## 7. 下一步

1. ✅ monitor.py 使用 scrapling 方案
2. ⚠️ 如遇懂车帝强反爬，输出提示切换汽车之家/易车
3. 🔄 长期：考虑接入官方 API（若有）
