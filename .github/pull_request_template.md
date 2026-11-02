## 这个 PR 做了什么

<!-- 一两句话说清楚，比如：修了设置里切换后端后状态栏不更新的问题 -->

## 改动类型

- [ ] 修复 bug
- [ ] 新功能
- [ ] 界面 / 外观
- [ ] 文档
- [ ] 重构（不改变行为）
- [ ] 其它

## 怎么验证的

<!-- 说清楚你实际跑过什么，截图更好 -->

```
1. 启动 ollama serve
2. python qwen_chat.py
3. ...
```

## 自查清单

- [ ] 本地跑过 `python tests/test_basic.py`，全部通过
- [ ] `python -m compileall -q .` 没有语法错误
- [ ] 涉及界面时附了截图
- [ ] 没有提交 `settings.json`、`sessions/`、个人图片
- [ ] 如果是新后端，已在 `providers.py` 里加适配器并补了测试

## 相关 Issue

<!-- 例如：Closes #12 -->
