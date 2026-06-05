# 剧情线主从视图 —— 设计文档

- 日期：2026-06-05
- 主题：把看板「剧情结构」标签页从通用卡片网格升级为专门的「幕大纲 + 详情」主从视图
- 状态：已与用户对齐，待实现

## 1. 背景与动机

当前一个游戏/剧本的剧情线设定（幕 `act_plan` + 主线节点 `main_quest_path`）和其它设定共用同一套通用卡片网格（`BoardBlockGrid`），通过点开 `BlockDetailModal` 逐块编辑。痛点：**剧情线散在通用看板里，没有专属的编辑形态**，看不清「幕 → 节点」的从属与走向，编辑效率低。

数据模型本身够用（线性「幕 → 主线节点」两层结构，节点靠 `act_id` 归属到幕、靠 `transition_to_next_act` 推进），无需改结构。本次只解决**编辑入口/编辑体验**问题。

## 2. 目标 / 非目标

**目标**
- 切到看板「剧情结构」(`plot`) 标签页时，呈现专门的主从视图：顶部剧情纲领总览、左幕大纲、右幕详情（含该幕节点列表）
- 支持字段就地编辑 + 增删幕/节点，编辑闭环完整
- 完全复用现有 `SettingsBoard` 的读写/diff/写回链路，不碰后端

**非目标（YAGNI）**
- 不做节点拖拽重排 / 跨幕拖动改归属（顺序与归属靠字段调整）
- 不改后端 schema、`story_blueprint` 运行时、StoryDirector 消费逻辑
- 不改其它标签页（世界观/角色/玩法/约束/素材）的呈现
- 不新增页面/路由，不动 `AppShell` 导航

## 3. 现状关键事实（实现依据）

- 看板组件 `web/components/board/SettingsBoard.tsx` 出现在两个页面：`web/app/games/new/page.tsx`、`web/app/games/[id]/settings/page.tsx`
- `SettingsBoard` 持有 `activeTab` state（默认 `world`），当前 tab 的 `current.blocks` 交给 `BoardBlockGrid` 渲染
- 编辑/删除/新增已抽成回调，由父页面落到 settings payload + diff：
  - `onEditBlock(block, fields)` —— 编辑块字段
  - `onDeleteBlock(block)` —— 删除块
  - `onAddItem(arrayKey, item)` —— 往数组类设定新增一项
- `lib/generatorBoard.ts` 的 `buildBoardModel` 把 settings 还原成分类化的 `BoardModel`：
  - 幕：plot 分类，block.address = `settingsItem { arrayKey: "act_plan" }`
  - 主线节点：plot 分类，block.address = `settingsItem { arrayKey: "main_quest_path" }`，含 `act_id` 字段
  - 剧情纲领标量（premise/central_mystery/main_goal/emotional_arc/narrative_style/core_fantasy）：**world 分类**，block.address = `settingsScalar { path: ["story_core", k] }`

## 4. 设计

### 4.1 架构与接入点

- 新增组件 `web/components/board/PlotMasterDetail.tsx`
- 在 `SettingsBoard` 中，当 `activeTab === "plot"` 时用 `PlotMasterDetail` **替换** `BoardBlockGrid`，其它分支不变
- `PlotMasterDetail` 接收与 `SettingsBoard` 同源的 props：`model`、`diff`、`lockedIds`、`onEditBlock`、`onDeleteBlock`、`onAddItem`
- **不新增任何数据流**：所有写操作走上述既有回调

### 4.2 数据派生（纯函数，可单测）

新增 `web/lib/plotView.ts`，导出纯函数：

```ts
function derivePlotView(model: BoardModel): {
  overview: BoardBlock[];      // 纲领标量块（来自 world 分类的 story_core.*）
  acts: Array<{
    actBlock: BoardBlock;      // 幕块
    nodes: BoardBlock[];       // 归属该幕的主线节点块
  }>;
  unassignedNodes: BoardBlock[]; // act_id 指向不存在幕的孤儿节点
};
```

派生规则：
- `overview` = world 分类中 `address.kind === "settingsScalar" && path[0] === "story_core"` 的块，按既定字段顺序排列
- 幕 = plot 分类中 `address.arrayKey === "act_plan"` 的块，保持 model 内顺序
- 节点 = plot 分类中 `address.arrayKey === "main_quest_path"` 的块，读其 `act_id` 字段值，分组挂到匹配的幕；匹配不到则进 `unassignedNodes`

> 不依赖 React，便于 vitest 单测（与 `generatorBoard.ts` 同风格）。

### 4.3 交互与写回

| 操作 | 落地回调 |
|------|----------|
| 编辑纲领/幕/节点任意字段 | `onEditBlock(block, fields)` |
| 新增幕 | `onAddItem("act_plan", { id, title, ... })` |
| 新增节点 | `onAddItem("main_quest_path", { act_id: 当前选中幕, ... })`，`act_id` 预填 |
| 删除幕 / 删除节点 | `onDeleteBlock(block)` |

- 「当前选中幕」由 `PlotMasterDetail` 内部 state 管理，默认第一幕；删除当前幕后回退到第一幕（无幕则空态）
- 字段编辑形态：**默认复用现有 `BlockDetailModal`**（点幕/节点/纲领项 → 弹窗编辑），不自造编辑控件，以最大化复用并保持与其它 tab 一致的编辑手感
- 新增幕/节点的身份必填校验沿用 `SettingsBoard` 现有逻辑（`idKey` 非空才提交，重名/合法性由后端 validate 兜底）

### 4.4 边界与降级

- **无幕**：左栏只显示「＋ 新增幕」，右栏空态提示
- **孤儿节点**（`act_id` 指向不存在的幕）：归入「未分配」分组展示，可编辑其 `act_id` 重新归位，**绝不丢失**
- **纲领空字段**：始终显示标签且可编辑，不依赖「显示空设定项」开关
- **锁定块**（`lockedIds`）：沿用现有锁定态展示与 `onUnlockBlock`（若父页面提供）

### 4.5 测试

- `lib/plotView.test.ts`（vitest）覆盖 `derivePlotView`：
  - 节点按 `act_id` 正确分组到幕
  - 孤儿节点归入 `unassignedNodes`
  - 纲领镜像：world 分类的 story_core 标量被正确提取且不重复
  - 空态：无幕 / 无节点 / 无纲领
- 复用现有回调，无需后端改动与新迁移

## 5. 文件清单

- 新增 `web/lib/plotView.ts` —— `derivePlotView` 纯函数
- 新增 `web/lib/plotView.test.ts` —— 单测
- 新增 `web/components/board/PlotMasterDetail.tsx` —— 主从视图组件
- 修改 `web/components/board/SettingsBoard.tsx` —— `activeTab === "plot"` 时切换渲染

## 6. 风险与注意

- 纲领总览与「世界观」tab 是同一份 story_core 数据的两处入口，编辑后都经 `onEditBlock` 写回同一 `settingsScalar` 地址，diff 一致，无双写冲突
- `act_id` 字段在节点块中的 key/类型需与 `generatorBoard.ts` 中 `main_quest_path` 的字段定义一致（实现前核对 `deriveFields` 对 `act_id` 的处理）
- 遵守项目约定：完成后在 `docs/OPTIMIZATION_PLAN.md §1` 追加 `Round N` 条目（本次设计文档不替代该记录）
