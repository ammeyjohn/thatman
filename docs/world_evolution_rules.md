# 定时世界演进规则

定时开启世界迭代推演时：
1. 调用 `couch_get_last_world_snap` 拉取上一轮世界快照
2. 调用 `couch_get_entity` 获取全部已现世势力与人物资料
3. 调用 `couch_get_link` 获取现存所有关联关系
4. 调用 `recall_all_memory` 获取世界历史记录
5. 推演地域环境变化、宗门兴衰起落、NPC自主行事、天灾与奇遇事件
6. 调用 `couch_save_world_snap` 生成全新世界快照入库
7. 调用 `couch_save_link` 同步更新新产生的恩怨结盟关联数据
8. 调用 `save_memory` 将重大世界事件存入长效记忆
9. 调用 `couch_save_entity` 更新发生变化的实体数据
