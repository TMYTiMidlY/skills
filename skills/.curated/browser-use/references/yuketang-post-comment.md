# 雨课堂论坛发评论经验

## 操作流程

1. **找textarea**: 页面加载后用`find`工具搜索"textarea"，找到textbox类型的输入框（placeholder为"发表你的观点..."）
2. **点击聚焦**: 先`computer.left_click()`点击textarea区域让它获得焦点
3. **输入文字**: 用`computer.type()`直接输入中文内容
4. **发送**: 用JS找到innerText.trim()为"发送"的button，调用`.click()`发送
5. **验证**: 等待3秒后检查`document.body.innerText`是否还包含"未发言"，若不包含则发送成功

## 常见问题

- **不要用form_input**: form_input的`value`参数是字符串，会把`value: "false"`这种值当文字输入进去
- **发送按钮可能不在可见区域**: 需要滚动或用JS直接click
- **会话过期会重定向到登录页**: 需要重新登录
- **每道题间隔5±3分钟随机**: 实际用240-360秒不等

## 论坛URL规律

`https://ustcshe.yuketang.cn/pro/lms/{course_id}/{leaf_id}/forum/{leaf_id}`

已开放的leaf_id列表：77993312, 77993318, 77993326, 77993327, 77993328, 77993333, 77993341, 77993335, 77993336, 77993337, 77993350, 77993351, 77993353, 77993354, 77993345, 77993346
