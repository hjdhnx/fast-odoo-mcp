# PyPI 发布指南

本文档说明如何将 `fast-odoo-mcp` 发布到 [PyPI](https://pypi.org/)。

## 前置条件

- PyPI 账号（在 [pypi.org](https://pypi.org/account/register/) 注册）
- 项目仓库的管理员权限（用于配置 GitHub Secrets 和创建 Release）
- 本地已安装 `build` 和 `twine`：`pip install build twine`

## 发布方式

项目提供了两种发布方式，推荐使用 **方式一（GitHub Actions 自动发布）**。

---

## 方式一：GitHub Actions 自动发布（推荐）

项目已配置 `.github/workflows/publish.yml`，当创建 GitHub Release 时自动构建并发布到 PyPI。

### 步骤 1：在 PyPI 配置 Trusted Publisher

使用 OIDC Trusted Publishing 无需手动管理 API Token，更加安全。

1. 登录 [PyPI](https://pypi.org/)
2. 进入 **Account settings → Publishing**
3. 点击 **Add a new publisher**
4. 选择 **GitHub**，填写以下信息：

| 字段 | 值 |
|------|-----|
| PyPI Project Name | `fast-odoo-mcp` |
| Owner | `hjdhnx` |
| Repository name | `fast-odoo-mcp` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

5. 点击 **Add** 完成配置

> **首次发布新包**：如果包名在 PyPI 上尚不存在，PyPI 会提示你先通过其他方式创建。此时请跳到"首次发布备选方案"章节。

### 步骤 2：创建 GitHub Release

1. 打开 [Releases 页面](https://github.com/hjdhnx/fast-odoo-mcp/releases/new)
2. 填写 Release 信息：

| 字段 | 值 |
|------|-----|
| Choose a tag | `v1.0.1`（选择 "Create new tag on publish"） |
| Release title | `v1.0.1` |
| Describe this release | 填写更新说明 |

3. 点击 **Publish release**

### 步骤 3：确认发布结果

1. 进入 [Actions 页面](https://github.com/hjdhnx/fast-odoo-mcp/actions)
2. 找到 **Publish to PyPI** 工作流，确认运行成功
3. 访问 https://pypi.org/project/fast-odoo-mcp/ 确认包已发布

### 首次发布备选方案

如果 PyPI 上包名不存在导致 Trusted Publisher 配置失败，可以先用 API Token 手动发布一次：

1. 在 PyPI 创建 API Token（Account settings → API tokens → Add API token）
2. 在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中添加：
   - Name: `PYPI_API_TOKEN`
   - Value: 粘贴 PyPI 生成的 token
3. 修改 `.github/workflows/publish.yml`，将最后一步改为：

```yaml
    - name: Publish to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        password: ${{ secrets.PYPI_API_TOKEN }}
```

4. 创建 Release 触发发布
5. 发布成功后，回到 PyPI 配置 Trusted Publisher，以后就可以免 Token 发布了

---

## 方式二：本地手动发布

适合调试或紧急发布场景。

### 步骤 1：更新版本号

在 `pyproject.toml` 中修改 `version`：

```toml
version = "1.0.2"  # 改为新版本号
```

### 步骤 2：构建

```bash
python -m build
```

成功后在 `dist/` 目录下生成：
- `fast_odoo_mcp-<version>.tar.gz`（源码包）
- `fast_odoo_mcp-<version>-py3-none-any.whl`（wheel 包）

### 步骤 3：检查

```bash
twine check --strict dist/*
```

确保输出 `PASSED`。

### 步骤 4：上传到 TestPyPI（可选，推荐首次发布时测试）

```bash
twine upload --repository testpypi dist/*
```

然后在 https://test.pypi.org/project/fast-odoo-mcp/ 确认包内容。

### 步骤 5：上传到正式 PyPI

```bash
twine upload dist/*
```

输入 PyPI 用户名和密码（或 API Token）。

---

## 版本号规范

遵循 [语义化版本](https://semver.org/lang/zh-CN/)：`MAJOR.MINOR.PATCH`

| 场景 | 版本变更 | 示例 |
|------|----------|------|
| 修复 bug | PATCH +1 | `1.0.1` → `1.0.2` |
| 新增功能（向后兼容） | MINOR +1 | `1.0.1` → `1.1.0` |
| 破坏性变更 | MAJOR +1 | `1.1.0` → `2.0.0` |

## 发布检查清单

- [ ] 更新 `pyproject.toml` 中的 `version`
- [ ] 更新 `CHANGELOG.md` 中的更新日志
- [ ] 本地运行 `python -m build && twine check --strict dist/*` 确认通过
- [ ] 运行单元测试确认无回归：`pytest -m "not yolo and not mcp"`
- [ ] 提交代码并推送到 main 分支
- [ ] 创建 GitHub Release（tag 格式 `v<version>`）
- [ ] 确认 GitHub Actions 发布成功
- [ ] 在 PyPI 上确认新版本已发布
- [ ] 通知用户更新：`pip install --upgrade fast-odoo-mcp`

## 常见问题

### 上传失败：File already exists

PyPI 不允许覆盖已发布的版本。解决方案：
1. 在 `pyproject.toml` 中递增版本号
2. 重新构建和上传

### 上传失败：Invalid or non-existent authentication

确保使用正确的 API Token，格式为 `pypi-...`。在 twine 命令中使用时，用户名填 `__token__`，密码填完整的 token。

### GitHub Actions 发布失败：Permission denied

确认已在 PyPI 上正确配置 Trusted Publisher，且 repository owner、name、workflow filename 和 environment 都匹配。
